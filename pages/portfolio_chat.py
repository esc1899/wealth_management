"""
Portfolio Chat — natural language interface to the Portfolio Agent.
"""

import asyncio
import pandas as pd
import streamlit as st

from state import get_portfolio_agent, get_positions_repo

st.set_page_config(page_title="Portfolio Chat", page_icon="💬", layout="wide")
st.title("💬 Portfolio Chat")

agent = get_portfolio_agent()
repo = get_positions_repo()

st.caption(
    f"Modell: {agent._llm.model} · "
    "Beispiele: 'Ich habe heute 10 SAP-Aktien für 185€ gekauft' · "
    "'Zeig mein Portfolio' · 'Füge Tesla zur Watchlist hinzu'"
)

col_chat, col_tables = st.columns([3, 2])

with col_chat:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Nachricht eingeben..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Denke nach..."):
                response = asyncio.run(agent.chat(prompt))
            st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()

with col_tables:
    # Always read fresh from DB
    portfolio = repo.get_portfolio()
    st.subheader(f"Portfolio ({len(portfolio)} Positionen)")
    if portfolio:
        df = pd.DataFrame([
            {
                "ID":          e.id,
                "Ticker":      e.ticker or "—",
                "Name":        e.name,
                "Klasse":      e.asset_class,
                "Strategie":   e.strategy or "—",
                "Anzahl":      e.quantity,
                "Einheit":     e.unit,
                "Kaufpreis €": e.purchase_price,
                "Datum":       e.purchase_date.strftime("%d.%m.%Y") if e.purchase_date else "—",
            }
            for e in portfolio
        ])
        st.dataframe(
            df.style.format({
                "Anzahl":      "{:.4g}",
                "Kaufpreis €": lambda x: f"{x:.2f}" if x is not None else "—",
            }),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Noch keine Positionen.")

    watchlist = repo.get_watchlist()
    st.subheader(f"Watchlist ({len(watchlist)} Einträge)")
    if watchlist:
        df_wl = pd.DataFrame([
            {
                "ID":        e.id,
                "Ticker":    e.ticker or "—",
                "Name":      e.name,
                "Klasse":    e.asset_class,
                "Strategie": e.strategy or "—",
                "Quelle":    e.recommendation_source or "—",
                "Notizen":   e.notes or "",
            }
            for e in watchlist
        ])
        st.dataframe(df_wl, use_container_width=True, hide_index=True)
    else:
        st.info("Noch keine Einträge.")
