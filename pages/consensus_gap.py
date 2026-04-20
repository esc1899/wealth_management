"""
Konsens-Lücken-Analyse — Claude's Anlagestrategie, Säule 2.

Misst für jede Portfolio-Position den Abstand zwischen der eigenen These
und dem Markt-Konsens. Zeigt wo der Markt (noch) falsch liegt.
"""

import asyncio
import threading
import time

import streamlit as st

from core.i18n import t, current_language
from core.ui.verdicts import VERDICT_CONFIGS, verdict_badge, render_verdict_legend, cloud_notice
from state import (
    get_analyses_repo,
    get_consensus_gap_agent,
    get_skills_repo,
    get_portfolio_service,
    get_analysis_service,
)

st.set_page_config(
    page_title="Konsens-Lücken",
    page_icon="🎯",
    layout="wide",
)
st.title(f"🎯 {t('consensus_gap.title')}")
st.caption(t("consensus_gap.subtitle"))

_agent = get_consensus_gap_agent()
cloud_notice(_agent.model)

_analyses_repo = get_analyses_repo()
_portfolio_service = get_portfolio_service()
_analysis_service = get_analysis_service()
_skills = get_skills_repo().get_by_area("consensus_gap")

# ------------------------------------------------------------------
# Background job tracking (session_state — survives reruns)
# ------------------------------------------------------------------

if "_cgap_job" not in st.session_state:
    st.session_state["_cgap_job"] = {"running": False, "done": False, "count": 0, "error": None, "last_error": None}

_JOB = st.session_state["_cgap_job"]


def _run_background(agent, positions, skill_name, skill_prompt, language: str, job: dict):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(
            agent.analyze_portfolio(
                positions=positions,
                skill_name=skill_name,
                skill_prompt=skill_prompt,
                language=language,
            )
        )
        job.update({"running": False, "done": True, "count": len(results), "error": None})
    except Exception as exc:
        job.update({"running": False, "done": True, "count": 0, "error": str(exc), "last_error": str(exc)})
    finally:
        loop.close()


# Use shared verdict config
_VERDICT_CONFIG = VERDICT_CONFIGS["consensus_gap"]


# ------------------------------------------------------------------
# Portfolio + Watchlist positions with stories
# ------------------------------------------------------------------

_eligible = _portfolio_service.get_all_positions(
    include_portfolio=True, include_watchlist=True, require_story=True
)
_all_ids = [p.id for p in _eligible if p.id]

if not _eligible:
    st.info(t("consensus_gap.no_eligible"))
    st.stop()

# Load latest verdicts early (needed for pending filter)
_current_verdicts = _analyses_repo.get_latest_bulk(_all_ids, agent="consensus_gap")
_pending = [p for p in _eligible if p.id not in _current_verdicts]

if st.session_state.pop("_auto_run_consensus_gap", False) and _pending and not _JOB["running"] and _skills:
    _default_skill = next((s for s in _skills if "Standard" in s.name), _skills[0])
    _JOB.update({"running": True, "done": False, "error": None, "last_error": None})
    threading.Thread(
        target=_run_background,
        args=(_agent, _pending, _default_skill.name, _default_skill.prompt, current_language(), _JOB),
        daemon=True,
    ).start()
    st.rerun()

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
            disabled=_JOB["running"] or not _pending,
        ):
            _sel_skill = _skill_options[_sel_skill_name]
            _lang = current_language()
            _JOB["running"] = True
            _JOB["done"] = False
            _JOB["error"] = None
            _JOB["last_error"] = None
            t_bg = threading.Thread(
                target=_run_background,
                args=(_agent, _pending, _sel_skill.name, _sel_skill.prompt, _lang, _JOB),
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
    # Reload verdicts and pending after batch completes
    _current_verdicts = _analyses_repo.get_latest_bulk(_all_ids, agent="consensus_gap")
    _pending = [p for p in _eligible if p.id not in _current_verdicts]

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
                st.markdown(verdict_badge(_verdict, _VERDICT_CONFIG))
                if _analysis and _analysis.created_at:
                    st.caption(_analysis.created_at.strftime("%d.%m.%Y"))
            else:
                st.caption(t("consensus_gap.not_yet_analyzed"))

        if _analysis and _analysis.summary:
            st.markdown(f"_{_analysis.summary}_")

        if _pos.story:
            with st.expander(t("consensus_gap.show_story")):
                st.markdown(_pos.story)

        # Details footer with metadata
        if _analysis:
            with st.expander("Details"):
                st.caption(f"Agent: consensus_gap")
                st.caption(f"Model: {_agent.model}")
                if _analysis.created_at:
                    st.caption(f"Analysiert: {_analysis.created_at.strftime('%d.%m.%Y %H:%M')}")

st.divider()

# ------------------------------------------------------------------
# Legend
# ------------------------------------------------------------------

render_verdict_legend(_VERDICT_CONFIG)
