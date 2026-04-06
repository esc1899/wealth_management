"""
Benchmark — performance tests per agent/skill/model.

Run the same agent call repeatedly (with fixed inputs) and compare
token costs over time. Useful after prompt or model changes.

Supported scenarios:
  - structural_scan: runs a scan with a chosen skill (no position needed)
  - news:            runs a digest for a fixed ticker list
"""

import asyncio
import threading

import pandas as pd
import streamlit as st

from core.i18n import t
from core.storage.usage import compute_cost
from state import (
    get_app_config_repo,
    get_news_agent,
    get_news_repo,
    get_skills_repo,
    get_structural_change_agent,
    get_structural_scans_repo,
    get_usage_repo,
)

st.set_page_config(page_title="Benchmark", page_icon="⚡", layout="wide")
st.title(f"⚡ {t('benchmark.title')}")
st.caption(t("benchmark.subtitle"))
st.info(t("benchmark.caption"))

usage_repo = get_usage_repo()
config_repo = get_app_config_repo()
model_prices = config_repo.get_model_prices()
skills_repo = get_skills_repo()

_BENCHMARK_JOB_KEY = "_benchmark_job"

if _BENCHMARK_JOB_KEY not in st.session_state:
    st.session_state[_BENCHMARK_JOB_KEY] = {
        "running": False,
        "done": False,
        "result": None,
        "error": None,
    }

_job = st.session_state[_BENCHMARK_JOB_KEY]

# ------------------------------------------------------------------
# Background runner helpers
# ------------------------------------------------------------------

def _run_structural_benchmark(agent, skill_name, skill_prompt, repo, job: dict):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        run, _ = loop.run_until_complete(
            agent.start_scan(
                skill_name=skill_name,
                skill_prompt=skill_prompt,
                user_focus=None,
                repo=repo,
            )
        )
        job.update({"running": False, "done": True, "result": run.id, "error": None})
    except Exception as exc:
        job.update({"running": False, "done": True, "result": None, "error": str(exc)})
    finally:
        loop.close()


def _run_news_benchmark(agent, tickers, ticker_names, skill_name, skill_prompt, repo, job: dict):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        run, _ = loop.run_until_complete(
            agent.start_run(
                tickers=tickers,
                ticker_names=ticker_names,
                skill_name=skill_name,
                skill_prompt=skill_prompt,
                user_context="",
                repo=repo,
            )
        )
        job.update({"running": False, "done": True, "result": run.id, "error": None})
    except Exception as exc:
        job.update({"running": False, "done": True, "result": None, "error": str(exc)})
    finally:
        loop.close()


# ------------------------------------------------------------------
# Run form
# ------------------------------------------------------------------

st.subheader(t("benchmark.run_header"))

_SCENARIO_OPTIONS = {
    "structural_scan": t("benchmark.scenario_structural"),
    "news": t("benchmark.scenario_news"),
}

_sc1, _sc2 = st.columns(2)
with _sc1:
    _scenario_key = st.selectbox(
        t("benchmark.agent_label"),
        options=list(_SCENARIO_OPTIONS.keys()),
        format_func=lambda k: _SCENARIO_OPTIONS[k],
        key="_bm_scenario",
        disabled=_job["running"],
    )

_scenario_skills = skills_repo.get_by_area(_scenario_key)
_skill_map = {s.name: s for s in _scenario_skills}

with _sc2:
    if _skill_map:
        _sel_skill_name = st.selectbox(
            t("benchmark.skill_label"),
            options=list(_skill_map.keys()),
            key="_bm_skill",
            disabled=_job["running"],
        )
        _sel_skill = _skill_map[_sel_skill_name]
    else:
        st.warning(t("benchmark.no_skill"))
        _sel_skill = None
        _sel_skill_name = ""

# News-specific: ticker input
_tickers_raw = ""
if _scenario_key == "news":
    _tickers_raw = st.text_input(
        t("benchmark.news_tickers_label"),
        value=t("benchmark.news_tickers_default"),
        key="_bm_tickers",
        disabled=_job["running"],
    )

_bm_label = st.text_input(
    t("benchmark.label_label"),
    placeholder=t("benchmark.label_placeholder"),
    key="_bm_label",
    disabled=_job["running"],
)

# Auto-refresh while running
if _job["running"]:
    import time
    st.info(t("benchmark.running"))
    time.sleep(3)
    st.rerun()

# Handle completion
if _job["done"] and not _job["running"]:
    if _job["error"]:
        st.error(t("benchmark.error").format(error=_job["error"]))
    elif _job.get("pending_record"):
        # Record the benchmark result now (in main thread)
        pr = _job["pending_record"]
        usage_repo.record_benchmark(
            scenario_name=pr["scenario_name"],
            agent=pr["agent"],
            model=pr["model"],
            skill_name=pr["skill_name"],
            input_tokens=pr["input_tokens"],
            output_tokens=pr["output_tokens"],
            cost_eur=pr["cost_eur"],
            label=pr["label"] or None,
            duration_ms=pr.get("duration_ms"),
        )
        total_tokens = pr["input_tokens"] + pr["output_tokens"]
        st.success(t("benchmark.success").format(tokens=total_tokens, cost=pr["cost_eur"]))
    _job.update({"done": False, "result": None, "error": None, "pending_record": None})

