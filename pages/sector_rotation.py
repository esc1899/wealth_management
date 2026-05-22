"""
Sector Rotation Monitor — analyzes sector rotation momentum vs. portfolio positioning.

Cloud agent (Claude ☁️) uses web_search to research current sector flows,
maps portfolio tickers to GICS sectors, and delivers per-sector verdicts +
a full markdown report.
"""

import asyncio
import threading
import time

import streamlit as st

from core.i18n import t, current_language
from core.ui.verdicts import VERDICT_CONFIGS, verdict_badge, cloud_notice
from core.ui.markdown import llm_markdown
from state import (
    get_portfolio_service,
    get_sector_rotation_agent,
    get_sector_rotation_repo,
    get_skills_repo,
)

st.set_page_config(
    page_title="Sector Rotation Monitor",
    page_icon=":material/rotate_right:",
    layout="wide",
)
st.title(f":material/rotate_right: {t('sector_rotation.title')}")
st.caption(t("sector_rotation.subtitle"))

_agent = get_sector_rotation_agent()
cloud_notice(_agent.model, provider="claude")

_repo = get_sector_rotation_repo()
_skills = get_skills_repo().get_by_area("sector_rotation")
_portfolio_service = get_portfolio_service()

if not _skills:
    st.warning(t("sector_rotation.no_skills"))
    st.stop()

_VERDICT_CONFIG = VERDICT_CONFIGS["sector_rotation"]

_MOMENTUM_LABELS = {
    "inflow":  t("sector_rotation.momentum_inflow"),
    "neutral": t("sector_rotation.momentum_neutral"),
    "outflow": t("sector_rotation.momentum_outflow"),
}

# ------------------------------------------------------------------
# Background job tracking
# ------------------------------------------------------------------

if "_sr_job" not in st.session_state:
    st.session_state["_sr_job"] = {
        "running": False, "done": False, "run_id": None,
        "error": None, "last_error": None,
    }

_JOB = st.session_state["_sr_job"]

if "sr_run_id" not in st.session_state:
    st.session_state["sr_run_id"] = None


def _run_background(agent, positions, skill_name, skill_prompt, language: str, repo, job: dict):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        run, _, verdicts = loop.run_until_complete(
            agent.start_scan(
                positions=positions,
                skill_name=skill_name,
                skill_prompt=skill_prompt,
                language=language,
            )
        )
        job.update({"running": False, "done": True, "run_id": run.id, "error": None})
    except Exception as exc:
        job.update({"running": False, "done": True, "run_id": None,
                    "error": str(exc), "last_error": str(exc)})
    finally:
        loop.close()


# ------------------------------------------------------------------
# Layout: left column (controls) + right column (results)
# ------------------------------------------------------------------

_col_left, _col_right = st.columns([1, 2])

with _col_left:
    st.subheader(t("sector_rotation.new_scan_header"))

    _skill_options = {s.name: s for s in _skills}
    _sel_skill_name = st.selectbox(
        t("sector_rotation.skill_label"),
        options=list(_skill_options.keys()),
        key="_sr_skill",
        disabled=_JOB["running"],
    )
    _sel_skill = _skill_options[_sel_skill_name]

    # Portfolio context — show which positions will be sent
    _positions = _portfolio_service.get_public_positions(include_portfolio=True, include_watchlist=False)
    _ticker_positions = [p for p in _positions if p.ticker]

    with st.expander(t("sector_rotation.portfolio_context"), expanded=False):
        if _ticker_positions:
            for p in _ticker_positions:
                st.caption(f"**{p.ticker}** — {p.name} ({p.asset_class})")
        else:
            st.caption("Keine Positionen mit Ticker gefunden.")

    if st.button(
        t("sector_rotation.run_button"),
        type="primary",
        key="_sr_start",
        disabled=_JOB["running"] or not _ticker_positions,
    ):
        _lang = current_language()
        _JOB["running"] = True
        _JOB["done"] = False
        _JOB["run_id"] = None
        _JOB["error"] = None
        _t = threading.Thread(
            target=_run_background,
            args=(_agent, _ticker_positions, _sel_skill.name, _sel_skill.prompt, _lang, _repo, _JOB),
            daemon=True,
        )
        _t.start()
        st.rerun()

    if not _ticker_positions:
        st.caption("Keine Portfolio-Positionen mit Ticker — bitte zuerst Marktdaten aktualisieren.")

