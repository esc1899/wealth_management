"""
Analysis — performance charts, historical prices, allocation.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from core.i18n import t
from state import get_market_agent

st.set_page_config(page_title="Analyse", page_icon="🔍", layout="wide")
st.title(f"🔍 {t('analysis.title')}")

agent = get_market_agent()

col_title, col_refresh = st.columns([5, 1])
with col_refresh:
    if st.button(f"🔄 {t('common.refresh')}"):
        st.rerun()

valuations = agent.get_portfolio_valuation()

if not valuations:
    st.info(t("analysis.portfolio_empty"))
    st.stop()

has_prices = any(v.current_value_eur is not None for v in valuations)

if not has_prices:
    st.warning(t("analysis.no_price_data"))

# ------------------------------------------------------------------
# P&L per position
# ------------------------------------------------------------------
st.subheader(t("analysis.pnl_chart"))

col_pnl_eur = t("common.pnl_eur")
col_pnl_pct = t("common.pnl_pct")
col_value = t("common.value")

pnl_rows = [
    {"Symbol": v.symbol, col_pnl_eur: v.pnl_eur, col_pnl_pct: v.pnl_pct, col_value: v.current_value_eur}
    for v in valuations if v.pnl_eur is not None
]

if pnl_rows:
    df_pnl = pd.DataFrame(pnl_rows).sort_values(col_pnl_eur)
    fig_pnl = px.bar(
        df_pnl, x="Symbol", y=col_pnl_eur,
        color=col_pnl_eur,
        color_continuous_scale=["red", "lightgrey", "green"],
        color_continuous_midpoint=0,
        text=df_pnl[col_pnl_pct].apply(lambda x: f"{x:+.1f}%"),
    )
    fig_pnl.update_traces(textposition="outside")
    fig_pnl.update_layout(coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig_pnl, use_container_width=True)
else:
    st.info(t("analysis.no_pnl"))

st.divider()

# ------------------------------------------------------------------
# Price history
# ------------------------------------------------------------------
st.subheader(t("analysis.price_history"))

symbols = [v.symbol for v in valuations]
selected = st.selectbox(t("analysis.select_symbol"), symbols)

if selected:
    history = agent._market.get_historical(selected, days=365)
    if history:
        col_date = t("common.date")
        col_price = t("market_data.price_col")
        df_hist = pd.DataFrame([{col_date: h.date, col_price: h.close_eur} for h in history])
        fig_hist = px.line(df_hist, x=col_date, y=col_price, title=f"{selected} — letztes Jahr")
        fig_hist.update_layout(margin=dict(t=40))
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info(t("analysis.no_history"))

st.divider()

# ------------------------------------------------------------------
# Portfolio allocation — only investment types that are present
# ------------------------------------------------------------------
col_pie1, col_pie2 = st.columns(2)

with col_pie1:
    st.subheader(t("analysis.weight_by_type"))
    alloc_type = {}
    for v in valuations:
        if v.current_value_eur:
            alloc_type[v.investment_type] = alloc_type.get(v.investment_type, 0) + v.current_value_eur
    if alloc_type:
        fig = px.pie(names=list(alloc_type.keys()), values=list(alloc_type.values()), hole=0.3)
        fig.update_layout(margin=dict(t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(t("analysis.no_weight_data"))

with col_pie2:
    st.subheader(t("analysis.weight_by_position"))
    alloc_pos = {v.symbol: v.current_value_eur for v in valuations if v.current_value_eur}
    if alloc_pos:
        fig2 = px.pie(names=list(alloc_pos.keys()), values=list(alloc_pos.values()), hole=0.3)
        fig2.update_layout(margin=dict(t=0, b=0))
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info(t("analysis.no_weight_data"))
