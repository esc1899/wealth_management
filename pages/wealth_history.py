"""
Wealth History page — displays portfolio wealth and dividend income over time.
Combines automatic snapshots taken after each market data refresh into charts and tables.
"""

import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

from core.i18n import t
from state import get_wealth_snapshot_agent, get_dividend_snapshot_repo


st.markdown(f"## {t('nav.wealth_history', default='Vermögenshistorie')}")

agent = get_wealth_snapshot_agent()
div_repo = get_dividend_snapshot_repo()

# Get snapshots
wealth_snapshots = agent.list_snapshots(days=None) or []
dividend_snapshots = div_repo.list(days=None) or []

if not wealth_snapshots and not dividend_snapshots:
    st.info(t(
        "wealth_history.no_snapshots",
        default="Keine Snapshots vorhanden. Snapshots werden automatisch nach jedem Marktdaten-Refresh erstellt."
    ))
    st.stop()

# ─────────────────────────────────────────────────────────────────────────
# Section 1: Wealth Development
# ─────────────────────────────────────────────────────────────────────────

st.markdown(f"### {t('wealth_history.wealth_section', default='Vermögensentwicklung')}")

if wealth_snapshots:
    col_date, col_total, col_coverage = st.columns(3)
    latest = wealth_snapshots[-1]

    with col_date:
        st.metric(
            label=t("wealth_history.latest_snapshot_date", default="Letzter Snapshot"),
            value=latest.date,
        )
    with col_total:
        st.metric(
            label=t("wealth_history.total_wealth", default="Gesamtvermögen"),
            value=f"€ {latest.total_eur:,.0f}",
        )
    with col_coverage:
        st.metric(
            label=t("wealth_history.data_coverage", default="Datenabdeckung"),
            value=f"{latest.coverage_pct:.1f}%",
        )

    # Wealth development chart
    dates = [s.date for s in wealth_snapshots]
    values = [s.total_eur for s in wealth_snapshots]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=values,
            mode="lines+markers",
            name=t("wealth_history.total_wealth", default="Gesamtvermögen"),
            line=dict(color="#1f77b4", width=2),
            marker=dict(size=6),
            hovertemplate="<b>%{x}</b><br>€ %{y:,.0f}<extra></extra>",
        )
    )

    fig.update_layout(
        hovermode="x unified",
        height=400,
        margin=dict(l=50, r=50, t=20, b=50),
        xaxis_title=t("wealth_history.date_label", default="Datum"),
        yaxis_title=t("wealth_history.value_eur", default="Wert (€)"),
        template="plotly_light",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Optional: stacked breakdown chart
    if st.checkbox(t("wealth_history.show_breakdown", default="Vermögensverteilung nach Assetklasse anzeigen")):
        fig_breakdown = go.Figure()

        # Get all asset classes present in any snapshot
        all_classes = set()
        for snapshot in wealth_snapshots:
            all_classes.update(snapshot.breakdown.keys())

        for asset_class in sorted(all_classes):
            values_by_class = [snapshot.breakdown.get(asset_class, 0) for snapshot in wealth_snapshots]
            fig_breakdown.add_trace(
                go.Scatter(
                    x=dates,
                    y=values_by_class,
                    mode="lines",
                    name=asset_class,
                    stackgroup="one",
                    hovertemplate="<b>%{x}</b><br>" + asset_class + ": € %{y:,.0f}<extra></extra>",
                )
            )

        fig_breakdown.update_layout(
            hovermode="x unified",
            height=400,
            margin=dict(l=50, r=50, t=20, b=50),
            xaxis_title=t("wealth_history.date_label", default="Datum"),
            yaxis_title=t("wealth_history.value_eur", default="Wert (€)"),
            template="plotly_light",
        )
        st.plotly_chart(fig_breakdown, use_container_width=True)

else:
    st.warning(t("wealth_history.no_wealth_snapshots", default="Keine Vermögenshistorie vorhanden."))

# ─────────────────────────────────────────────────────────────────────────
# Section 2: Dividend Development
# ─────────────────────────────────────────────────────────────────────────

st.markdown(f"### {t('wealth_history.dividend_section', default='Dividendenentwicklung')}")

if dividend_snapshots:
    col_date, col_total = st.columns(2)
    latest_div = dividend_snapshots[-1]

    with col_date:
        st.metric(
            label=t("wealth_history.latest_snapshot_date", default="Letzter Snapshot"),
            value=latest_div.date,
        )
    with col_total:
        st.metric(
            label=t("wealth_history.annual_dividend", default="Jährliche Dividende"),
            value=f"€ {latest_div.total_eur:,.0f}",
        )

    # Dividend development chart
    dates_div = [s.date for s in dividend_snapshots]
    values_div = [s.total_eur for s in dividend_snapshots]

    fig_div = go.Figure()
    fig_div.add_trace(
        go.Bar(
            x=dates_div,
            y=values_div,
            name=t("wealth_history.annual_dividend", default="Jährliche Dividende"),
            marker=dict(color="#2ca02c"),
            hovertemplate="<b>%{x}</b><br>€ %{y:,.0f}<extra></extra>",
        )
    )

    fig_div.update_layout(
        hovermode="x unified",
        height=400,
        margin=dict(l=50, r=50, t=20, b=50),
        xaxis_title=t("wealth_history.date_label", default="Datum"),
        yaxis_title=t("wealth_history.value_eur", default="Wert (€)"),
        template="plotly_light",
        showlegend=False,
    )
    st.plotly_chart(fig_div, use_container_width=True)

    # Optional: stacked by asset class
    if st.checkbox(t("wealth_history.show_dividend_breakdown", default="Dividenden nach Assetklasse anzeigen")):
        fig_div_breakdown = go.Figure()

        # Get all asset classes present in any dividend snapshot
        all_div_classes = set()
        for snapshot in dividend_snapshots:
            all_div_classes.update(snapshot.breakdown.keys())

        for asset_class in sorted(all_div_classes):
            values_by_class = [snapshot.breakdown.get(asset_class, 0) for snapshot in dividend_snapshots]
            fig_div_breakdown.add_trace(
                go.Bar(
                    x=dates_div,
                    y=values_by_class,
                    name=asset_class,
                    hovertemplate="<b>%{x}</b><br>" + asset_class + ": € %{y:,.0f}<extra></extra>",
                )
            )

        fig_div_breakdown.update_layout(
            hovermode="x unified",
            height=400,
            margin=dict(l=50, r=50, t=20, b=50),
            xaxis_title=t("wealth_history.date_label", default="Datum"),
            yaxis_title=t("wealth_history.value_eur", default="Wert (€)"),
            template="plotly_light",
            barmode="stack",
        )
        st.plotly_chart(fig_div_breakdown, use_container_width=True)

else:
    st.warning(t("wealth_history.no_dividend_snapshots", default="Keine Dividendenhistorie vorhanden."))

# ─────────────────────────────────────────────────────────────────────────
# Section 3: Raw Data Tables
# ─────────────────────────────────────────────────────────────────────────

st.markdown(f"### {t('wealth_history.raw_data', default='Rohdaten')}")

tab_wealth, tab_dividend = st.tabs([
    t("wealth_history.wealth_tab", default="Vermögen"),
    t("wealth_history.dividend_tab", default="Dividenden"),
])

with tab_wealth:
    if wealth_snapshots:
        data = []
        for snap in wealth_snapshots:
            data.append({
                t("wealth_history.date_label", default="Datum"): snap.date,
                t("wealth_history.total_wealth", default="Gesamtvermögen"): f"€ {snap.total_eur:,.0f}",
                t("wealth_history.data_coverage", default="Datenabdeckung"): f"{snap.coverage_pct:.1f}%",
                t("wealth_history.manual_flag", default="Manuell"): "✓" if snap.is_manual else "",
            })
        st.dataframe(data, use_container_width=True, hide_index=True)
    else:
        st.info(t("wealth_history.no_data", default="Keine Daten"))

with tab_dividend:
    if dividend_snapshots:
        data = []
        for snap in dividend_snapshots:
            data.append({
                t("wealth_history.date_label", default="Datum"): snap.date,
                t("wealth_history.annual_dividend", default="Jährliche Dividende"): f"€ {snap.total_eur:,.0f}",
                t("wealth_history.data_coverage", default="Datenabdeckung"): f"{snap.coverage_pct:.1f}%",
                t("wealth_history.manual_flag", default="Manuell"): "✓" if snap.is_manual else "",
            })
        st.dataframe(data, use_container_width=True, hide_index=True)
    else:
        st.info(t("wealth_history.no_data", default="Keine Daten"))
