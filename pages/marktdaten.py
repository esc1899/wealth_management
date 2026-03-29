"""
Marktdaten — trigger price fetches and show current prices.
"""

import pandas as pd
import streamlit as st

from state import get_market_agent, get_positions_repo

st.set_page_config(page_title="Marktdaten", page_icon="📈", layout="wide")
st.title("📈 Marktdaten")

agent = get_market_agent()
repo = get_positions_repo()

col_title, col_refresh = st.columns([5, 1])
with col_refresh:
    if st.button("🔄 Jetzt aktualisieren"):
        with st.spinner("Kurse werden abgerufen..."):
            try:
                result = agent.fetch_all_now(fetch_history=True)
                if result.fetched > 0:
                    st.success(f"{result.fetched} Kurs(e) aktualisiert.")
                else:
                    st.warning("Keine Kurse abgerufen.")
                if result.failed:
                    st.error(f"Fehler bei: {', '.join(result.failed)}")
            except Exception as e:
                st.error(f"Fehler: {e}")
        st.rerun()

last_fetch = agent._market.get_latest_fetch_time()
if last_fetch:
    st.caption(f"Zuletzt aktualisiert: {last_fetch.strftime('%d.%m.%Y %H:%M')} UTC")
else:
    st.caption("Noch keine Kursdaten.")

st.divider()

# ------------------------------------------------------------------
# Positions with current prices
# ------------------------------------------------------------------
valuations = agent.get_portfolio_valuation(include_watchlist=True)
tickers = repo.get_tickers_for_price_fetch()

st.subheader(f"Positionen ({len(tickers)} Ticker)")

if not tickers:
    st.info("Keine Ticker vorhanden. Positionen im Portfolio-Chat hinzufügen.")
    st.stop()

def fmt_opt(val, pattern="{:.2f}"):
    return pattern.format(val) if val is not None else "—"


def fmt_quantity(x):
    if x is None:
        return "—"
    if x == int(x):
        return f"{int(x):,}"
    elif x >= 1:
        return f"{x:,.2f}"
    else:
        return f"{x:.4f}"

def render_valuations(entries):
    if not entries:
        st.info("Noch keine Kurse. Auf 'Jetzt aktualisieren' klicken.")
        return
    rows = [
        {
            "Ticker":    v.symbol,
            "Name":      v.name,
            "Klasse":    v.asset_class,
            "Anzahl":    v.quantity,
            "Einheit":   v.unit,
            "Kurs €":    v.current_price_eur,
            "Wert €":    v.current_value_eur,
            "Abgerufen": v.fetched_at.strftime("%d.%m %H:%M") if v.fetched_at else "—",
        }
        for v in entries
    ]
    df = pd.DataFrame(rows)
    st.dataframe(
        df.style.format({
            "Anzahl": fmt_quantity,
            "Kurs €": lambda x: fmt_opt(x),
            "Wert €": lambda x: fmt_opt(x, "€ {:,.2f}"),
        }),
        use_container_width=True,
        hide_index=True,
    )

portfolio_vals = [v for v in valuations if v.in_portfolio]
watchlist_vals = [v for v in valuations if not v.in_portfolio]

if portfolio_vals or not watchlist_vals:
    st.markdown("**Portfolio**")
    render_valuations(portfolio_vals)

if watchlist_vals:
    st.markdown("**Watchlist**")
    render_valuations(watchlist_vals)

# Positions without ticker
no_ticker = [p for p in repo.get_portfolio() if not p.ticker]
if no_ticker:
    st.divider()
    st.warning(f"{len(no_ticker)} Position(en) ohne Ticker — kein Kursabruf möglich:")
    for p in no_ticker:
        st.write(f"• {p.name} ({p.asset_class})")
