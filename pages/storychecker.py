"""
Story Checker — checks whether investment theses are still intact.

Cloud ☁️ agent: only the investment thesis text (story) is sent to the API.
No quantities or purchase prices are exposed.
Uses built-in web search to find current news before assessing the thesis.
"""

import asyncio
import threading
import time
from datetime import datetime

import streamlit as st

from core.i18n import t, current_language
from core.ui.verdicts import VERDICT_CONFIGS, verdict_icon, cloud_notice
from state import get_analyses_repo, get_positions_repo, get_storychecker_agent

st.set_page_config(page_title="Story Checker", page_icon="🔍", layout="wide")
st.title(f"🔍 {t('storychecker.title')}")
st.caption(t("storychecker.subtitle"))

agent = get_storychecker_agent()
analyses_repo = get_analyses_repo()
cloud_notice(agent.model)

# Use shared verdict config
_VERDICT_CONFIG = VERDICT_CONFIGS["storychecker"]

with st.expander(t("storychecker.what_is_this"), expanded=False):
    st.markdown(t("storychecker.explanation"))

# ------------------------------------------------------------------
# Load data
# ------------------------------------------------------------------

positions_with_story = [p for p in get_positions_repo().get_all() if p.story]

# Filter to positions without an existing verdict (pending only)
_sc_existing = analyses_repo.get_latest_bulk(
    [p.id for p in positions_with_story if p.id], agent="storychecker"
)
pending_positions = [p for p in positions_with_story if p.id not in _sc_existing]

# ------------------------------------------------------------------
# Batch check — background job
# ------------------------------------------------------------------

if "_sc_batch_job" not in st.session_state:
    st.session_state["_sc_batch_job"] = {
        "running": False, "done": False, "count": 0, "errors": 0, "error": None, "last_error": None,
    }

_BATCH = st.session_state["_sc_batch_job"]


def _run_batch_background(ag, positions, language: str, job: dict):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(ag.batch_check_all(positions=positions, language=language))
        errors = sum(1 for _, err in results if err)
        job.update({"running": False, "done": True, "count": len(results), "errors": errors, "error": None})
    except Exception as exc:
        job.update({"running": False, "done": True, "count": 0, "errors": 0, "error": str(exc), "last_error": str(exc)})
    finally:
        loop.close()


if st.session_state.pop("_auto_run_storychecker", False) and pending_positions and not _BATCH["running"]:
    _BATCH.update({"running": True, "done": False, "error": None, "last_error": None})
    threading.Thread(
        target=_run_batch_background,
        args=(agent, pending_positions, current_language(), _BATCH),
        daemon=True,
    ).start()
    st.rerun()

if positions_with_story:
    with st.expander(t("storychecker.batch_header"), expanded=False):
        only_pending = st.checkbox(
            t("storychecker.batch_only_pending"),
            value=True,
            key="_sc_only_pending",
        )
        target_positions = pending_positions if only_pending else positions_with_story
        st.caption(
            t("storychecker.batch_caption_v2").format(
                total=len(positions_with_story),
                pending=len(pending_positions),
            )
        )
        if st.button(
            t("storychecker.batch_button"),
            type="primary",
            key="_sc_batch_run",
            use_container_width=False,
            disabled=_BATCH["running"] or not target_positions,
        ):
            _lang = current_language()
            _BATCH["running"] = True
            _BATCH["done"] = False
            _BATCH["error"] = None
            _BATCH["last_error"] = None
            threading.Thread(
                target=_run_batch_background,
                args=(agent, target_positions, _lang, _BATCH),
                daemon=True,
            ).start()
            st.rerun()

if _BATCH["running"]:
    st.info(f"⏳ {t('storychecker.batch_running')}", icon=":material/hourglass_top:")
    time.sleep(5)
    st.rerun()

if _BATCH["done"]:
    if _BATCH["error"]:
        # Log detailed error, show safe summary to user
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Batch error details: %s", _BATCH['error'])
        st.error("❌ Der Batch-Lauf ist fehlgeschlagen. Bitte versuchen Sie es später erneut.")
    else:
        msg = f"✅ {_BATCH['count']} {t('storychecker.batch_done')}"
        if _BATCH["errors"]:
            msg += f" ({_BATCH['errors']} {t('storychecker.batch_errors')})"
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
# Left: new check form + past sessions
# ------------------------------------------------------------------

