"""
Fundamental Analyzer — in-depth analysis of individual positions via chat.

Cloud ☁️ agent: analyzes valuation, business quality, competitive position, risks.
Interactive chat interface for following up on specific questions.
"""

import asyncio
import logging
import threading
import time
from datetime import datetime

import streamlit as st

from core.i18n import t, current_language
from core.ui.verdicts import cloud_notice, verdict_icon, VERDICT_CONFIGS
from state import (
    get_analyses_repo,
    get_fundamental_analyzer_agent,
    get_fundamental_agent,
    get_portfolio_service,
)

st.set_page_config(page_title="Fundamental Analyzer", page_icon="📊", layout="wide")
st.title(f"📊 {t('fundamental.title')}")
st.caption(t("fundamental.subtitle"))

agent = get_fundamental_analyzer_agent()
batch_agent = get_fundamental_agent()
analyses_repo = get_analyses_repo()
portfolio_service = get_portfolio_service()
cloud_notice(agent.model)

_VERDICT_CONFIG = VERDICT_CONFIGS.get("fundamental_analyzer", {})

with st.expander(t("fundamental.how_to_use"), expanded=False):
    st.markdown(t("fundamental.how_to_use_text"))

# ------------------------------------------------------------------
# Load data
# ------------------------------------------------------------------

all_positions = portfolio_service.get_public_positions(
    include_portfolio=True, include_watchlist=True, require_ticker=True
)
positions_with_required_fields = [p for p in all_positions if p.name]

if not positions_with_required_fields:
    st.warning(t("fundamental.no_positions"))
    st.stop()

_all_ids = [p.id for p in positions_with_required_fields if p.id]
_current_verdicts = analyses_repo.get_latest_bulk(_all_ids, agent="fundamental")
_pending = [p for p in positions_with_required_fields if p.id not in _current_verdicts]

# ------------------------------------------------------------------
# Batch job tracking
# ------------------------------------------------------------------

if "_fa_batch_job" not in st.session_state:
    st.session_state["_fa_batch_job"] = {
        "running": False, "done": False, "count": 0, "errors": 0, "error": None, "last_error": None,
    }

_BATCH = st.session_state["_fa_batch_job"]


