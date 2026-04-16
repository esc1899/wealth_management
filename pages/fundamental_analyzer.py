"""
Fundamental Analyzer — in-depth analysis of individual positions via chat.

Cloud ☁️ agent: analyzes valuation, business quality, competitive position, risks.
Interactive chat interface for following up on specific questions.
"""

import asyncio
import threading
import time

import streamlit as st

from core.i18n import t
from core.ui.verdicts import cloud_notice
from state import get_analyses_repo, get_fundamental_analyzer_agent, get_portfolio_service

st.set_page_config(page_title="Fundamental Analyzer", page_icon="📊", layout="wide")
st.title("📊 Fundamental Analyzer")
st.caption("Tiefgehende Fundamentalwert-Analyse einzelner Positionen")

agent = get_fundamental_analyzer_agent()
analyses_repo = get_analyses_repo()
cloud_notice(agent.model)

with st.expander("ℹ️ Wie nutze ich das?", expanded=False):
    st.markdown("""
**Fundamental Analyzer** analysiert einzelne Positionen aus Ihrem Portfolio oder Ihrer Watchlist tiefgehend.

Fokusthemen:
- **Geschäftsmodell & Strategie:** Kerngeschäft, Profitabilität, Management-Quality
- **Bewertung:** KGV, EV/EBITDA, Fair Value, Margin of Safety
- **Wachstum:** Historische Trends, TAM-Expansion, Katalysatoren
- **Risiken:** Finanzielle, operative, makroökonomische Risiken
- **Zeithorizont:** Wann wird die Bewertung gerecht?

Der Agent nutzt Web-Search um aktuelle Daten zu finden (Finanzkennzahlen, Management-Updates, Konkurrenztrends).

**Tipp:** Starten Sie mit einer Position und stellen Sie Folgefragen um tiefer einzusteigen.
""")

# ------------------------------------------------------------------
# Load data
# ------------------------------------------------------------------

portfolio_service = get_portfolio_service()
all_positions = portfolio_service.get_all_positions(
    include_portfolio=True, include_watchlist=True
)
positions_with_required_fields = [p for p in all_positions if p.name]

# ------------------------------------------------------------------
# Layout: left control panel | right chat
# ------------------------------------------------------------------

col_left, col_right = st.columns([0.8, 2.2], gap="medium")

# ------------------------------------------------------------------
# Left: position selection + past sessions
# ------------------------------------------------------------------

with col_left:
    st.subheader("Position wählen")

    if not positions_with_required_fields:
        st.warning("Keine Positionen vorhanden. Fügen Sie zunächst Positionen hinzu.")
        st.stop()
    else:
        pos_labels = [
            f"{p.name} ({p.ticker})" if p.ticker else p.name
            for p in positions_with_required_fields
        ]

        with st.form("new_analysis_form"):
            selected_idx = st.selectbox(
                "Position für Analyse",
                options=range(len(positions_with_required_fields)),
                format_func=lambda i: pos_labels[i],
            )
            selected_position = positions_with_required_fields[selected_idx]

            submitted = st.form_submit_button("▶️ Analyse starten", use_container_width=True, type="primary")

        # Show position details as reference
        if selected_position:
            with st.expander(f"📋 {selected_position.name}", expanded=False):
                if selected_position.ticker:
                    st.caption(f"**Ticker:** {selected_position.ticker}")
                if selected_position.asset_class:
                    st.caption(f"**Anlageklasse:** {selected_position.asset_class}")
                if selected_position.anlageart:
                    st.caption(f"**Anlage-Art:** {selected_position.anlageart}")
                if selected_position.purchase_price:
                    st.metric("Kaufpreis", f"€{selected_position.purchase_price:,.2f}")
                if selected_position.story:
                    st.caption("**Investment-These:**")
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
            st.error(f"⚠️ Fehler: {st.session_state.pop('fa_start_error')}")

        if submitted:
            with st.spinner("Starte Analyse..."):
                try:
                    # Clear old session if position changed
                    current_session = agent.get_session(st.session_state.get("fa_session_id")) if st.session_state.get("fa_session_id") else None
                    if current_session and current_session.position_id != selected_position.id:
                        st.session_state.pop("fa_session_id", None)

                    session = agent.start_session(position=selected_position)
                    st.session_state["fa_session_id"] = session.id
                except Exception as exc:
                    st.session_state["fa_start_error"] = str(exc)
            st.rerun()

# ------------------------------------------------------------------
# Right: chat interface
# ------------------------------------------------------------------

with col_right:
    session_id = st.session_state.get("fa_session_id")

    if session_id is None:
        st.info("Wählen Sie eine Position und starten Sie die Analyse")
    else:
        session = agent.get_session(session_id)
        if session is None:
            st.warning("Sitzung nicht gefunden")
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
                        st.caption("💡 Mit Web-Search gesammelte Informationen")

            if prompt := st.chat_input("Weitere Fragen zur Position..."):
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner("Analysiere..."):
                        try:
                            response = agent.chat(session_id, prompt)
                        except Exception as exc:
                            response = f"⚠️ Fehler: {exc}"
                    st.markdown(response)
                    st.caption("💡 Mit Web-Search gesammelte Informationen")
                st.rerun()
