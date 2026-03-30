"""
Rebalance Chat — conversational portfolio analysis using local Ollama LLM.
"""

import asyncio

import streamlit as st

from config import config
from core.health import is_local_url
from core.i18n import t
from state import get_rebalance_agent, get_rebalance_repo, get_skills_repo

st.set_page_config(page_title="Invest / Rebalance", page_icon="⚖️", layout="wide")
st.title(f"⚖️ {t('rebalance_chat.title')}")
st.caption(t("rebalance_chat.subtitle"))

agent = get_rebalance_agent()

if is_local_url(config.OLLAMA_HOST):
    st.info(t("rebalance_chat.private_notice").format(model=agent._llm.model), icon="🔒")
else:
    st.warning(t("rebalance_chat.remote_notice").format(host=config.OLLAMA_HOST, model=agent._llm.model), icon="⚠️")
repo = get_rebalance_repo()

if "rb_session_id" not in st.session_state:
    st.session_state.rb_session_id = None

# ------------------------------------------------------------------
# Layout: left sidebar | right chat
# ------------------------------------------------------------------

col_sidebar, col_chat = st.columns([1, 2])

# ------------------------------------------------------------------
# Left: new session form + past sessions
# ------------------------------------------------------------------

with col_sidebar:
    st.subheader(t("rebalance_chat.new_session"))

    rebalance_skills = get_skills_repo().get_by_area("rebalance")

    with st.form("new_rebalance_form"):
        if rebalance_skills:
            skill_names = [s.name for s in rebalance_skills]
            _skill_map = {s.name: s for s in rebalance_skills}
            skill_choice = st.selectbox(t("rebalance_chat.skill_label"), skill_names)
        else:
            st.warning(t("rebalance_chat.no_skill"))
            skill_choice = None

        context_input = st.text_input(
            t("rebalance_chat.context_label"),
            placeholder=t("rebalance_chat.context_placeholder"),
        ).strip()

        submitted = st.form_submit_button(
            t("rebalance_chat.start_button"), use_container_width=True
        )

    if submitted and skill_choice:
        selected_skill = _skill_map[skill_choice]
        with st.spinner(t("rebalance_chat.thinking")):
            try:
                session, _ = asyncio.run(
                    agent.start_session(
                        skill_name=selected_skill.name,
                        skill_prompt=selected_skill.prompt,
                        user_context=context_input,
                        repo=repo,
                    )
                )
                st.session_state.rb_session_id = session.id
            except Exception as exc:
                st.error(f"⚠️ {t('common.agent_error')}: {exc}")
        st.rerun()

    st.divider()
    st.subheader(t("rebalance_chat.past_sessions"))

    sessions = repo.list_sessions(limit=30)
    if not sessions:
        st.info(t("rebalance_chat.no_sessions"))
    else:
        for s in sessions:
            date_str = s.created_at.strftime("%d.%m.%Y %H:%M")
            label = f"**{s.skill_name}**  \n{date_str}"
            active = st.session_state.rb_session_id == s.id
            col_btn, col_del = st.columns([5, 1])
            if col_btn.button(
                label,
                key=f"rb_sess_{s.id}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state.rb_session_id = s.id
                st.rerun()
            if col_del.button("🗑", key=f"rb_del_{s.id}"):
                repo.delete_session(s.id)
                if st.session_state.rb_session_id == s.id:
                    st.session_state.rb_session_id = None
                st.rerun()

# ------------------------------------------------------------------
# Right: chat interface
# ------------------------------------------------------------------

with col_chat:
    session_id = st.session_state.rb_session_id

    if session_id is None:
        st.info(t("rebalance_chat.select_or_start"))
    else:
        session = repo.get_session(session_id)
        if session is None:
            st.warning(t("rebalance_chat.session_not_found"))
            st.session_state.rb_session_id = None
        else:
            st.markdown(f"### {session.skill_name}")
            st.caption(session.created_at.strftime("%d.%m.%Y %H:%M"))

            messages = repo.get_messages(session_id)
            for msg in messages:
                role = "user" if msg.role == "user" else "assistant"
                with st.chat_message(role):
                    st.markdown(msg.content)
                    if role == "assistant":
                        st.caption(t("common.ai_disclaimer"))

            if prompt := st.chat_input(t("rebalance_chat.chat_placeholder")):
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner(t("rebalance_chat.thinking")):
                        try:
                            response = asyncio.run(
                                agent.chat(session_id, prompt, repo)
                            )
                        except Exception as exc:
                            response = f"⚠️ {t('common.agent_error')}: {exc}"
                    st.markdown(response)
                    st.caption(t("common.ai_disclaimer"))
                st.rerun()