# Running indicator — auto-refresh every 5s
if _JOB["running"]:
    st.info(f"⏳ {t('sector_rotation.running')}", icon=":material/hourglass_top:")
    time.sleep(5)
    st.rerun()

# Done: update active run
if _JOB["done"]:
    if _JOB["error"]:
        import logging
        logging.getLogger(__name__).error("Sector rotation error: %s", _JOB["error"])
        st.error("❌ Sector Rotation Scan fehlgeschlagen. Bitte versuchen Sie es später erneut.")
    elif _JOB["run_id"]:
        st.session_state["sr_run_id"] = _JOB["run_id"]
    _JOB["done"] = False
    if _JOB["run_id"]:
        st.rerun()

if _JOB.get("last_error") and not _JOB["running"]:
    import logging
    logging.getLogger(__name__).error("Last SR error: %s", _JOB["last_error"])
    st.error("❌ Letzter Scan fehlgeschlagen. Bitte versuchen Sie es später erneut.")

# ------------------------------------------------------------------
# Active run — verdicts + report
# ------------------------------------------------------------------

_active_run_id = st.session_state.get("sr_run_id")

# Auto-load latest run if none active
if _active_run_id is None:
    _latest = _repo.get_recent_runs(limit=1)
    if _latest:
        _active_run_id = _latest[0].id
        st.session_state["sr_run_id"] = _active_run_id

with _col_right:
    if _active_run_id:
        _run = _repo.get_run(_active_run_id)
        if _run:
            st.subheader(
                f"{t('sector_rotation.report_header')} — "
                f"{_run.created_at.strftime('%d.%m.%Y %H:%M')} · {_run.skill_name}"
            )

            # Sektor-Verdicts als Karten
            _verdicts = _repo.get_verdicts(_active_run_id)
            if _verdicts:
                st.markdown(f"**{t('sector_rotation.verdicts_header')}**")
                _vcols = st.columns(min(len(_verdicts), 3))
                for i, sv in enumerate(_verdicts):
                    with _vcols[i % 3]:
                        _badge = verdict_badge(sv.verdict, _VERDICT_CONFIG)
                        _momentum_label = _MOMENTUM_LABELS.get(sv.momentum or "neutral", sv.momentum or "")
                        st.markdown(
                            f"**{sv.sector}**  \n"
                            f"{_badge} · {_momentum_label}"
                        )
                        if sv.summary:
                            st.caption(sv.summary)
                st.divider()

            # Vollständiger Report
            with st.expander(t("sector_rotation.report_header"), expanded=True):
                llm_markdown(_run.result)

            if st.button(t("sector_rotation.new_scan_button"), key="_sr_new"):
                st.session_state["sr_run_id"] = None
                st.rerun()
    else:
        st.info(t("sector_rotation.no_runs"))

# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------

_recent = _repo.get_recent_runs(limit=8)
_history = [r for r in _recent if r.id != _active_run_id]

if _history:
    st.divider()
    st.subheader(t("sector_rotation.history_header"))
    for _h in _history:
        _label = f"{_h.created_at.strftime('%d.%m.%Y %H:%M')} — {_h.skill_name}"
        with st.expander(_label):
            _h_verdicts = _repo.get_verdicts(_h.id)
            if _h_verdicts:
                _summary_parts = [
                    f"{verdict_badge(sv.verdict, _VERDICT_CONFIG)} {sv.sector}"
                    for sv in _h_verdicts
                ]
                st.caption(" · ".join(_summary_parts))
            llm_markdown(_h.result)
            if st.button(
                "Laden",
                key=f"_sr_load_{_h.id}",
            ):
                st.session_state["sr_run_id"] = _h.id
                st.rerun()
