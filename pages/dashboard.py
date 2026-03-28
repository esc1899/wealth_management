"""
Dashboard — portfolio overview with current valuations and P&L.
Positions grouped by investment type (only types present in portfolio shown).
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from state import get_market_agent

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
st.title("📊 Dashboard")
st.caption("Agentic Wealth Manager")

market_agent = get_market_agent()

col_title, col_refresh = st.columns([5, 1])
with col_refresh:
    if st.button("🔄 Aktualisieren"):
        st.rerun()

valuations = market_agent.get_portfolio_valuation()
last_fetch = market_agent._market.get_latest_fetch_time()

if last_fetch:
    st.caption(f"Kurse zuletzt abgerufen: {last_fetch.strftime('%d.%m.%Y %H:%M')} UTC")
else:
    st.caption("Noch keine Kursdaten. Bitte auf der Marktdaten-Seite aktualisieren.")

if not valuations:
    st.info("Portfolio ist leer. Füge Positionen im Portfolio-Chat hinzu.")
    st.stop()

# ------------------------------------------------------------------
# KPI row
# ------------------------------------------------------------------
has_prices = any(v.current_value_eur is not None for v in valuations)
total_value = sum(v.current_value_eur for v in valuations if v.current_value_eur is not None)
total_cost = sum(v.cost_basis_eur for v in valuations if v.cost_basis_eur is not None)
total_pnl = (total_value - total_cost) if has_prices and total_cost > 0 else None
total_pnl_pct = (total_pnl / total_cost * 100) if total_pnl is not None and total_cost > 0 else None

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Portfoliowert", f"€ {total_value:,.2f}" if has_prices else "Keine Kurse")
with col2:
    if total_pnl is not None:
        st.metric("Gesamt G/V", f"€ {total_pnl:,.2f}", delta=f"{total_pnl_pct:.2f}%")
    else:
        st.metric("Gesamt G/V", "—")
with col3:
    st.metric("Einstandswert", f"€ {total_cost:,.2f}" if total_cost else "—")
with col4:
    st.metric("Positionen", len(valuations))

st.divider()


def fmt_optional(val, pattern="{:.2f}"):
    return pattern.format(val) if val is not None else "—"


fmt = {
    "Anzahl": "{:.4g}",
    "Einheit": "{}",
    "Kaufpreis €": lambda x: fmt_optional(x),
    "Aktuell €":   lambda x: fmt_optional(x),
    "Wert €":      lambda x: fmt_optional(x, "€ {:,.2f}"),
    "G/V €":       lambda x: fmt_optional(x, "{:+,.2f}"),
    "G/V %":       lambda x: fmt_optional(x, "{:+.2f}%"),
}

# ------------------------------------------------------------------
# Positions grouped by investment type
# ------------------------------------------------------------------
investment_types = list(dict.fromkeys(v.investment_type for v in valuations))

for inv_type in investment_types:
    group = [v for v in valuations if v.investment_type == inv_type]
    st.subheader(inv_type)

    rows = [
        {
            "Symbol":      v.symbol,
            "Name":        v.name,
            "Klasse":      v.asset_class,
            "Anzahl":      v.quantity,
            "Einheit":     v.unit,
            "Kaufpreis €": v.purchase_price_eur,
            "Aktuell €":   v.current_price_eur,
            "Wert €":      v.current_value_eur,
            "G/V €":       v.pnl_eur,
            "G/V %":       v.pnl_pct,
        }
        for v in group
    ]
    df = pd.DataFrame(rows)
    st.dataframe(df.style.format(fmt), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------
# Allocation chart (only if prices available)
# ------------------------------------------------------------------
if has_prices:
    st.divider()
    st.subheader("Portfoliogewichtung")

    col_pie1, col_pie2 = st.columns(2)

    with col_pie1:
        st.caption("Nach Investment-Typ")
        alloc_type = {}
        for v in valuations:
            if v.current_value_eur:
                alloc_type[v.investment_type] = alloc_type.get(v.investment_type, 0) + v.current_value_eur
        if alloc_type:
            fig = px.pie(names=list(alloc_type.keys()), values=list(alloc_type.values()), hole=0.4)
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    with col_pie2:
        st.caption("Nach Position")
        alloc_pos = {v.symbol: v.current_value_eur for v in valuations if v.current_value_eur}
        if alloc_pos:
            fig2 = px.pie(names=list(alloc_pos.keys()), values=list(alloc_pos.values()), hole=0.4)
            fig2.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig2, use_container_width=True)
