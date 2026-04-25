"""
Dashboard — portfolio overview with current valuations and P&L.
Positions grouped by investment type (only types present in portfolio shown).
"""

from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.currency import fmt, symbol
from core.i18n import t
from state import get_market_agent, get_wealth_snapshot_agent

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
st.title(f"📊 {t('dashboard.title')}")
st.caption("Agentic Wealth Manager")

market_agent = get_market_agent()

col_title, col_refresh, col_egg = st.columns([5, 1, 0.15])
with col_refresh:
    if st.button(f"🔄 {t('common.refresh')}"):
        st.rerun()
with col_egg:
    if st.button("·", key="_egg_btn", help=""):
        st.session_state["_egg_clicks"] = st.session_state.get("_egg_clicks", 0) + 1
        st.rerun()

try:
    valuations = market_agent.get_portfolio_valuation()
    last_fetch = market_agent.get_latest_fetch_time()
except Exception as exc:
    st.error(f"⚠️ {t('common.agent_error')}: {exc}")
    st.stop()

if last_fetch:
    st.caption(f"{t('dashboard.prices_last_fetched')}: {last_fetch.strftime('%d.%m.%Y %H:%M')} UTC")
else:
    st.caption(t("dashboard.no_price_data"))

if not valuations:
    st.info(t("dashboard.portfolio_empty"))
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
    st.metric(t("dashboard.portfolio_value"), fmt(total_value) if has_prices else t("dashboard.no_prices"))
with col2:
    if total_pnl is not None:
        st.metric(t("dashboard.pnl"), fmt(total_pnl), delta=f"{total_pnl_pct:.2f}%")
    else:
        st.metric(t("dashboard.pnl"), "—")
with col3:
    st.metric(t("dashboard.cost_basis"), fmt(total_cost) if total_cost else "—")
with col4:
    st.metric(t("dashboard.positions_count"), len(valuations))

st.divider()


def fmt_optional(val, pattern="{:.2f}"):
    return pattern.format(val) if val is not None and not pd.isna(val) else "—"


def fmt_quantity(x):
    if x is None or pd.isna(x):
        return "—"
    if x == int(x):
        return f"{int(x):,}"
    elif x >= 1:
        return f"{x:,.2f}"
    else:
        return f"{x:.4f}"


# Column header keys mapped to translation keys
COL_QUANTITY = t("common.quantity")
COL_UNIT = t("common.unit")
COL_PURCHASE_PRICE = t("common.purchase_price")
COL_CURRENT_PRICE = t("common.current_price")
COL_VALUE = t("common.value")
COL_PNL_EUR = t("common.pnl_eur")
COL_PNL_PCT = t("common.pnl_pct")
COL_TICKER = t("common.ticker")
COL_NAME = t("common.name")
COL_ASSET_CLASS = t("common.asset_class")

COL_DIV_YIELD = "Div.-Rendite"

fmt_rules = {
    COL_QUANTITY:       fmt_quantity,
    COL_UNIT:           "{}",
    COL_PURCHASE_PRICE: lambda x: fmt_optional(x),
    COL_CURRENT_PRICE:  lambda x: fmt_optional(x),
    COL_VALUE:          lambda x: fmt_optional(x, f"{symbol()} {{:,.2f}}"),
    COL_DIV_YIELD:      lambda x: fmt_optional(x, "{:.2f}%"),
    COL_PNL_EUR:        lambda x: fmt_optional(x, "{:+,.2f}"),
    COL_PNL_PCT:        lambda x: fmt_optional(x, "{:+.2f}%"),
}

# ------------------------------------------------------------------
# Positions grouped by investment type
# ------------------------------------------------------------------
investment_types = list(dict.fromkeys(v.investment_type for v in valuations))

for inv_type in investment_types:
    group = [v for v in valuations if v.investment_type == inv_type]
    st.subheader(t(f"investment_types.{inv_type}"))

    rows = [
        {
            "Symbol":         v.symbol,
            COL_NAME:         v.name,
            COL_ASSET_CLASS:  v.asset_class,
            COL_QUANTITY:     v.quantity,
            COL_UNIT:         v.unit,
            COL_PURCHASE_PRICE: v.purchase_price_eur,
            COL_CURRENT_PRICE:  v.current_price_eur,
            COL_VALUE:          v.current_value_eur,
            COL_DIV_YIELD:      (v.dividend_yield_pct * 100) if v.dividend_yield_pct else None,
            COL_PNL_EUR:        v.pnl_eur,
            COL_PNL_PCT:        v.pnl_pct,
        }
        for v in group
    ]
    df = pd.DataFrame(rows)
    st.dataframe(df.style.format(fmt_rules), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------
# Allocation chart (only if prices available)
# ------------------------------------------------------------------
if has_prices:
    st.divider()
    st.subheader(t("dashboard.portfolio_weight"))

    col_sunburst1, col_sunburst2 = st.columns(2)

    # Sector grouping for 3-level sunburst (Sektor → Anlageklasse → Anlageform/Position)
    _SEKTOR_MAP = {
        "Wertpapiere": "Wertpapiere",
        "Renten": "Geldwerte",
        "Geld": "Geldwerte",
        "Bargeld": "Geldwerte",
        "Immobilien": "Sachwerte",
        "Rohstoffe": "Sachwerte",
        "Krypto": "Krypto",
    }

    with col_sunburst1:
        st.caption(t("analysis.weight_by_type"))
        rows = [
            {
                "sektor": _SEKTOR_MAP.get(v.investment_type, v.investment_type),
                "anlageklasse": t(f"investment_types.{v.investment_type}"),
                "anlageform": v.asset_class,
                "wert": v.current_value_eur
            }
            for v in valuations
            if v.current_value_eur
        ]
        if rows:
            df = pd.DataFrame(rows).groupby(["sektor", "anlageklasse", "anlageform"])["wert"].sum().reset_index()
            fig = px.sunburst(
                df,
                path=["sektor", "anlageklasse", "anlageform"],
                values="wert",
                color="sektor"
            )
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

    with col_sunburst2:
        st.caption(t("analysis.weight_by_position"))
        rows = [
            {
                "sektor": _SEKTOR_MAP.get(v.investment_type, v.investment_type),
                "anlageklasse": t(f"investment_types.{v.investment_type}"),
                "position": v.symbol,
                "wert": v.current_value_eur
            }
            for v in valuations
            if v.current_value_eur
        ]
        if rows:
            df = pd.DataFrame(rows).groupby(["sektor", "anlageklasse", "position"])["wert"].sum().reset_index()
            fig2 = px.sunburst(
                df,
                path=["sektor", "anlageklasse", "position"],
                values="wert",
                color="sektor"
            )
            fig2.update_layout(margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig2, use_container_width=True)

# Wealth history moved to dedicated "Vermögenshistorie" page
