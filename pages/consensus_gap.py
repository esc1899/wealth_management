"""
Konsens-Lücken-Analyse — Claude's Anlagestrategie, Säule 2.

Misst für jede Portfolio-Position den Abstand zwischen der eigenen These
und dem Markt-Konsens. Zeigt wo der Markt (noch) falsch liegt.
"""

import asyncio
import threading
import time

import streamlit as st

from core.i18n import t
from state import (
    get_analyses_repo,
    get_consensus_gap_agent,
    get_positions_repo,
    get_skills_repo,
)

st.set_page_config(
    page_title="Konsens-Lücken",
    page_icon="🎯",
    layout="wide",
)
st.title(f"🎯 {t('consensus_gap.title')}")
st.caption(t("consensus_gap.subtitle"))

_agent = get_consensus_gap_agent()
_positions_repo = get_positions_repo()
_analyses_repo = get_analyses_repo()
_skills = get_skills_repo().get_by_area("consensus_gap")

# ------------------------------------------------------------------
# Background job tracking (session_state — survives reruns)
# ------------------------------------------------------------------

if "_cgap_job" not in st.session_state:
    st.session_state["_cgap_job"] = {"running": False, "done": False, "count": 0, "error": None, "last_error": None}

_JOB = st.session_state["_cgap_job"]


def _run_background(agent, positions, skill_name, skill_prompt, analyses_repo, job: dict):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(
            agent.analyze_portfolio(
                positions=positions,
                skill_name=skill_name,
                skill_prompt=skill_prompt,
                analyses_repo=analyses_repo,
            )
        )
        job.update({"running": False, "done": True, "count": len(results), "error": None})
    except Exception as exc:
        job.update({"running": False, "done": True, "count": 0, "error": str(exc), "last_error": str(exc)})
    finally:
        loop.close()


# ------------------------------------------------------------------
# Verdict display helpers
# ------------------------------------------------------------------

_VERDICT_CONFIG = {
    "wächst":    ("🟢", t("consensus_gap.verdict_waechst")),
    "stabil":    ("🟡", t("consensus_gap.verdict_stabil")),
    "schließt":  ("🟠", t("consensus_gap.verdict_schliesst")),
    "eingeholt": ("🔴", t("consensus_gap.verdict_eingeholt")),
}


def _verdict_badge(verdict: str) -> str:
    icon, label = _VERDICT_CONFIG.get(verdict, ("⚪", verdict))
    return f"{icon} {label}"


# ------------------------------------------------------------------
# Portfolio + Watchlist positions with stories
# ------------------------------------------------------------------

_all_positions = _positions_repo.get_all()  # Include watchlist positions
_eligible = [p for p in _all_positions if p.story]
_all_ids = [p.id for p in _eligible if p.id]

if not _eligible:
    st.info(t("consensus_gap.no_eligible"))
    st.stop()

# Load latest verdicts from DB
_current_verdicts = _analyses_repo.get_latest_bulk(_all_ids, agent="consensus_gap")

# ------------------------------------------------------------------
# Run analysis button
# ------------------------------------------------------------------

if not _skills:
    st.warning(t("consensus_gap.no_skills"))
else:
    _skill_options = {s.name: s for s in _skills}
    col_skill, col_btn = st.columns([3, 1])
    with col_skill:
        _sel_skill_name = st.selectbox(
            t("consensus_gap.skill_label"),
            options=list(_skill_options.keys()),
            key="_cgap_skill",
            disabled=_JOB["running"],
        )
    with col_btn:
        st.write("")
        st.write("")
        if st.button(
            t("consensus_gap.run_button"),
            type="primary",
            key="_cgap_run",
            use_container_width=True,
            disabled=_JOB["running"],
        ):
            _sel_skill = _skill_options[_sel_skill_name]
            _JOB["running"] = True
            _JOB["done"] = False
            _JOB["error"] = None
            _JOB["last_error"] = None
            t_bg = threading.Thread(
                target=_run_background,
                args=(_agent, _eligible, _sel_skill.name, _sel_skill.prompt, _analyses_repo, _JOB),
                daemon=True,
            )
            t_bg.start()
            st.rerun()

# Running indicator — auto-refresh every 5s
if _JOB["running"]:
    st.info(f"⏳ {t('consensus_gap.running')}", icon=":material/hourglass_top:")
    time.sleep(5)
    st.rerun()

# Done notification
if _JOB["done"]:
    if _JOB["error"]:
        st.error(f"❌ {_JOB['error']}")
    else:
        st.success(
            f"✅ {_JOB['count']} {t('consensus_gap.analysis_done')}",
            icon=":material/check_circle:",
        )
    _JOB["done"] = False
    _current_verdicts = _analyses_repo.get_latest_bulk(_all_ids, agent="consensus_gap")

if _JOB["last_error"] and not _JOB["running"]:
    st.error(f"❌ Letzter Lauf fehlgeschlagen: {_JOB['last_error']}")

st.divider()

# ------------------------------------------------------------------
# Position cards with current verdicts
# ------------------------------------------------------------------

st.subheader(t("consensus_gap.positions_header"))

_eligible_sorted = sorted(_eligible, key=lambda p: p.name.lower())

for _pos in _eligible_sorted:
    _analysis = _current_verdicts.get(_pos.id)
    _verdict = _analysis.verdict if _analysis else None
    _icon = _VERDICT_CONFIG.get(_verdict, ("⚪", ""))[0] if _verdict else "⚪"

    with st.container(border=True):
        _hc1, _hc2 = st.columns([5, 2])
        with _hc1:
            st.markdown(f"**{_icon} {_pos.name}**" + (f" · {_pos.ticker}" if _pos.ticker else ""))
            st.caption(f"{_pos.asset_class}" + (f" · {_pos.anlageart}" if _pos.anlageart else ""))
        with _hc2:
            if _verdict:
                st.markdown(_verdict_badge(_verdict))
                if _analysis and _analysis.created_at:
                    st.caption(_analysis.created_at.strftime("%d.%m.%Y"))
            else:
                st.caption(t("consensus_gap.not_yet_analyzed"))

        if _analysis and _analysis.summary:
            st.markdown(f"_{_analysis.summary}_")

        if _pos.story:
            with st.expander(t("consensus_gap.show_story")):
                st.markdown(_pos.story)

st.divider()

# ------------------------------------------------------------------
# Legend
# ------------------------------------------------------------------

with st.expander(t("consensus_gap.legend_header")):
    for verdict, (icon, label) in _VERDICT_CONFIG.items():
        st.markdown(f"**{icon} {label}** — {t(f'consensus_gap.legend_{verdict}')}")
