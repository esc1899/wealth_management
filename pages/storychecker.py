"""
Story Checker — checks whether investment theses are still intact.

Cloud ☁️ agent: only the investment thesis text (story) is sent to the API.
No quantities or purchase prices are exposed.
Uses built-in web search to find current news before assessing the thesis.
"""

import asyncio
import threading
import time

import streamlit as st

from core.i18n import t
from state import get_analyses_repo, get_positions_repo, get_storychecker_agent

st.set_page_config(page_title="Story Checker", page_icon="🔍", layout="wide")
st.title(f"🔍 {t('storychecker.title')}")
st.caption(t("storychecker.subtitle"))

agent = get_storychecker_agent()
analyses_repo = get_analyses_repo()
st.info(t("storychecker.cloud_notice").format(model=agent._llm.model), icon="ℹ️")

with st.expander(t("storychecker.what_is_this"), expanded=False):
    st.markdown(t("storychecker.explanation"))

# ------------------------------------------------------------------
# Load data
# ------------------------------------------------------------------

positions_with_story = [p for p in get_positions_repo().get_all() if p.story]

# ------------------------------------------------------------------
# Batch check — background job
# ------------------------------------------------------------------

if "_sc_batch_job" not in st.session_state:
    st.session_state["_sc_batch_job"] = {
        "running": False, "done": False, "count": 0, "errors": 0, "error": None, "last_error": None,
    }

_BATCH = st.session_state["_sc_batch_job"]


def _run_batch_background(ag, positions, job: dict):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(ag.batch_check_all(positions=positions))
        errors = sum(1 for _, err in results if err)
        job.update({"running": False, "done": True, "count": len(results), "errors": errors, "error": None})
    except Exception as exc:
        job.update({"running": False, "done": True, "count": 0, "errors": 0, "error": str(exc), "last_error": str(exc)})
    finally:
        loop.close()


if positions_with_story:
    with st.expander(t("storychecker.batch_header"), expanded=False):
        st.caption(t("storychecker.batch_caption").format(n=len(positions_with_story)))
        if st.button(
            t("storychecker.batch_button"),
            type="primary",
            key="_sc_batch_run",
            use_container_width=False,
            disabled=_BATCH["running"],
        ):
            _BATCH["running"] = True
            _BATCH["done"] = False
            _BATCH["error"] = None
            _BATCH["last_error"] = None
            threading.Thread(
                target=_run_batch_background,
                args=(agent, positions_with_story, _BATCH),
                daemon=True,
            ).start()
            st.rerun()

if _BATCH["running"]:
    st.info(f"⏳ {t('storychecker.batch_running')}", icon=":material/hourglass_top:")
    time.sleep(5)
    st.rerun()

if _BATCH["done"]:
    if _BATCH["error"]:
        st.error(f"❌ {_BATCH['error']}")
    else:
        msg = f"✅ {_BATCH['count']} {t('storychecker.batch_done')}"
        if _BATCH["errors"]:
            msg += f" ({_BATCH['errors']} {t('storychecker.batch_errors')})"
        st.success(msg, icon=":material/check_circle:")
    _BATCH["done"] = False
    st.rerun()

if _BATCH["last_error"] and not _BATCH["running"]:
    st.error(f"❌ Letzter Batch-Lauf fehlgeschlagen: {_BATCH['last_error']}")

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

        # Verdict history for selected position
        past_analyses = analyses_repo.get_for_position(selected_position.id, limit=5)
        if past_analyses:
            _VERDICT_ICON = {"intact": "🟢", "gemischt": "🟡", "gefaehrdet": "🔴", "unknown": "⚪"}
            with st.expander(t("storychecker.verdict_history"), expanded=False):
                for a in past_analyses:
                    icon = _VERDICT_ICON.get(a.verdict or "unknown", "⚪")
                    date_str = a.created_at.strftime("%d.%m.%Y")
                    skill_label = f" · {a.skill_name}" if a.skill_name else ""
                    st.markdown(f"{icon} **{date_str}**{skill_label}")
                    if a.summary:
                        st.caption(a.summary)

        if st.session_state.get("sc_start_error"):
            st.error(f"⚠️ {t('storychecker.error')}: {st.session_state.pop('sc_start_error')}")

        if submitted:
            with st.spinner(t("storychecker.thinking")):
                try:
                    session = agent.start_session(position=selected_position)
                    st.session_state["sc_session_id"] = session.id
                except Exception as exc:
                    st.session_state["sc_start_error"] = str(exc)
            st.rerun()

    st.divider()
    st.subheader(t("storychecker.past_checks"))

    sessions = agent.list_sessions(limit=30)
    if not sessions:
        st.info(t("storychecker.no_checks"))
    else:
        _VERDICT_ICON = {"intact": "🟢", "gemischt": "🟡", "gefaehrdet": "🔴"}
        for s in sessions:
            icon = _VERDICT_ICON.get(s.verdict or "", "⚪")
            date_str = s.created_at.strftime("%d.%m. %H:%M")
            skill_part = f" · {s.skill_name}" if s.skill_name else ""
            btn_label = f"{icon} **{s.position_name}**  \n{date_str}{skill_part}"
            active = st.session_state.get("sc_session_id") == s.id
            if st.button(
                btn_label,
                key=f"sc_sess_{s.id}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state["sc_session_id"] = s.id
                st.rerun()

# ------------------------------------------------------------------
# Right: chat interface
# ------------------------------------------------------------------

with col_right:
    session_id = st.session_state.get("sc_session_id")

    if session_id is None:
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
