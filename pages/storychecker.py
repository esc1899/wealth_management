"""
Story Checker — checks whether investment theses are still intact.

Cloud ☁️ agent: only the investment thesis text (story) is sent to the API.
No quantities or purchase prices are exposed.
Uses built-in web search to find current news before assessing the thesis.
"""

import streamlit as st

from core.i18n import t
from state import get_analyses_repo, get_positions_repo, get_skills_repo, get_storychecker_agent

st.set_page_config(page_title="Story Checker", page_icon="🔍", layout="wide")
st.title(f"🔍 {t('storychecker.title')}")
st.caption(t("storychecker.subtitle"))

agent = get_storychecker_agent()
analyses_repo = get_analyses_repo()
st.info(t("storychecker.cloud_notice").format(model=agent._llm.model), icon="ℹ️")

with st.expander(t("storychecker.what_is_this"), expanded=True):
    st.markdown(t("storychecker.explanation"))

# ------------------------------------------------------------------
# Load data
# ------------------------------------------------------------------

positions_with_story = [p for p in get_positions_repo().get_all() if p.story]
storychecker_skills = get_skills_repo().get_by_area("storychecker")
_skill_map = {s.name: s for s in storychecker_skills}

# ------------------------------------------------------------------
# Layout: left control panel | right chat
# ------------------------------------------------------------------

col_left, col_right = st.columns([1, 2])

# ------------------------------------------------------------------
# Left: new check form + past sessions
# ------------------------------------------------------------------

with col_left:
    st.subheader(t("storychecker.new_check"))

    if not positions_with_story:
        st.warning(t("storychecker.no_stories"))
        st.caption(t("storychecker.no_stories_hint"))
    elif not storychecker_skills:
        st.warning(t("storychecker.no_skills"))
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

            # Prefer the skill stored on the position; fall back to first skill
            default_skill_name = selected_position.story_skill
            skill_names = [s.name for s in storychecker_skills]
            default_idx = skill_names.index(default_skill_name) if default_skill_name in skill_names else 0

            selected_skill_name = st.selectbox(
                t("storychecker.pick_skill"),
                options=skill_names,
                index=default_idx,
            )

            submitted = st.form_submit_button(
                t("storychecker.run_button"), use_container_width=True, type="primary"
            )

        # Show stored story as reference
        if selected_position.story:
            with st.expander(t("storychecker.show_story"), expanded=False):
                st.markdown(selected_position.story)
                if selected_position.story_skill:
                    st.caption(f"Anlage-Idee: {selected_position.story_skill}")

        # Verdict history for selected position
        past_analyses = analyses_repo.get_for_position(selected_position.id, limit=5)
        if past_analyses:
            _VERDICT_ICON = {"intact": "🟢", "gemischt": "🟡", "gefaehrdet": "🔴", "unknown": "⚪"}
            with st.expander(t("storychecker.verdict_history"), expanded=False):
                for a in past_analyses:
                    icon = _VERDICT_ICON.get(a.verdict or "unknown", "⚪")
                    date_str = a.created_at.strftime("%d.%m.%Y")
                    st.markdown(f"{icon} **{date_str}** · {a.skill_name}")
                    if a.summary:
                        st.caption(a.summary)

        if submitted:
            skill = _skill_map.get(selected_skill_name)
            if skill:
                with st.spinner(t("storychecker.thinking")):
                    try:
                        session = agent.start_session(
                            position=selected_position,
                            skill_name=skill.name,
                            skill_prompt=skill.prompt,
                        )
                        st.session_state["sc_session_id"] = session.id
                    except Exception as exc:
                        st.error(f"⚠️ {t('storychecker.error')}: {exc}")
                st.rerun()

    st.divider()
    st.subheader(t("storychecker.past_checks"))

    sessions = agent.list_sessions(limit=30)
    if not sessions:
        st.info(t("storychecker.no_checks"))
    else:
        for s in sessions:
            label = f"**{s.position_name}** — {s.skill_name}"
            date_str = s.created_at.strftime("%d.%m.%Y")
            btn_label = f"{label}  \n{date_str}"
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
            st.caption(
                f"{t('storychecker.skill_caption')}: {session.skill_name} · "
                f"{t('storychecker.started_caption')}: "
                f"{session.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

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
