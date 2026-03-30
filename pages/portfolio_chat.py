"""
Portfolio Chat — natural language interface to the Portfolio Agent.
"""

import asyncio
import pandas as pd
import streamlit as st

from config import config
from core.health import is_local_url
from core.i18n import t
from state import get_portfolio_agent, get_positions_repo

st.set_page_config(page_title="Portfolio Chat", page_icon="💬", layout="wide")
st.title(f"💬 {t('portfolio_chat.title')}")

agent = get_portfolio_agent()
repo = get_positions_repo()

st.caption(
    f"Modell: {agent._llm.model} · "
    "Beispiele: 'Ich habe heute 10 SAP-Aktien für 185€ gekauft' · "
    "'Zeig mein Portfolio' · 'Füge Tesla zur Watchlist hinzu'"
)

if is_local_url(config.OLLAMA_HOST):
    st.info(t("rebalance_chat.private_notice").format(model=agent._llm.model), icon="🔒")
else:
    st.warning(t("rebalance_chat.remote_notice").format(host=config.OLLAMA_HOST, model=agent._llm.model), icon="⚠️")

if config.DEMO_MODE:
    st.info(t("portfolio_chat.demo_warning"), icon=":material/experiment:")

col_chat, col_tables = st.columns([3, 2])

with col_chat:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input(t("portfolio_chat.input_placeholder")):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner(t("portfolio_chat.thinking")):
                try:
                    response = asyncio.run(agent.chat(prompt))
                except Exception as exc:
                    response = f"⚠️ {t('common.agent_error')}: {exc}"
            st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()

with col_tables:
    # Always read fresh from DB
    portfolio = repo.get_portfolio()
    portfolio_count_label = t("portfolio_chat.portfolio_count").replace("{count}", str(len(portfolio)))
    st.subheader(portfolio_count_label)
    if portfolio:
        df = pd.DataFrame([
            {
                "ID":                        e.id,
                t("common.ticker"):          e.ticker or "—",
                t("common.name"):            e.name,
                t("common.asset_class"):     e.asset_class,
                t("common.strategy"):        e.strategy or "—",
                t("common.quantity"):        e.quantity,
                t("common.unit"):            e.unit,
                t("common.purchase_price"):  e.purchase_price,
                t("common.date"):            e.purchase_date.strftime("%d.%m.%Y") if e.purchase_date else "—",
            }
            for e in portfolio
        ])
        st.dataframe(
            df.style.format({
                t("common.quantity"):        lambda x: "—" if x is None or pd.isna(x) else (f"{int(x):,}" if x == int(x) else f"{x:,.2f}"),
                t("common.purchase_price"):  lambda x: f"{x:.2f}" if x is not None and not pd.isna(x) else "—",
            }),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(t("portfolio_chat.empty_positions"))

    watchlist = repo.get_watchlist()
    watchlist_count_label = t("portfolio_chat.watchlist_count").replace("{count}", str(len(watchlist)))
    st.subheader(watchlist_count_label)
    if watchlist:
        df_wl = pd.DataFrame([
            {
                "ID":                        e.id,
                t("common.ticker"):          e.ticker or "—",
                t("common.name"):            e.name,
                t("common.asset_class"):     e.asset_class,
                t("common.strategy"):        e.strategy or "—",
                t("portfolio_chat.source"):  e.recommendation_source or "—",
                t("portfolio_chat.notes"):   e.notes or "",
            }
            for e in watchlist
        ])
        st.dataframe(df_wl, use_container_width=True, hide_index=True)
    else:
        st.info(t("portfolio_chat.empty_portfolio"))
