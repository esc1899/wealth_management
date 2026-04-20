"""
Analysis — performance charts, historical prices, allocation.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from core.currency import symbol
from core.i18n import t
from state import get_market_agent

st.set_page_config(page_title="Analyse", page_icon="🔍", layout="wide")
st.title(f"🔍 {t('analysis.title')}")

agent = get_market_agent()

# ------------------------------------------------------------------
# Auto-fetch: refresh prices if last fetch is older than 1 hour
# ------------------------------------------------------------------

if "analyse_auto_fetched" not in st.session_state:
    st.session_state.analyse_auto_fetched = False

if not st.session_state.analyse_auto_fetched:
    valuations_check = agent.get_portfolio_valuation()
    prices_fresh = any(
        v.fetched_at is not None
        and (datetime.now(timezone.utc) - v.fetched_at.replace(tzinfo=timezone.utc)).total_seconds() < 3600
        for v in valuations_check
        if v.fetched_at is not None
    )
    if not prices_fresh:
        with st.spinner(t("analysis.auto_fetch_notice")):
            agent.fetch_all_now(fetch_history=True)
    st.session_state.analyse_auto_fetched = True

col_title, col_refresh = st.columns([5, 1])
with col_refresh:
    if st.button(f"🔄 {t('common.refresh')}"):
        st.session_state.analyse_auto_fetched = False
        st.rerun()

valuations = agent.get_portfolio_valuation()

if not valuations:
    st.info(t("analysis.portfolio_empty"))
    st.stop()

has_prices = any(v.current_value_eur is not None for v in valuations)

if not has_prices:
    st.warning(t("analysis.no_price_data"))

# ------------------------------------------------------------------
# Today's performance (daily P&L)
# ------------------------------------------------------------------
st.subheader(t("analysis.day_pnl_header"))

col_day_eur = t("analysis.day_pnl_col")
col_day_pct = t("analysis.day_pnl_pct_col")

day_rows = [
    {
        "Symbol": v.symbol,
        col_day_eur: v.day_pnl_eur,
        col_day_pct: v.day_pnl_pct,
    }
    for v in valuations
    if v.day_pnl_eur is not None
]

if day_rows:
    df_day = pd.DataFrame(day_rows).sort_values(col_day_eur)
    total_day = df_day[col_day_eur].sum()
    total_sign = "+" if total_day >= 0 else ""
    st.caption(f"**Gesamt heute: {total_sign}{symbol()}{total_day:,.2f}**".replace(",", "X").replace(".", ",").replace("X", "."))

    fig_day = px.bar(
        df_day, x="Symbol", y=col_day_eur,
        color=col_day_eur,
        color_continuous_scale=["red", "lightgrey", "green"],
        color_continuous_midpoint=0,
        text=df_day[col_day_pct].apply(lambda x: f"{x:+.2f}%" if x is not None else ""),
    )
    fig_day.update_traces(textposition="outside")
    fig_day.update_layout(coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig_day, use_container_width=True)
else:
    st.info(t("analysis.no_day_pnl"))

st.divider()

# ------------------------------------------------------------------
# P&L per position (total, vs. cost basis)
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
    history = agent.get_historical(selected, days=365)
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
# Portfolio allocation — Sunburst with positions outer ring
# ------------------------------------------------------------------
st.subheader(t("analysis.weight_by_position"))
rows = [
    {
        "anlageklasse": t(f"investment_types.{v.investment_type}"),
        "position": v.symbol,
        "wert": v.current_value_eur
    }
    for v in valuations
    if v.current_value_eur
]
if rows:
    df = pd.DataFrame(rows).groupby(["anlageklasse", "position"])["wert"].sum().reset_index()
    fig = px.sunburst(
        df,
        path=["anlageklasse", "position"],
        values="wert",
        color="anlageklasse"
    )
    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info(t("analysis.no_weight_data"))
