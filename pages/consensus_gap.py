"""
Konsens-Lücken-Analyse — Claude's Anlagestrategie, Säule 2.

Misst für jede Portfolio-Position den Abstand zwischen der eigenen These
und dem Markt-Konsens. Zeigt wo der Markt (noch) falsch liegt.
"""

import asyncio
import logging
import threading
import time

import streamlit as st

from core.i18n import t, current_language
from core.ui.verdicts import VERDICT_CONFIGS, verdict_icon, verdict_badge, render_verdict_legend, cloud_notice
from state import (
    get_analyses_repo,
    get_consensus_gap_agent,
    get_skills_repo,
    get_portfolio_service,
)

st.set_page_config(page_title="Konsens-Lücken", page_icon="🎯", layout="wide")
st.title(f"🎯 {t('consensus_gap.title')}")
st.caption(t("consensus_gap.subtitle"))

_agent = get_consensus_gap_agent()
cloud_notice(_agent.model)

_analyses_repo = get_analyses_repo()
_portfolio_service = get_portfolio_service()
_skills = get_skills_repo().get_by_area("consensus_gap")

_VERDICT_CONFIG = VERDICT_CONFIGS["consensus_gap"]

# ------------------------------------------------------------------
# Help section
# ------------------------------------------------------------------

with st.expander(t("consensus_gap.what_is_this"), expanded=False):
    st.markdown(t("consensus_gap.explanation"))

# ------------------------------------------------------------------
# Load positions
# ------------------------------------------------------------------

_eligible = _portfolio_service.get_public_positions(
    include_portfolio=True, include_watchlist=True, require_story=True
)
_all_ids = [p.id for p in _eligible if p.id]

if not _eligible:
    st.info(t("consensus_gap.no_eligible"))
    st.stop()

_current_verdicts = _analyses_repo.get_latest_bulk(_all_ids, agent="consensus_gap")
_pending = [p for p in _eligible if p.id not in _current_verdicts]

# ------------------------------------------------------------------
# Batch job tracking
# ------------------------------------------------------------------

if "_cgap_batch_job" not in st.session_state:
    st.session_state["_cgap_batch_job"] = {
        "running": False, "done": False, "count": 0, "errors": 0, "error": None, "last_error": None,
    }

_BATCH = st.session_state["_cgap_batch_job"]


def _run_batch_background(ag, positions, skill_name, skill_prompt, language: str, job: dict):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(
            ag.analyze_portfolio(
                positions=positions,
                skill_name=skill_name,
                skill_prompt=skill_prompt,
                language=language,
            )
        )
        errors = sum(1 for _, err in results if err)
        job.update({"running": False, "done": True, "count": len(results), "errors": errors, "error": None})
    except Exception as exc:
        job.update({"running": False, "done": True, "count": 0, "errors": 0, "error": str(exc), "last_error": str(exc)})
    finally:
        loop.close()


if st.session_state.pop("_auto_run_consensus_gap", False) and _pending and not _BATCH["running"] and _skills:
    _default_skill = next((s for s in _skills if "Standard" in s.name), _skills[0])
    _BATCH.update({"running": True, "done": False, "error": None, "last_error": None})
    threading.Thread(
        target=_run_batch_background,
        args=(_agent, _pending, _default_skill.name, _default_skill.prompt, current_language(), _BATCH),
        daemon=True,
    ).start()
    st.rerun()

# ------------------------------------------------------------------
# Batch section
# ------------------------------------------------------------------

if not _skills:
    st.warning(t("consensus_gap.no_skills"))
else:
    _skill_options = {s.name: s for s in _skills}

    with st.expander(t("consensus_gap.batch_header"), expanded=True):
        _only_pending = st.checkbox(
            t("consensus_gap.batch_only_pending"),
            value=True,
            key="_cgap_only_pending",
        )
        _target_positions = _pending if _only_pending else _eligible
        st.caption(
            t("consensus_gap.batch_caption").format(
                total=len(_eligible),
                pending=len(_pending),
            )
        )

        _sel_skill_name = st.selectbox(
            t("consensus_gap.skill_label"),
            options=list(_skill_options.keys()),
            key="_cgap_skill",
            disabled=_BATCH["running"],
        )

        if st.button(
            t("consensus_gap.batch_button"),
            type="primary",
            key="_cgap_batch_run",
            use_container_width=False,
            disabled=_BATCH["running"] or not _target_positions,
        ):
            _sel_skill = _skill_options[_sel_skill_name]
            _lang = current_language()
            _BATCH.update({"running": True, "done": False, "error": None, "last_error": None})
            threading.Thread(
                target=_run_batch_background,
                args=(_agent, _target_positions, _sel_skill.name, _sel_skill.prompt, _lang, _BATCH),
                daemon=True,
            ).start()
            st.rerun()

if _BATCH["running"]:
    st.info(f"⏳ {t('consensus_gap.batch_running')}", icon=":material/hourglass_top:")
    time.sleep(5)
    st.rerun()

if _BATCH["done"]:
    if _BATCH["error"]:
        logger = logging.getLogger(__name__)
        logger.error("Batch error: %s", _BATCH["error"])
        st.error("❌ Der Batch-Lauf ist fehlgeschlagen. Bitte versuchen Sie es später erneut.")
    else:
        msg = f"✅ {_BATCH['count']} {t('consensus_gap.batch_done')}"
        if _BATCH["errors"]:
            msg += f" ({_BATCH['errors']} {t('consensus_gap.batch_errors')})"
        st.success(msg, icon=":material/check_circle:")
    _BATCH["done"] = False
    st.rerun()

