"""
Research Chat — chat-based stock analysis with Claude + web search.
"""

import asyncio

import streamlit as st

from core.i18n import t, current_language
from core.strategy_config import CUSTOM_STRATEGY_NAME
from core.ui.verdicts import cloud_notice
from state import get_research_agent, get_skills_repo

st.set_page_config(page_title="Research Chat", page_icon="🔍", layout="wide")
st.title(f"🔍 {t('research_chat.title')}")
st.caption(t("research_chat.subtitle"))
agent = get_research_agent()
cloud_notice(agent.model, "claude")

# Load research skills from DB; fall back gracefully if none exist
research_skills = get_skills_repo().get_by_area("research")
skill_names = [s.name for s in research_skills] + [t("research_chat.custom_strategy")]
# Build lookup: name -> skill
_skill_map = {s.name: s for s in research_skills}

# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------

if "rc_session_id" not in st.session_state:
    st.session_state.rc_session_id = None

if "rc_proposals" not in st.session_state:
    st.session_state.rc_proposals = []

# ------------------------------------------------------------------
# Layout: left sidebar (sessions + new) | right chat
# ------------------------------------------------------------------

col_sidebar, col_chat = st.columns([1, 2])

# ------------------------------------------------------------------
# Left: new session form + past sessions
# ------------------------------------------------------------------

with col_sidebar:
    st.subheader(t("research_chat.new_session"))

    with st.form("new_session_form"):
        company_input = st.text_input(
            t("research_chat.company_label"),
            placeholder=t("research_chat.company_placeholder"),
        ).strip()

        strategy_choice = st.selectbox(t("research_chat.strategy_label"), skill_names)

        custom_prompt = ""
        if strategy_choice == t("research_chat.custom_strategy"):
            custom_prompt = st.text_area(
                t("research_chat.custom_strategy_label"),
                placeholder=t("research_chat.custom_strategy_placeholder"),
                height=120,
            ).strip()

        submitted = st.form_submit_button(t("research_chat.start_button"), use_container_width=True)

    if submitted:
        if not company_input:
            st.error(t("research_chat.no_company_error"))
        elif strategy_choice == t("research_chat.custom_strategy") and not custom_prompt:
            st.error(t("research_chat.no_focus_error"))
        else:
            # Resolve prompt: use DB skill prompt or custom free-text prompt
            if strategy_choice == t("research_chat.custom_strategy"):
                resolved_prompt = custom_prompt or None
                resolved_strategy_name = CUSTOM_STRATEGY_NAME
            else:
                selected_skill = _skill_map[strategy_choice]
                resolved_prompt = selected_skill.prompt
                resolved_strategy_name = selected_skill.name

            # Use input as ticker placeholder; agent will resolve it if it's a name
            session = agent.start_session(
                ticker=company_input.upper(),
                strategy_name=resolved_strategy_name,
                company_name=None,
                custom_prompt=resolved_prompt,
            )
            st.session_state.rc_session_id = session.id
            initial_msg = (
                f"Bitte analysiere '{company_input}'. Falls das kein Ticker-Symbol ist, "
                f"finde zunächst das korrekte Ticker-Symbol und gib mir dann eine "
                f"strukturierte Bewertung gemäß der Analysestrategie."
            )
            with st.spinner(t("research_chat.thinking")):
                try:
                    response, proposals = asyncio.run(agent.chat(session.id, initial_msg, language=current_language()))
                    st.session_state.rc_proposals = proposals
                except Exception as exc:
                    st.error(f"⚠️ {t('common.agent_error')}: {exc}")
            st.rerun()

    st.divider()
    st.subheader(t("research_chat.past_sessions"))

    sessions = agent.list_sessions(limit=30)
    if not sessions:
        st.info(t("research_chat.no_sessions"))
    else:
        for s in sessions:
            label = f"**{s.ticker}** — {s.strategy_name}"
            date_str = s.created_at.strftime("%d.%m.%Y")
            if s.company_name:
                label = f"**{s.ticker}** ({s.company_name}) — {s.strategy_name}"
            btn_label = f"{label}  \n{date_str}"
            active = st.session_state.rc_session_id == s.id
            btn_type = "primary" if active else "secondary"
            if st.button(btn_label, key=f"sess_{s.id}", use_container_width=True, type=btn_type):
                st.session_state.rc_session_id = s.id
                st.session_state.rc_proposals = []
                st.rerun()

# ------------------------------------------------------------------
# Right: chat interface
# ------------------------------------------------------------------

with col_chat:
    session_id = st.session_state.rc_session_id

    if session_id is None:
        st.info(t("research_chat.select_or_start"))
    else:
        session = agent.get_session(session_id)
        if session is None:
            st.warning(t("research_chat.session_not_found"))
            st.session_state.rc_session_id = None
        else:
            # Header
            header = f"### {session.ticker}"
            if session.company_name:
                header += f" · {session.company_name}"
            st.markdown(header)
            st.caption(
                f"{t('research_chat.strategy_caption')}: {session.strategy_name} · "
                f"{t('research_chat.started_caption')}: {session.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            # Display messages
            messages = agent.get_messages(session_id)
            for msg in messages:
                if msg.role == "tool":
                    continue
                role = "user" if msg.role == "user" else "assistant"
                with st.chat_message(role):
                    st.markdown(msg.content)
                    if role == "assistant":
                        st.caption(t("common.ai_disclaimer"))

            # Render proposal panel if there are proposals
            if st.session_state.rc_proposals:
                st.divider()
                st.subheader("📋 Watchlist-Vorschläge")
                st.caption("Claude empfiehlt diese Kandidaten — wähle aus, welche du übernehmen möchtest:")

                for i, p in enumerate(st.session_state.rc_proposals):
                    st.checkbox(
                        f"**{p['name']}** ({p['ticker']}) · {p['asset_class']}",
                        key=f"prop_check_{session_id}_{i}",
                    )
                    if p.get("notes"):
                        st.caption(p["notes"])

                if st.button("Zur Watchlist hinzufügen", type="primary", key=f"add_proposals_{session_id}"):
                    selected_proposals = [
                        st.session_state.rc_proposals[i]
                        for i in range(len(st.session_state.rc_proposals))
                        if st.session_state.get(f"prop_check_{session_id}_{i}", False)
                    ]
                    if selected_proposals:
                        for prop in selected_proposals:
                            try:
                                agent.add_from_proposal(session_id, prop)
                            except Exception as exc:
                                st.error(f"Error adding {prop['name']}: {exc}")
                        st.success(f"✅ {len(selected_proposals)} Position(en) hinzugefügt!", icon=":material/bookmark_added:")
                        st.session_state.rc_proposals = []
                        st.rerun()
                    else:
                        st.info("Bitte wähle mindestens eine Position aus.")

            # Chat input
            if prompt := st.chat_input(t("research_chat.chat_placeholder")):
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner(t("research_chat.analysing")):
                        try:
                            response, proposals = asyncio.run(agent.chat(session_id, prompt, language=current_language()))
                            st.session_state.rc_proposals = proposals
                        except Exception as exc:
                            response = f"⚠️ {t('common.agent_error')}: {exc}"
                            st.session_state.rc_proposals = []
                    st.markdown(response)
                    st.caption(t("common.ai_disclaimer"))
                st.rerun()