with col_left:
    st.subheader(t("storychecker.new_check"))

    if not positions_with_story:
        st.warning(t("storychecker.no_stories"))
        st.caption(t("storychecker.no_stories_hint"))
    else:
        pos_labels = [
            f"{p.name} ({p.ticker})" if p.ticker else p.name
            for p in positions_with_story
        ]

        with st.form("new_check_form"):
            selected_idx = st.selectbox(
                t("storychecker.pick_position"),
                options=range(len(positions_with_story)),
                format_func=lambda i: pos_labels[i],
            )
            selected_position = positions_with_story[selected_idx]

            submitted = st.form_submit_button(
                t("storychecker.run_button"), use_container_width=True, type="primary"
            )

        # Show stored story as reference
        if selected_position.story:
            with st.expander(t("storychecker.show_story"), expanded=False):
                st.markdown(selected_position.story)
                if selected_position.story_skill:
                    st.caption(f"{t('storychecker.skill_caption')}: {selected_position.story_skill}")

        if st.session_state.get("sc_start_error"):
            error_details = st.session_state.pop('sc_start_error')
            logger = logging.getLogger(__name__)
            logger.error("Story checker start error: %s", error_details)
            st.error(f"⚠️ {t('storychecker.error')} Die Story-Analyse konnte nicht gestartet werden.")

        if submitted:
            with st.spinner(t("storychecker.thinking")):
                try:
                    # Clear old session if position changed
                    current_session = agent.get_session(st.session_state.get("sc_session_id")) if st.session_state.get("sc_session_id") else None
                    if current_session and current_session.position_id != selected_position.id:
                        st.session_state.pop("sc_session_id", None)

                    session = agent.start_session(position=selected_position, language=current_language())
                    st.session_state["sc_session_id"] = session.id
                except Exception as exc:
                    st.session_state["sc_start_error"] = str(exc)
            st.rerun()

# ------------------------------------------------------------------
# Right: chat interface
# ------------------------------------------------------------------

with col_right:
    session_id = st.session_state.get("sc_session_id")

    if session_id is None:
        if _sc_existing:
            st.subheader("Aktuelle Ergebnisse")
            _verdicts_with_pos = [
                (_p, _sc_existing[_p.id])
                for _p in positions_with_story
                if _p.id in _sc_existing
            ]
            _verdicts_with_pos.sort(key=lambda x: x[1].created_at or datetime.min, reverse=True)
            for _p, _a in _verdicts_with_pos:
                _icon = verdict_icon(_a.verdict or "unknown", _VERDICT_CONFIG)
                st.markdown(f"{_icon} **{_p.name}**")
                if _a.created_at:
                    st.caption(_a.created_at.strftime("%d.%m.%Y %H:%M"))
                if _a.summary:
                    st.caption(_a.summary)

                # Full analysis text from session
                if _a.session_id:
                    _messages = agent.get_messages(_a.session_id)
                    _assistant_msgs = [m for m in _messages if m.role == "assistant"]
                    if _assistant_msgs:
                        with st.expander("▼ Vollständige Analyse", expanded=True):
                            st.markdown(_assistant_msgs[0].content)

                # Inline history expander
                _history = [
                    a for a in analyses_repo.get_for_position(_p.id, limit=20)
                    if a.agent == "storychecker"
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
            st.info(t("storychecker.select_to_start"))
    else:
        session = agent.get_session(session_id)
        if session is None:
            st.warning(t("storychecker.session_not_found"))
            st.session_state.pop("sc_session_id", None)
        else:
            st.markdown(f"### {session.position_name}")
            caption = session.created_at.strftime("%d.%m.%Y %H:%M")
            if session.skill_name:
                caption = f"{t('storychecker.skill_caption')}: {session.skill_name} · {caption}"
            st.caption(caption)

            messages = agent.get_messages(session_id)
            for msg in messages:
                if msg.role == "user":
                    # Skip the auto-generated first user message (too verbose to show)
                    continue
                with st.chat_message("assistant"):
                    st.markdown(msg.content)
                    st.caption(t("common.ai_disclaimer"))

            if prompt := st.chat_input(t("storychecker.chat_placeholder")):
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner(t("storychecker.thinking_followup")):
                        try:
                            response = agent.chat(session_id, prompt)
                        except Exception as exc:
                            response = f"⚠️ {t('common.agent_error')}: {exc}"
                    st.markdown(response)
                    st.caption(t("common.ai_disclaimer"))
                st.rerun()