if _BATCH["last_error"] and not _BATCH["running"]:
    logger = logging.getLogger(__name__)
    logger.error("Last batch error: %s", _BATCH["last_error"])
    st.error("❌ Letzter Batch-Lauf fehlgeschlagen. Bitte versuchen Sie es später erneut.")

st.divider()

# ------------------------------------------------------------------
# Layout: left selector + list | right detail view
# ------------------------------------------------------------------

col_left, col_right = st.columns([0.8, 2.2], gap="medium")

_eligible_sorted = sorted(_eligible, key=lambda p: p.name.lower())
pos_labels = [
    f"{p.name} ({p.ticker})" if p.ticker else p.name
    for p in _eligible_sorted
]

# ------------------------------------------------------------------
# Left: position selector + single-run + past verdict list
# ------------------------------------------------------------------

with col_left:
    st.subheader(t("storychecker.new_check"))

    if not _skills:
        st.warning(t("consensus_gap.no_skills"))
    else:
        with st.form("cgap_single_form"):
            _sel_idx = st.selectbox(
                t("storychecker.pick_position"),
                options=range(len(_eligible_sorted)),
                format_func=lambda i: pos_labels[i],
            )
            _sel_pos = _eligible_sorted[_sel_idx]
            _single_skill_name = st.selectbox(
                t("consensus_gap.skill_label"),
                options=list(_skill_options.keys()),
                key="_cgap_single_skill",
            )
            _single_submitted = st.form_submit_button(
                t("consensus_gap.run_button"),
                use_container_width=True,
                type="primary",
            )

        if _sel_pos.story:
            with st.expander(t("consensus_gap.show_story"), expanded=False):
                st.markdown(_sel_pos.story)

        if st.session_state.get("_cgap_single_error"):
            logger = logging.getLogger(__name__)
            logger.error("Single analysis error: %s", st.session_state["_cgap_single_error"])
            st.error("⚠️ Die Analyse konnte nicht gestartet werden.")
            del st.session_state["_cgap_single_error"]

        if _single_submitted:
            with st.spinner(t("storychecker.thinking")):
                _single_skill = _skill_options[_single_skill_name]
                try:
                    _loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(_loop)
                    try:
                        _loop.run_until_complete(
                            _agent.analyze_portfolio(
                                positions=[_sel_pos],
                                skill_name=_single_skill.name,
                                skill_prompt=_single_skill.prompt,
                                language=current_language(),
                            )
                        )
                    finally:
                        _loop.close()
                    st.session_state["cgap_selected_id"] = _sel_pos.id
                except Exception as exc:
                    st.session_state["_cgap_single_error"] = str(exc)
            st.rerun()

        st.divider()
        st.subheader(t("storychecker.past_checks"))

        _analyzed = [p for p in _eligible_sorted if p.id in _current_verdicts]
        if not _analyzed:
            st.info(t("storychecker.no_checks"))
        else:
            for _p in _analyzed:
                _a = _current_verdicts[_p.id]
                _icon = verdict_icon(_a.verdict or "unknown", _VERDICT_CONFIG)
                _date_str = _a.created_at.strftime("%d.%m. %H:%M") if _a.created_at else ""
                _active = st.session_state.get("cgap_selected_id") == _p.id
                if st.button(
                    f"{_icon} **{_p.name}**  \n{_date_str}",
                    key=f"cgap_pos_{_p.id}",
                    use_container_width=True,
                    type="primary" if _active else "secondary",
                ):
                    st.session_state["cgap_selected_id"] = _p.id
                    st.rerun()

# ------------------------------------------------------------------
# Right: detail view for selected position
# ------------------------------------------------------------------

with col_right:
    _sel_id = st.session_state.get("cgap_selected_id")

    if _sel_id is None:
        st.info(t("storychecker.select_to_start"))
    else:
        _detail_pos = next((p for p in _eligible if p.id == _sel_id), None)
        if _detail_pos is None:
            st.session_state.pop("cgap_selected_id", None)
        else:
            _latest = _current_verdicts.get(_sel_id) or _analyses_repo.get_latest(_sel_id, agent="consensus_gap")

            st.markdown(f"### {_detail_pos.name}")
            if _detail_pos.ticker:
                st.caption(f"`{_detail_pos.ticker}`")

            if _latest:
                st.markdown(verdict_badge(_latest.verdict or "unknown", _VERDICT_CONFIG))
                if _latest.created_at:
                    st.caption(_latest.created_at.strftime("%d.%m.%Y %H:%M"))
                if _latest.summary:
                    st.markdown(_latest.summary)
            else:
                st.caption(t("consensus_gap.not_yet_analyzed"))

            # Verdict history
            _history = [
                a for a in _analyses_repo.get_for_position(_sel_id, limit=20)
                if a.agent == "consensus_gap"
            ]
            if len(_history) > 1:
                with st.expander(t("storychecker.verdict_history"), expanded=False):
                    for _a in _history[1:]:  # skip the latest (already shown)
                        _icon = verdict_icon(_a.verdict or "unknown", _VERDICT_CONFIG)
                        _date_str = _a.created_at.strftime("%d.%m.%Y") if _a.created_at else "—"
                        st.markdown(f"{_icon} **{_date_str}**")
                        if _a.summary:
                            st.caption(_a.summary)

st.divider()
render_verdict_legend(_VERDICT_CONFIG)
