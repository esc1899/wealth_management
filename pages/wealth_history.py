"""
Wealth History page — displays portfolio wealth and dividend income over time.
Combines automatic snapshots taken after each market data refresh into charts and tables.
"""

import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

from core.i18n import t
from state import get_wealth_snapshot_agent, get_dividend_snapshot_repo, get_market_agent


col_title, col_update, col_rebuild = st.columns([3, 1, 1])
with col_title:
    st.markdown(f"## {t('nav.wealth_history')}")
with col_update:
    st.write("")
    if st.button(t("wealth_history.update_button"), use_container_width=True,
                 help=t("wealth_history.update_help")):
        try:
            with st.spinner(t("wealth_history.update_running")):
                market = get_market_agent()
                result = market.fetch_all_now(fetch_history=True, include_watchlist=False)
                try:
                    market.fetch_dividends_now()
                except Exception:
                    pass
                _agent = get_wealth_snapshot_agent()
                _agent.take_snapshot(is_manual=True, overwrite=True)
                _agent.take_dividend_snapshot(is_manual=True, overwrite=True)
            if result.failed:
                st.session_state["wh_msg"] = {
                    "kind": "warning",
                    "text": t("wealth_history.update_failed").format(symbols=", ".join(result.failed)),
                }
            else:
                st.session_state["wh_msg"] = {"kind": "success", "text": t("wealth_history.update_success")}
            st.rerun()
        except Exception as e:
            st.error(t("wealth_history.update_error").format(error=e))
with col_rebuild:
    st.write("")
    if st.button(t("wealth_history.rebuild_button"), use_container_width=True,
                 help=t("wealth_history.rebuild_help")):
        try:
            with st.spinner(t("wealth_history.rebuild_running")):
                summary = get_wealth_snapshot_agent().rebuild_wealth_history()
            text = t("wealth_history.rebuild_summary").format(n=summary["recomputed"])
            issues = len(summary["low_coverage_dates"]) + len(summary["missing_dates"])
            if issues:
                text += " " + t("wealth_history.rebuild_issues").format(
                    low=len(summary["low_coverage_dates"]), missing=len(summary["missing_dates"])
                )
            st.session_state["wh_msg"] = {"kind": "warning" if issues else "success", "text": text}
            st.rerun()
        except Exception as e:
            st.error(t("wealth_history.update_error").format(error=e))

# Surface the outcome of update/rebuild across the rerun
_wh_msg = st.session_state.pop("wh_msg", None)
if _wh_msg:
    (st.success if _wh_msg["kind"] == "success" else st.warning)(_wh_msg["text"])

agent = get_wealth_snapshot_agent()
div_repo = get_dividend_snapshot_repo()

# Get snapshots
wealth_snapshots = agent.list_snapshots(days=None) or []
dividend_snapshots = div_repo.list(days=None) or []

if not wealth_snapshots and not dividend_snapshots:
    st.info(t("wealth_history.no_snapshots"))
    st.stop()

# ─────────────────────────────────────────────────────────────────────────
# Section 1: Wealth Development
# ─────────────────────────────────────────────────────────────────────────

st.markdown(f"### {t('wealth_history.wealth_section')}")

if wealth_snapshots:
    col_date, col_total, col_coverage = st.columns(3)
    latest = wealth_snapshots[-1]

    with col_date:
        st.metric(
            label=t("wealth_history.latest_snapshot_date"),
            value=latest.date,
        )
    with col_total:
        st.metric(
            label=t("wealth_history.total_wealth"),
            value=f"€ {latest.total_eur:,.0f}",
        )
    with col_coverage:
        st.metric(
            label=t("wealth_history.data_coverage"),
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
            name=t("wealth_history.total_wealth"),
            line=dict(color="#1f77b4", width=2),
            marker=dict(size=6),
            hovertemplate="<b>%{x}</b><br>€ %{y:,.0f}<extra></extra>",
        )
    )

    fig.update_layout(
        hovermode="x unified",
        height=400,
        margin=dict(l=50, r=50, t=20, b=50),
        xaxis_title=t("wealth_history.date_label"),
        yaxis_title=t("wealth_history.value_eur"),
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Optional: stacked breakdown chart
    if st.checkbox(t("wealth_history.show_breakdown")):
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
            xaxis_title=t("wealth_history.date_label"),
            yaxis_title=t("wealth_history.value_eur"),
            template="plotly_white",
        )
        st.plotly_chart(fig_breakdown, use_container_width=True)

else:
    st.warning(t("wealth_history.no_wealth_snapshots"))

# ─────────────────────────────────────────────────────────────────────────
# Section 2: Dividend Development
# ─────────────────────────────────────────────────────────────────────────

st.markdown(f"### {t('wealth_history.dividend_section')}")

