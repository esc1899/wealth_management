"""
Market Data — trigger price fetches and show current prices.
"""

import pandas as pd
import streamlit as st

from core.i18n import t
from state import get_market_agent, get_positions_repo

st.set_page_config(page_title="Marktdaten", page_icon="📈", layout="wide")
st.title(f"📈 {t('market_data.title')}")

agent = get_market_agent()
repo = get_positions_repo()

col_title, col_refresh = st.columns([5, 1])
with col_refresh:
    if st.button(f"🔄 {t('common.refresh')}"):
        with st.spinner(t("market_data.fetching")):
            try:
                result = agent.fetch_all_now(fetch_history=True)
                if result.fetched > 0:
                    st.success(f"{result.fetched} {t('market_data.fetch_success')}")
                else:
                    st.warning(t("market_data.fetch_warning"))
                if result.failed:
                    st.error(f"{t('market_data.fetch_error')}: {', '.join(result.failed)}")
            except Exception as e:
                st.error(f"{t('market_data.fetch_exception')}: {e}")
        st.rerun()

last_fetch = agent.get_latest_fetch_time()
if last_fetch:
    st.caption(f"{t('market_data.last_updated')}: {last_fetch.strftime('%d.%m.%Y %H:%M')} UTC")
else:
    st.caption(t("market_data.no_price_data"))

st.divider()

# ------------------------------------------------------------------
# Positions with current prices
# ------------------------------------------------------------------
valuations = agent.get_portfolio_valuation(include_watchlist=True)
tickers = repo.get_tickers_for_price_fetch()

tickers_label = t("market_data.positions_tickers").replace("{count}", str(len(tickers)))
st.subheader(tickers_label)

if not tickers:
    st.info(t("market_data.no_tickers"))
    st.stop()


def fmt_opt(val, pattern="{:.2f}"):
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


def render_valuations(entries):
    if not entries:
        st.info(t("market_data.no_prices"))
        return

    col_retrieved = t("market_data.retrieved_at")
    col_price = t("market_data.price_col")
    col_div = "Div.-Rendite"

    rows = [
        {
            t("common.ticker"):      v.symbol,
            t("common.name"):        v.name,
            t("common.asset_class"): v.asset_class,
            t("common.quantity"):    v.quantity,
            t("common.unit"):        v.unit,
            col_price:               v.current_price_eur,
            t("common.value"):       v.current_value_eur,
            col_div:                 (v.dividend_yield_pct * 100) if v.dividend_yield_pct else None,
            col_retrieved:           v.fetched_at.strftime("%d.%m %H:%M") if v.fetched_at else "—",
        }
        for v in entries
    ]
    df = pd.DataFrame(rows)
    st.dataframe(
        df.style.format({
            t("common.quantity"): fmt_quantity,
            col_price:            lambda x: fmt_opt(x),
            t("common.value"):    lambda x: fmt_opt(x, "€ {:,.2f}"),
            col_div:              lambda x: fmt_opt(x, "{:.2f}%"),
        }),
        use_container_width=True,
        hide_index=True,
    )
    st.caption("ℹ️ Dividenden / Ausschüttungen werden nicht automatisch mit Kursen aktualisiert — Button auf der Positionen-Seite.")


portfolio_vals = [v for v in valuations if v.in_portfolio]
watchlist_vals = [v for v in valuations if v.in_watchlist]

if portfolio_vals or not watchlist_vals:
    st.markdown(t("market_data.portfolio_section"))
    render_valuations(portfolio_vals)

if watchlist_vals:
    st.markdown(t("market_data.watchlist_section"))
    render_valuations(watchlist_vals)

# Positions without ticker
no_ticker = [p for p in repo.get_portfolio() if not p.ticker]
if no_ticker:
    st.divider()
    st.warning(f"{len(no_ticker)} {t('market_data.no_ticker_warning')}:")
    for p in no_ticker:
        st.write(f"• {p.name} ({p.asset_class})")
