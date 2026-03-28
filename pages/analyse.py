"""
Analyse — performance charts, historical prices, allocation.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from state import get_market_agent

st.set_page_config(page_title="Analyse", page_icon="🔍", layout="wide")
st.title("🔍 Analyse")

agent = get_market_agent()

col_title, col_refresh = st.columns([5, 1])
with col_refresh:
    if st.button("🔄 Aktualisieren"):
        st.rerun()

valuations = agent.get_portfolio_valuation()

if not valuations:
    st.info("Portfolio ist leer.")
    st.stop()

has_prices = any(v.current_value_eur is not None for v in valuations)

if not has_prices:
    st.warning("Noch keine Kursdaten. Bitte auf der Marktdaten-Seite aktualisieren.")

# ------------------------------------------------------------------
# G/V je Position
# ------------------------------------------------------------------
st.subheader("Gewinn / Verlust je Position")

pnl_rows = [
    {"Symbol": v.symbol, "G/V €": v.pnl_eur, "G/V %": v.pnl_pct, "Wert €": v.current_value_eur}
    for v in valuations if v.pnl_eur is not None
]

if pnl_rows:
    df_pnl = pd.DataFrame(pnl_rows).sort_values("G/V €")
    fig_pnl = px.bar(
        df_pnl, x="Symbol", y="G/V €",
        color="G/V €",
        color_continuous_scale=["red", "lightgrey", "green"],
        color_continuous_midpoint=0,
        text=df_pnl["G/V %"].apply(lambda x: f"{x:+.1f}%"),
    )
    fig_pnl.update_traces(textposition="outside")
    fig_pnl.update_layout(coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig_pnl, use_container_width=True)
else:
    st.info("Keine G/V-Daten verfügbar — Kurse noch nicht abgerufen.")

st.divider()

# ------------------------------------------------------------------
# Kursverlauf
# ------------------------------------------------------------------
st.subheader("Kursverlauf")

symbols = [v.symbol for v in valuations]
selected = st.selectbox("Symbol auswählen", symbols)

if selected:
    history = agent._market.get_historical(selected, days=365)
    if history:
        df_hist = pd.DataFrame([{"Datum": h.date, "Kurs €": h.close_eur} for h in history])
        fig_hist = px.line(df_hist, x="Datum", y="Kurs €", title=f"{selected} — letztes Jahr")
        fig_hist.update_layout(margin=dict(t=40))
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info("Keine historischen Daten. Auf der Marktdaten-Seite 'Jetzt aktualisieren' klicken.")

st.divider()

# ------------------------------------------------------------------
# Portfoliogewichtung — nur Investment-Typen die vorhanden sind
# ------------------------------------------------------------------
col_pie1, col_pie2 = st.columns(2)

with col_pie1:
    st.subheader("Gewichtung nach Investment-Typ")
    alloc_type = {}
    for v in valuations:
        if v.current_value_eur:
            alloc_type[v.investment_type] = alloc_type.get(v.investment_type, 0) + v.current_value_eur
    if alloc_type:
        fig = px.pie(names=list(alloc_type.keys()), values=list(alloc_type.values()), hole=0.3)
        fig.update_layout(margin=dict(t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Keine Kursdaten für Gewichtung.")

with col_pie2:
    st.subheader("Gewichtung nach Position")
    alloc_pos = {v.symbol: v.current_value_eur for v in valuations if v.current_value_eur}
    if alloc_pos:
        fig2 = px.pie(names=list(alloc_pos.keys()), values=list(alloc_pos.values()), hole=0.3)
        fig2.update_layout(margin=dict(t=0, b=0))
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Keine Kursdaten für Gewichtung.")
