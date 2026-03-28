"""
Research Chat — chat-based stock analysis with Claude + web search.
"""

import asyncio

import streamlit as st

from core.strategy_config import CUSTOM_STRATEGY_NAME
from state import get_research_agent

st.set_page_config(page_title="Research Chat", page_icon="🔍", layout="wide")
st.title("🔍 Research Chat")
st.caption("Aktienanalyse mit Claude + Web-Suche")

agent = get_research_agent()
strategy_registry = agent._strategies

# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------

if "rc_session_id" not in st.session_state:
    st.session_state.rc_session_id = None

# ------------------------------------------------------------------
# Layout: left sidebar (sessions + new) | right chat
# ------------------------------------------------------------------

col_sidebar, col_chat = st.columns([1, 2])

# ------------------------------------------------------------------
# Left: new session form + past sessions
# ------------------------------------------------------------------

with col_sidebar:
    st.subheader("Neue Analyse")

    with st.form("new_session_form"):
        company_input = st.text_input(
            "Unternehmen oder Ticker *",
            placeholder="z.B. Apple, AAPL, SAP SE, SAP.DE",
        ).strip()

        strategy_options = strategy_registry.all_names() + [CUSTOM_STRATEGY_NAME]
        strategy_choice = st.selectbox("Strategie", strategy_options)

        custom_prompt = ""
        if strategy_choice == CUSTOM_STRATEGY_NAME:
            custom_prompt = st.text_area(
                "Analysefokus *",
                placeholder="Beschreibe deinen Analysefokus...",
                height=120,
            ).strip()

        submitted = st.form_submit_button("Analyse starten", use_container_width=True)

    if submitted:
        if not company_input:
            st.error("Bitte Unternehmen oder Ticker eingeben.")
        elif strategy_choice == CUSTOM_STRATEGY_NAME and not custom_prompt:
            st.error("Bitte Analysefokus eingeben.")
        else:
            # Use input as ticker placeholder; agent will resolve it if it's a name
            session = agent.start_session(
                ticker=company_input.upper(),
                strategy_name=strategy_choice,
                company_name=None,
                custom_prompt=custom_prompt or None,
            )
            st.session_state.rc_session_id = session.id
            initial_msg = (
                f"Bitte analysiere '{company_input}'. Falls das kein Ticker-Symbol ist, "
                f"finde zunächst das korrekte Ticker-Symbol und gib mir dann eine "
                f"strukturierte Bewertung gemäß der Analysestrategie."
            )
            with st.spinner("Analyse läuft…"):
                asyncio.run(agent.chat(session.id, initial_msg))
            st.rerun()

    st.divider()
    st.subheader("Vergangene Analysen")

    sessions = agent.list_sessions(limit=30)
    if not sessions:
        st.info("Noch keine Analysen.")
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
                st.rerun()

# ------------------------------------------------------------------
# Right: chat interface
# ------------------------------------------------------------------

with col_chat:
    session_id = st.session_state.rc_session_id

    if session_id is None:
        st.info("Wähle links eine vergangene Analyse oder starte eine neue.")
    else:
        session = agent.get_session(session_id)
        if session is None:
            st.warning("Session nicht gefunden.")
            st.session_state.rc_session_id = None
        else:
            # Header
            header = f"### {session.ticker}"
            if session.company_name:
                header += f" · {session.company_name}"
            st.markdown(header)
            st.caption(
                f"Strategie: {session.strategy_name} · "
                f"Gestartet: {session.created_at.strftime('%d.%m.%Y %H:%M')}"
            )

            # Display messages
            messages = agent.get_messages(session_id)
            for msg in messages:
                if msg.role == "tool":
                    continue
                role = "user" if msg.role == "user" else "assistant"
                with st.chat_message(role):
                    st.markdown(msg.content)

            # Chat input
            if prompt := st.chat_input("Frage zur Analyse…"):
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner("Analysiere…"):
                        response = asyncio.run(agent.chat(session_id, prompt))
                    st.markdown(response)
                st.rerun()