if st.button(t("benchmark.run_button"), disabled=_job["running"] or not _sel_skill, type="primary"):
    if not model_prices:
        st.warning(t("benchmark.prices_missing"))

    # Snapshot usage counts before the run to compute delta
    import time as _time
    _before = usage_repo.total_all_time()
    _before_map = {
        (r["agent"], r["model"], r["skill"]): (r["input_tokens"], r["output_tokens"])
        for r in _before
    }
    _bm_start = _time.monotonic()

    def _after_run_record(scenario_key, skill_name, model, label):
        """Called after background thread completes to record benchmark result."""
        _after = usage_repo.total_all_time()
        _after_map = {
            (r["agent"], r["model"], r["skill"]): (r["input_tokens"], r["output_tokens"])
            for r in _after
        }
        # Find agent name for this scenario
        _agent_names = {
            "structural_scan": "structural_scan",
            "news": "news_digest",
        }
        _agent_key = _agent_names.get(scenario_key, scenario_key)

        # Find delta for this agent/model/skill
        _in_delta = 0
        _out_delta = 0
        for (a, m, s), (inp, out) in _after_map.items():
            if a == _agent_key and m == model:
                _prev_inp, _prev_out = _before_map.get((a, m, s), (0, 0))
                _in_delta += inp - _prev_inp
                _out_delta += out - _prev_out

        _cost = compute_cost(_in_delta, _out_delta, model, model_prices)
        _duration_ms = int((_time.monotonic() - _bm_start) * 1000)
        _job["pending_record"] = {
            "scenario_name": f"{scenario_key}/{skill_name}",
            "agent": _agent_key,
            "model": model,
            "skill_name": skill_name,
            "input_tokens": _in_delta,
            "output_tokens": _out_delta,
            "cost_eur": _cost,
            "duration_ms": _duration_ms,
            "label": label,
        }
        _job.update({"running": False, "done": True, "error": None})

    _job.update({"running": True, "done": False, "result": None, "error": None, "pending_record": None})

    if _scenario_key == "structural_scan":
        _agent = get_structural_change_agent()
        _repo = get_structural_scans_repo()
        _model = config_repo.get(f"model_claude_structural_scan") or "claude-sonnet-4-6"

        def _bg_structural():
            _run_structural_benchmark(_agent, _sel_skill.name, _sel_skill.prompt, _repo, _job)
            _after_run_record(_scenario_key, _sel_skill.name, _model, _bm_label)

        threading.Thread(target=_bg_structural, daemon=True).start()

    elif _scenario_key == "news":
        _tickers = [tok.strip().upper() for tok in _tickers_raw.split(",") if tok.strip()]
        _news_agent = get_news_agent()
        _news_repo = get_news_repo()
        _model = config_repo.get("model_claude_news") or "claude-haiku-4-5-20251001"

        def _bg_news():
            _run_news_benchmark(
                _news_agent, _tickers, {}, _sel_skill.name, _sel_skill.prompt, _news_repo, _job
            )
            _after_run_record(_scenario_key, _sel_skill.name, _model, _bm_label)

        threading.Thread(target=_bg_news, daemon=True).start()

    st.rerun()

# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------

st.divider()
st.subheader(t("benchmark.history_header"))

_all_runs = usage_repo.get_benchmark_runs()

if not _all_runs:
    st.info(t("benchmark.no_history"))
else:
    df_bm = pd.DataFrame(_all_runs)
    df_bm = df_bm.drop(columns=["id", "agent"], errors="ignore")
    if "duration_ms" in df_bm.columns:
        df_bm["duration_s"] = (df_bm["duration_ms"] / 1000).round(1)
        df_bm = df_bm.drop(columns=["duration_ms"])
    df_bm = df_bm.rename(columns={
        "scenario_name": t("benchmark.col_scenario"),
        "label":         t("benchmark.col_label"),
        "model":         t("benchmark.col_model"),
        "skill_name":    t("benchmark.col_skill"),
        "input_tokens":  t("benchmark.col_input"),
        "output_tokens": t("benchmark.col_output"),
        "cost_eur":      t("benchmark.col_cost"),
        "duration_s":    "Dauer (s)",
        "run_at":        t("benchmark.col_run_at"),
    })
    st.dataframe(df_bm, use_container_width=True, hide_index=True)

    # Trend chart per scenario
    _scenarios = usage_repo.get_benchmark_scenarios()
    if len(_scenarios) > 0:
        _sel_sc = st.selectbox(
            t("benchmark.col_scenario"),
            options=_scenarios,
            key="_bm_hist_scenario",
        )
        _sc_runs = usage_repo.get_benchmark_runs(_sel_sc)
        if _sc_runs:
            df_trend = pd.DataFrame(_sc_runs)
            df_trend = df_trend.sort_values("run_at")
            df_trend["label_or_date"] = df_trend.apply(
                lambda r: r["label"] if r["label"] else r["run_at"][:16], axis=1
            )
            import plotly.express as px
            fig = px.bar(
                df_trend,
                x="label_or_date",
                y="cost_eur",
                color="model",
                labels={"label_or_date": t("benchmark.col_label"), "cost_eur": t("benchmark.col_cost")},
                title=_sel_sc,
            )
            fig.update_layout(xaxis_title="", yaxis_title=t("benchmark.col_cost"))
            st.plotly_chart(fig, use_container_width=True)