def _run_batch_background(positions, skill_name, skill_prompt, language: str, job: dict):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(
            batch_agent.analyze_portfolio(
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


# ------------------------------------------------------------------
# Batch section
# ------------------------------------------------------------------

with st.expander(t("fundamental.batch_header"), expanded=False):
    _only_pending = st.checkbox(
        t("fundamental.batch_only_pending"),
        value=True,
        key="_fa_only_pending",
    )
    _target_positions = _pending if _only_pending else positions_with_required_fields
    st.caption(
        t("fundamental.batch_caption").format(
            total=len(positions_with_required_fields),
            pending=len(_pending),
        )
    )
    st.write("**Bewertungs-Fokus:**")
    _skill_prompt = st.text_input(
        "z.B. 'Konzentriere dich auf Bewertungs-Metriken' oder 'Analysiere Geschäftsmodell'",
        value="",
        key="_fa_skill_prompt",
        disabled=_BATCH["running"],
    )

    if st.button(
        t("fundamental.batch_button"),
        type="primary",
        key="_fa_batch_run",
        use_container_width=False,
        disabled=_BATCH["running"] or not _target_positions,
    ):
        _lang = current_language()
        _BATCH["running"] = True
        _BATCH["done"] = False
        _BATCH["error"] = None
        _BATCH["last_error"] = None
        threading.Thread(
            target=_run_batch_background,
            args=(_target_positions, "fundamental_batch", _skill_prompt or "Allgemeine fundamentale Analyse", _lang, _BATCH),
            daemon=True,
        ).start()
        st.rerun()

if _BATCH["running"]:
    st.info(f"⏳ {t('fundamental.batch_running')}", icon=":material/hourglass_top:")
    time.sleep(5)
    st.rerun()

if _BATCH["done"]:
    if _BATCH["error"]:
        logger = logging.getLogger(__name__)
        logger.error("Batch error details: %s", _BATCH['error'])
        st.error("❌ Der Batch-Lauf ist fehlgeschlagen. Bitte versuchen Sie es später erneut.")
    else:
        msg = f"✅ {_BATCH['count']} {t('fundamental.batch_done')}"
        if _BATCH["errors"]:
            msg += f" ({_BATCH['errors']} {t('fundamental.batch_errors')})"
        st.success(msg, icon=":material/check_circle:")
    _BATCH["done"] = False
    st.rerun()

if _BATCH["last_error"] and not _BATCH["running"]:
    logger = logging.getLogger(__name__)
    logger.error("Last batch error details: %s", _BATCH['last_error'])
    st.error("❌ Letzter Batch-Lauf fehlgeschlagen. Bitte versuchen Sie es später erneut.")
    _BATCH["last_error"] = None

st.divider()

# ------------------------------------------------------------------
# Layout: left control panel | right chat
# ------------------------------------------------------------------

col_left, col_right = st.columns([0.8, 2.2], gap="medium")

# ------------------------------------------------------------------
# Left: position selection + past sessions
# ------------------------------------------------------------------

with col_left:
    st.subheader(t("fundamental.select_header"))

    pos_labels = [
        f"{p.name} ({p.ticker})" if p.ticker else p.name
        for p in positions_with_required_fields
    ]

    with st.form("new_analysis_form"):
        selected_idx = st.selectbox(
            t("fundamental.position_label"),
            options=range(len(positions_with_required_fields)),
            format_func=lambda i: pos_labels[i],
        )
        selected_position = positions_with_required_fields[selected_idx]

        submitted = st.form_submit_button(t("fundamental.start_button"), use_container_width=True, type="primary")

    # Show position details as reference
    if selected_position:
        with st.expander(f"📋 {selected_position.name}", expanded=False):
            if selected_position.ticker:
                st.caption(f"{t('fundamental.ticker_label')} {selected_position.ticker}")
            if selected_position.asset_class:
                st.caption(f"{t('fundamental.asset_class_label')} {selected_position.asset_class}")
            if selected_position.anlageart:
                st.caption(f"{t('fundamental.investment_type_label')} {selected_position.anlageart}")
            if selected_position.story:
                st.caption(t("fundamental.thesis_label"))
                st.markdown(selected_position.story)

    # Past analyses
    past_sessions = agent.list_sessions(limit=5)
    if past_sessions:
        with st.expander("📊 Letzte Analysen", expanded=False):
            for s in past_sessions:
                date_str = ""
                if s.messages and len(s.messages) > 0:
                    date_str = " · gerade eben"
                btn_label = f"📊 **{s.position_name}**{date_str}"
                active = st.session_state.get("fa_session_id") == s.id
                if st.button(
                    btn_label,
                    key=f"fa_sess_{s.id}",
                    use_container_width=True,
                    type="primary" if active else "secondary",
                ):
                    st.session_state["fa_session_id"] = s.id
                    st.rerun()

    if st.session_state.get("fa_start_error"):
        st.error(t("fundamental.start_error").format(error=st.session_state.pop('fa_start_error')))

    if submitted:
        with st.spinner(t("fundamental.starting")):
            try:
                # Clear old session if position changed
                current_session = agent.get_session(st.session_state.get("fa_session_id")) if st.session_state.get("fa_session_id") else None
                if current_session and current_session.position_id != selected_position.id:
                    st.session_state.pop("fa_session_id", None)

                session = agent.start_session(position=selected_position, language=current_language())
                st.session_state["fa_session_id"] = session.id
            except Exception as exc:
                st.session_state["fa_start_error"] = str(exc)
        st.rerun()

# ------------------------------------------------------------------
# Right: chat interface + batch results
# ------------------------------------------------------------------

with col_right:
    session_id = st.session_state.get("fa_session_id")

    if session_id is None:
        # Show batch results if available
        if _current_verdicts:
            st.subheader("Aktuelle Ergebnisse")
            _verdicts_with_pos = [
                (_p, _current_verdicts[_p.id])
                for _p in positions_with_required_fields
                if _p.id in _current_verdicts
            ]
            _verdicts_with_pos.sort(key=lambda x: x[1].created_at or datetime.min, reverse=True)

            for _pos, _analysis in _verdicts_with_pos:
                _verdict = _analysis.verdict or "unknown"
                _icon = verdict_icon(_verdict, _VERDICT_CONFIG)
                st.markdown(f"{_icon} **{_pos.name}**")
                if _analysis.created_at:
                    st.caption(_analysis.created_at.strftime("%d.%m.%Y %H:%M"))
                if _analysis.summary:
                    st.caption(_analysis.summary)

                # Inline history expander
                _history = [
                    a for a in analyses_repo.get_for_position(_pos.id, limit=20)
                    if a.agent == "fundamental"
                ]
                if len(_history) > 1:
                    with st.expander(f"{t('storychecker.verdict_history')} ({len(_history) - 1})", expanded=False):
                        for _h in _history[1:]:
                            _icon = verdict_icon(_h.verdict or "unknown", _VERDICT_CONFIG)
                            _date_str = _h.created_at.strftime("%d.%m.%Y") if _h.created_at else "—"
                            st.markdown(f"{_icon} **{_date_str}**")
                            if _h.summary:
                                st.caption(_h.summary)

                st.divider()
        else:
            st.info(t("fundamental.select_prompt"))
    else:
        session = agent.get_session(session_id)
        if session is None:
            st.warning(t("fundamental.session_not_found"))
            st.session_state.pop("fa_session_id", None)
        else:
            st.markdown(f"### {session.position_name}")
            if session.ticker:
                st.caption(f"`{session.ticker}`")

            messages = agent.get_messages(session_id)
            for msg in messages:
                if msg["role"] == "user":
                    # Skip the initial verbose system message (first user message)
                    if len(messages) > 1 and msg == messages[0]:
                        continue
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    if msg["role"] == "assistant":
                        st.caption(t("fundamental.web_search_info"))

            if prompt := st.chat_input(t("fundamental.chat_placeholder")):
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner(t("fundamental.analyzing")):
                        try:
                            response = agent.chat(session_id, prompt)
                        except Exception as exc:
                            response = t("fundamental.start_error").format(error=str(exc))
                    st.markdown(response)
                    st.caption(t("fundamental.web_search_info"))
                st.rerun()
