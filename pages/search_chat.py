"""
Search Chat — investment screening with Claude + web search.
"""

import asyncio

import streamlit as st

from core.i18n import t
from core.ui.verdicts import cloud_notice
from state import get_search_agent, get_skills_repo

st.set_page_config(page_title="Investment Search", page_icon="🔎", layout="wide")
st.title(f"🔎 {t('search_chat.title')}")
st.caption(t("search_chat.subtitle"))
agent = get_search_agent()
cloud_notice(agent.model, "claude")

# Load search skills from DB
search_skills = get_skills_repo().get_by_area("search")
skill_names = [s.name for s in search_skills] + [t("search_chat.custom_skill")]
_skill_map = {s.name: s for s in search_skills}

# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------

if "sc_session_id" not in st.session_state:
    st.session_state.sc_session_id = None

if "sc_proposals" not in st.session_state:
    st.session_state.sc_proposals = []

if "sc_prev_session_id" not in st.session_state:
    st.session_state.sc_prev_session_id = None

# ------------------------------------------------------------------
# Layout: left sidebar | right chat
# ------------------------------------------------------------------

col_sidebar, col_chat = st.columns([1, 2])

# ------------------------------------------------------------------
# Left: new search form + past sessions
# ------------------------------------------------------------------

with col_sidebar:
    st.subheader(t("search_chat.new_search"))

    with st.form("new_search_form"):
        query_input = st.text_input(
            t("search_chat.query_label"),
            placeholder=t("search_chat.query_placeholder"),
        ).strip()

        skill_choice = st.selectbox(t("search_chat.skill_label"), skill_names)

        custom_prompt = ""
        if skill_choice == t("search_chat.custom_skill"):
            custom_prompt = st.text_area(
                t("search_chat.custom_skill_label"),
                placeholder=t("search_chat.custom_skill_placeholder"),
                height=120,
            ).strip()

        submitted = st.form_submit_button(
            t("search_chat.start_button"), use_container_width=True
        )

    if submitted:
        if not query_input:
            st.error(t("search_chat.no_query_error"))
        elif skill_choice == t("search_chat.custom_skill") and not custom_prompt:
            st.error(t("search_chat.no_focus_error"))
        else:
            if skill_choice == t("search_chat.custom_skill"):
                resolved_prompt = custom_prompt
                resolved_skill_name = t("search_chat.custom_skill")
            else:
                selected_skill = _skill_map[skill_choice]
                resolved_prompt = selected_skill.prompt
                resolved_skill_name = selected_skill.name

            session = agent.start_session(
                query=query_input,
                skill_name=resolved_skill_name,
                skill_prompt=resolved_prompt,
            )
            st.session_state.sc_session_id = session.id

            initial_msg = (
                f"Please screen for investment opportunities matching this request: "
                f"**{query_input}**\n\nApply the screening strategy and return a ranked list."
            )
            with st.spinner(t("search_chat.thinking")):
                try:
                    response, proposals = asyncio.run(agent.chat(session.id, initial_msg))
                    st.session_state.sc_proposals = proposals
                except Exception as exc:
                    st.error(f"⚠️ {t('common.agent_error')}: {exc}")
            st.rerun()

    st.divider()
    st.subheader(t("search_chat.past_searches"))

    sessions = agent.list_sessions(limit=30)
    if not sessions:
        st.info(t("search_chat.no_searches"))
    else:
        for s in sessions:
            label = f"**{s.query[:40]}{'…' if len(s.query) > 40 else ''}** — {s.skill_name}"
            date_str = s.created_at.strftime("%d.%m.%Y")
            btn_label = f"{label}  \n{date_str}"
            active = st.session_state.sc_session_id == s.id
            if st.button(
                btn_label,
                key=f"sess_{s.id}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state.sc_session_id = s.id
                st.session_state.sc_proposals = []
                st.rerun()

# ------------------------------------------------------------------
# Right: chat interface
# ------------------------------------------------------------------

with col_chat:
    session_id = st.session_state.sc_session_id

    if session_id is None:
        st.info(t("search_chat.select_or_start"))
    else:
        session = agent.get_session(session_id)
        if session is None:
            st.warning(t("search_chat.session_not_found"))
            st.session_state.sc_session_id = None
        else:
            st.markdown(f"### {session.query}")
            st.caption(
                f"{t('search_chat.skill_caption')}: {session.skill_name} · "
                f"{t('search_chat.started_caption')}: "
                f"{session.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            messages = agent.get_messages(session_id)
            for msg in messages:
                role = "user" if msg.role == "user" else "assistant"
                with st.chat_message(role):
                    st.markdown(msg.content)
                    if role == "assistant":
                        st.caption(t("common.ai_disclaimer"))

            # Render proposal panel if there are proposals
            if st.session_state.sc_proposals:
                st.divider()
                st.subheader("📋 Watchlist-Vorschläge")
                st.caption("Claude empfiehlt diese Kandidaten — wähle aus, welche du übernehmen möchtest:")

                for i, p in enumerate(st.session_state.sc_proposals):
                    st.checkbox(
                        f"**{p['name']}** ({p['ticker']}) · {p['asset_class']}",
                        key=f"prop_check_{session_id}_{i}",
                    )
                    if p.get("notes"):
                        st.caption(p["notes"])

                if st.button("Zur Watchlist hinzufügen", type="primary", key=f"add_proposals_{session_id}"):
                    selected_proposals = [
                        st.session_state.sc_proposals[i]
                        for i in range(len(st.session_state.sc_proposals))
                        if st.session_state.get(f"prop_check_{session_id}_{i}", False)
                    ]
                    if selected_proposals:
                        for prop in selected_proposals:
                            try:
                                agent.add_from_proposal(session_id, prop)
                            except Exception as exc:
                                st.error(f"Error adding {prop['name']}: {exc}")
                        st.success(f"✅ {len(selected_proposals)} Position(en) hinzugefügt!", icon=":material/bookmark_added:")
                        st.session_state.sc_proposals = []
                        st.rerun()
                    else:
                        st.info("Bitte wähle mindestens eine Position aus.")

            if prompt := st.chat_input(t("search_chat.chat_placeholder")):
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner(t("search_chat.searching")):
                        try:
                            response, proposals = asyncio.run(agent.chat(session_id, prompt))
                            st.session_state.sc_proposals = proposals
                        except Exception as exc:
                            response = f"⚠️ {t('common.agent_error')}: {exc}"
                            st.session_state.sc_proposals = []
                    st.markdown(response)
                    st.caption(t("common.ai_disclaimer"))
                st.rerun()
