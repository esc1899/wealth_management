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
from core.ui.verdicts import VERDICT_CONFIGS, verdict_icon, cloud_notice
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
    with st.expander(t("consensus_gap.batch_header"), expanded=False):
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

        _skill_options = {s.name: s for s in _skills}
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
            _BATCH["running"] = True
            _BATCH["done"] = False
            _BATCH["error"] = None
            _BATCH["last_error"] = None
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
        logger.error("Batch error details: %s", _BATCH['error'])
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
    logger.error("Last batch error details: %s", _BATCH['last_error'])
    st.error("❌ Letzter Batch-Lauf fehlgeschlagen. Bitte versuchen Sie es später erneut.")

st.divider()

# ------------------------------------------------------------------
# Layout: left current results | right older tests
# ------------------------------------------------------------------

col_left, col_right = st.columns([0.8, 2.2], gap="medium")

# ------------------------------------------------------------------
# Left: current verdicts summary
# ------------------------------------------------------------------

with col_left:
    st.subheader(t("consensus_gap.positions_header"))

    _eligible_sorted = sorted(_eligible, key=lambda p: p.name.lower())

    for _pos in _eligible_sorted:
        _analysis = _current_verdicts.get(_pos.id)
        _verdict = _analysis.verdict if _analysis else None
        _icon = verdict_icon(_verdict or "unknown", _VERDICT_CONFIG)

        with st.container(border=True):
            st.markdown(f"{_icon} **{_pos.name}**" + (f" · {_pos.ticker}" if _pos.ticker else ""))
            st.caption(f"{_pos.asset_class}" + (f" · {_pos.anlageart}" if _pos.anlageart else ""))

            if _verdict:
                if _analysis and _analysis.created_at:
                    st.caption(_analysis.created_at.strftime("%d.%m.%Y"))
                if _analysis and _analysis.summary:
                    st.caption(_analysis.summary)
            else:
                st.caption(t("consensus_gap.not_yet_analyzed"))

# ------------------------------------------------------------------
# Right: older analyses per position
# ------------------------------------------------------------------

with col_right:
    st.subheader("Ältere Tests")

    for _pos in _eligible_sorted:
        _past_analyses = _analyses_repo.get_for_position(_pos.id, agent="consensus_gap", limit=5)
        if _past_analyses:
            with st.expander(f"📊 {_pos.name}", expanded=False):
                for _a in _past_analyses:
                    _icon = verdict_icon(_a.verdict or "unknown", _VERDICT_CONFIG)
                    _date_str = _a.created_at.strftime("%d.%m.%Y") if _a.created_at else "—"
                    st.markdown(f"{_icon} **{_date_str}**")
                    if _a.summary:
                        st.caption(_a.summary)

st.divider()

# ------------------------------------------------------------------
# Legend
# ------------------------------------------------------------------

st.subheader(t("consensus_gap.legend_header"))
for _verdict_key in ["verdict_waechst", "verdict_stabil", "verdict_schliesst", "verdict_eingeholt"]:
    _icon = verdict_icon(_verdict_key, _VERDICT_CONFIG)
    _label = t(f"consensus_gap.{_verdict_key}")
    _desc = t(f"consensus_gap.legend_{_verdict_key.replace('verdict_', '')}")
    st.markdown(f"{_icon} **{_label}**: {_desc}")
