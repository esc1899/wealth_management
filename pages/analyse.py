"""
Analysis — performance charts, historical prices, allocation.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from core.currency import symbol
from core.i18n import t
from state import get_market_agent, get_portfolio_service

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

st.divider()

# ------------------------------------------------------------------
# Bargeldcheck — deterministisch
# ------------------------------------------------------------------
st.subheader("💰 Bargeldcheck")

from state import get_skills_repo

skills_repo = get_skills_repo()
cash_skills = skills_repo.get_by_area("portfolio_cash_rule")
cash_skill = next((s for s in cash_skills if not s.hidden), None)

if cash_skill:
    # Parse skill prompt for min/max cash percentages (simple string parsing, not YAML to avoid injection)
    try:
        min_pct = 5.0
        max_pct = 15.0
        if cash_skill.prompt:
            # Extract min_pct and max_pct from skill prompt (supports "min_pct: 5" format)
            lines = cash_skill.prompt.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('min_pct:'):
                    try:
                        min_pct = float(line.split(':', 1)[1].strip())
                    except (ValueError, IndexError):
                        pass
                elif line.startswith('max_pct:'):
                    try:
                        max_pct = float(line.split(':', 1)[1].strip())
                    except (ValueError, IndexError):
                        pass
        # Validate ranges
        min_pct = max(0, min(100, min_pct))
        max_pct = max(0, min(100, max_pct))
        if min_pct > max_pct:
            min_pct, max_pct = 5.0, 15.0
    except Exception:
        min_pct, max_pct = 5.0, 15.0

    total_eur = sum(v.current_value_eur for v in valuations if v.current_value_eur)
    cash_eur = sum(
        v.current_value_eur
        for v in valuations
        if v.current_value_eur and v.investment_type == "Bargeld"
    )
    cash_pct = (cash_eur / total_eur * 100) if total_eur > 0 else 0

    if cash_pct < min_pct:
        status, icon = "🔴 Zu niedrig", "error"
    elif cash_pct > max_pct:
        status, icon = "🟡 Zu hoch", "warning"
    else:
        status, icon = "🟢 OK", "success"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Bargeld-Anteil", f"{cash_pct:.1f}%", delta=None)
    with col2:
        st.metric("Ziel-Range", f"{min_pct:.0f}–{max_pct:.0f}%")
    with col3:
        st.metric("Status", status.replace(" ", "\n"))

    st.info(f"Regel: {cash_skill.name}")
else:
    st.info("Keine Bargeldcheck-Regel aktiviert")

st.divider()

# ------------------------------------------------------------------
# Stabilitätscheck (Josef's Regel) — deterministisch
# ------------------------------------------------------------------
st.subheader("🏛️ Stabilitätscheck (Josef's Regel)")

from core.portfolio_stability import compute_josef_allocation

stability_skills = skills_repo.get_by_area("portfolio_stability")
stability_skill = next((s for s in stability_skills if not s.hidden), None)

if stability_skills:
    # Use correct Josef allocation calculation
    josef = compute_josef_allocation(valuations)
    aktien_pct = josef["Aktien"]
    renten_pct = josef["Renten/Geld"]
    rohstoffe_pct = josef["Rohstoffe"]

    ziel_pct = 33.33
    def _dev(pct: float) -> str:
        d = pct - ziel_pct
        return f"{d:+.0f}pp"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Aktien", f"{aktien_pct:.1f}%", delta=_dev(aktien_pct))
    with col2:
        st.metric("Renten/Geld", f"{renten_pct:.1f}%", delta=_dev(renten_pct))
    with col3:
        st.metric("Rohstoffe+Immo", f"{rohstoffe_pct:.1f}%", delta=_dev(rohstoffe_pct))

    max_dev = max(abs(aktien_pct - ziel_pct), abs(renten_pct - ziel_pct), abs(rohstoffe_pct - ziel_pct))
    if max_dev <= 5:
        status = "🟢 Stabil"
    elif max_dev <= 15:
        status = "🟡 Achtung"
    else:
        status = "🔴 Instabil"

    st.info(f"**Stabilitätsstatus:** {status} (max. Abweichung: {max_dev:.0f}pp von Ziel 33%)")
else:
    st.info("Keine Stabilitätscheck-Regeln aktiviert")

st.divider()

# ------------------------------------------------------------------
# Dividendencheck — deterministisch
# ------------------------------------------------------------------
st.subheader("💰 Portfolio-Dividenden")

total_dividend = sum(
    v.annual_dividend_eur
    for v in valuations
    if v.annual_dividend_eur
)
total_eur = sum(v.current_value_eur for v in valuations if v.current_value_eur)
dividend_yield = (total_dividend / total_eur * 100) if total_eur > 0 else 0

col1, col2 = st.columns(2)
with col1:
    st.metric("Jährliche Gesamtdividende", f"{total_dividend:.0f}€")
with col2:
    st.metric("Dividend Yield", f"{dividend_yield:.2f}%")

st.divider()

# ------------------------------------------------------------------
# Empfehler-Attribution
# ------------------------------------------------------------------

@dataclass
class AttributionRow:
    """Performance metrics aggregated by recommendation source."""
    source: Optional[str]
    count: int
    cost_basis_eur: float
    current_value_eur: float
    pnl_eur: float
    hit_rate_pct: float
    cagr_pct: Optional[float]
    cagr_with_dividend_pct: Optional[float]


def _compute_attribution(positions, valuations) -> dict[str, AttributionRow]:
    """
    Compute performance attribution by recommendation_source.
    Only includes portfolio positions (excludes watchlist).

    Returns dict {source_name: AttributionRow}, sorted by absolute P&L descending.
    """
    from datetime import date as dateobj

    # Map valuations by symbol for quick lookup
    val_by_symbol = {v.symbol: v for v in valuations}

    # Filter: only portfolio positions (exclude watchlist and analysis_excluded)
    portfolio_positions = [p for p in positions if p.in_portfolio and not p.analysis_excluded]

    # Group positions by recommendation_source
    grouped = {}
    for pos in portfolio_positions:
        source = pos.recommendation_source or "(ohne Angabe)"
        if source not in grouped:
            grouped[source] = []
        grouped[source].append(pos)

    # Compute metrics per source
    results = {}
    for source, pos_list in grouped.items():
        count = len(pos_list)
        cost_basis_eur = 0.0
        current_value_eur = 0.0
        pnl_eur = 0.0
        profitable_count = 0

        cagr_sum_weighted = 0.0
        cagr_sum_weight = 0.0
        cagr_div_sum_weighted = 0.0

        for pos in pos_list:
            val = val_by_symbol.get(pos.ticker or pos.name)
            if not val:
                continue

            # Aggregates
            if val.cost_basis_eur:
                cost_basis_eur += val.cost_basis_eur
            if val.current_value_eur:
                current_value_eur += val.current_value_eur
            if val.pnl_eur is not None:
                pnl_eur += val.pnl_eur
                if val.pnl_eur > 0:
                    profitable_count += 1

            # CAGR calculation (only if purchase_date exists and is recent enough)
            if (pos.purchase_date and val.cost_basis_eur and val.cost_basis_eur > 0
                    and val.current_value_eur and val.current_value_eur > 0):
                years_held = (dateobj.today() - pos.purchase_date).days / 365.25

                # Only compute CAGR if held > 14 days (avoid extreme annualization)
                if years_held > 14 / 365.25:
                    try:
                        cagr = (pow(val.current_value_eur / val.cost_basis_eur, 1 / years_held) - 1) * 100
                        cagr_sum_weighted += cagr * val.cost_basis_eur
                        cagr_sum_weight += val.cost_basis_eur

                        # CAGR with estimated dividend
                        estimated_div = (val.annual_dividend_eur or 0) * years_held
                        total_gain = (val.pnl_eur or 0) + estimated_div
                        cagr_div = (pow((val.cost_basis_eur + total_gain) / val.cost_basis_eur, 1 / years_held) - 1) * 100
                        cagr_div_sum_weighted += cagr_div * val.cost_basis_eur
                    except (ValueError, ZeroDivisionError):
                        pass

        # Compute weighted averages (cagr already includes * 100 from formula)
        cagr = (cagr_sum_weighted / cagr_sum_weight if cagr_sum_weight > 0 else None)
        cagr_div = (cagr_div_sum_weighted / cagr_sum_weight if cagr_sum_weight > 0 else None)

        hit_rate = (profitable_count / count * 100) if count > 0 else 0

        results[source] = AttributionRow(
            source=source,
            count=count,
            cost_basis_eur=cost_basis_eur,
            current_value_eur=current_value_eur,
            pnl_eur=pnl_eur,
            hit_rate_pct=hit_rate,
            cagr_pct=cagr,
            cagr_with_dividend_pct=cagr_div,
        )

    # Sort by P&L descending
    return dict(sorted(results.items(), key=lambda x: x[1].pnl_eur, reverse=True))


# Render attribution expander
with st.expander("📊 Empfehler-Attribution", expanded=False):
    portfolio_service = get_portfolio_service()
    all_positions = portfolio_service.get_all_positions(include_portfolio=True, include_watchlist=True)

    if not all_positions:
        st.info("Keine Positionen vorhanden.")
    else:
        attribution = _compute_attribution(all_positions, valuations)

        if not attribution:
            st.info("Keine Empfehler-Daten verfügbar.")
        else:
            # Build dataframe for display
            rows = []
            for source, row in attribution.items():
                rows.append({
                    "Empfehler": row.source,
                    "Anzahl": row.count,
                    "Kapital (€)": f"{row.cost_basis_eur:,.0f}",
                    "Aktuell (€)": f"{row.current_value_eur:,.0f}",
                    "G/V (€)": f"{row.pnl_eur:+,.0f}",
                    "Hit Rate": f"{row.hit_rate_pct:.0f}%",
                    "CAGR": f"{row.cagr_pct:.1f}%" if row.cagr_pct is not None else "n/a",
                    "Total Return (~)": f"{row.cagr_with_dividend_pct:.1f}%" if row.cagr_with_dividend_pct is not None else "n/a",
                })

            df_attr = pd.DataFrame(rows)
            st.dataframe(df_attr, use_container_width=True, hide_index=True)

            # Explanation
            st.caption(
                "**CAGR**: Kapitalgewichtete annualisierte Rendite (nur Kursgewinne). "
                "**Total Return (~)**: geschätzte Rendite inklusive Dividenden (basiert auf aktuelle Jahresrate). "
                "Positionen ohne Kaufdatum oder Zeitraum < 2 Wochen werden ausgeklammert."
            )