if dividend_snapshots:
    col_date, col_total = st.columns(2)
    latest_div = dividend_snapshots[-1]

    with col_date:
        st.metric(
            label=t("wealth_history.latest_snapshot_date"),
            value=latest_div.date,
        )
    with col_total:
        st.metric(
            label=t("wealth_history.annual_dividend"),
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
            name=t("wealth_history.annual_dividend"),
            marker=dict(color="#2ca02c"),
            hovertemplate="<b>%{x}</b><br>€ %{y:,.0f}<extra></extra>",
        )
    )

    fig_div.update_layout(
        hovermode="x unified",
        height=400,
        margin=dict(l=50, r=50, t=20, b=50),
        xaxis_title=t("wealth_history.date_label"),
        yaxis_title=t("wealth_history.value_eur"),
        template="plotly_white",
        showlegend=False,
    )
    st.plotly_chart(fig_div, use_container_width=True)

    # Optional: stacked by asset class
    if st.checkbox(t("wealth_history.show_dividend_breakdown")):
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
            xaxis_title=t("wealth_history.date_label"),
            yaxis_title=t("wealth_history.value_eur"),
            template="plotly_white",
            barmode="stack",
        )
        st.plotly_chart(fig_div_breakdown, use_container_width=True)

else:
    st.warning(t("wealth_history.no_dividend_snapshots"))

# ─────────────────────────────────────────────────────────────────────────
# Section 3: Raw Data Tables
# ─────────────────────────────────────────────────────────────────────────

st.markdown(f"### {t('wealth_history.raw_data')}")

# Show recalculation result after rerun
if "recalc_result" in st.session_state:
    msg = st.session_state.pop("recalc_result")
    if msg["ok"]:
        st.success(msg["text"])
    else:
        st.warning(msg["text"])

tab_wealth, tab_dividend = st.tabs([
    t("wealth_history.wealth_tab"),
    t("wealth_history.dividend_tab"),
])

with tab_wealth:
    if wealth_snapshots:
        header = st.columns([2, 2, 2, 1, 1, 1])
        header[0].markdown(f"**{t('wealth_history.date_label')}**")
        header[1].markdown(f"**{t('wealth_history.total_wealth')}**")
        header[2].markdown(f"**{t('wealth_history.data_coverage')}**")
        header[3].markdown(f"**{t('wealth_history.manual_flag')}**")
        st.divider()
        for snap in reversed(wealth_snapshots):
            low_coverage = snap.coverage_pct < 95.0
            cols = st.columns([2, 2, 2, 1, 1, 1])
            cols[0].write(snap.date)
            cols[1].write(f"€ {snap.total_eur:,.0f}")
            coverage_label = f"⚠️ {snap.coverage_pct:.1f}%" if low_coverage else f"{snap.coverage_pct:.1f}%"
            cols[2].write(coverage_label)
            cols[3].write("✓" if snap.is_manual else "")
            if cols[4].button("🔄", key=f"recalc_w_{snap.date}", help=t("wealth_history.recalculate_help")):
                with st.spinner(t("wealth_history.recalculating")):
                    try:
                        result = agent.recalculate_snapshot(snap.date)
                    except Exception as e:
                        st.error(str(e))
                        result = None
                if result:
                    if result.missing_pos:
                        msg_text = t("wealth_history.recalculate_success").format(
                            date=snap.date, coverage=f"{result.coverage_pct:.1f}", missing=len(result.missing_pos)
                        )
                    else:
                        msg_text = t("wealth_history.recalculate_success_full").format(
                            date=snap.date, coverage=f"{result.coverage_pct:.1f}"
                        )
                    st.session_state["recalc_result"] = {"ok": True, "text": msg_text}
                else:
                    st.session_state["recalc_result"] = {"ok": False, "text": t("wealth_history.recalculate_no_data")}
                st.rerun()
            if cols[5].button("🗑️", key=f"del_w_{snap.date}", help=t("wealth_history.delete_help")):
                try:
                    agent.delete_snapshot(snap.date)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    else:
        st.info(t("wealth_history.no_data"))

with tab_dividend:
    if dividend_snapshots:
        from state import get_dividend_snapshot_repo as _get_div_repo
        _div_repo = _get_div_repo()
        header = st.columns([2, 2, 2, 1, 1])
        header[0].markdown(f"**{t('wealth_history.date_label')}**")
        header[1].markdown(f"**{t('wealth_history.annual_dividend')}**")
        header[2].markdown(f"**{t('wealth_history.data_coverage')}**")
        header[3].markdown(f"**{t('wealth_history.manual_flag')}**")
        st.divider()
        for snap in reversed(dividend_snapshots):
            cols = st.columns([2, 2, 2, 1, 1])
            cols[0].write(snap.date)
            cols[1].write(f"€ {snap.total_eur:,.0f}")
            cols[2].write(f"{snap.coverage_pct:.1f}%")
            cols[3].write("✓" if snap.is_manual else "")
            if cols[4].button("🗑️", key=f"del_d_{snap.date}", help=t("wealth_history.delete_help")):
                try:
                    _div_repo.delete(snap.id)
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
    else:
        st.info(t("wealth_history.no_data"))
