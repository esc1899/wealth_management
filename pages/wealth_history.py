"""
Wealth History page — displays portfolio wealth and dividend income over time.
Combines automatic snapshots taken after each market data refresh into charts and tables.
"""

import streamlit as st
import plotly.graph_objects as go
from datetime import datetime

from core.i18n import t
from core.composition_drift import concentration_series, asset_class_mix_series, sold_positions_summary
from core.portfolio_twr import (
    portfolio_twr_series,
    benchmark_twr_series,
    drawdown_series,
    volatility_annualized,
)
from core.constants import BENCHMARK_SYMBOL_KEY as _BENCHMARK_SYMBOL_KEY, DEFAULT_BENCHMARK_SYMBOL as _DEFAULT_BENCHMARK_SYMBOL
from state import (
    get_wealth_snapshot_agent,
    get_dividend_snapshot_repo,
    get_market_agent,
    get_market_repo,
    get_app_config_repo,
)


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
            skipped = len(summary.get("skipped_legacy", []))
            if skipped:
                text += " " + t("wealth_history.rebuild_skipped").format(skipped=skipped)
            issues = len(summary["low_coverage_dates"]) + len(summary["missing_dates"])
            if issues:
                text += " " + t("wealth_history.rebuild_issues").format(
                    low=len(summary["low_coverage_dates"]), missing=len(summary["missing_dates"])
                )
            st.session_state["wh_msg"] = {"kind": "warning" if (issues or skipped) else "success", "text": text}
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
    latest = wealth_snapshots[-1]

    _eod_change = agent.compute_eod_day_change()
    col_date, col_total, col_day, col_coverage = st.columns(4)

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
    with col_day:
        if _eod_change is not None:
            _day_eur, _prev_eod = _eod_change
            _day_pct = (_day_eur / _prev_eod * 100) if _prev_eod else None
            _delta_str = f"{_day_pct:+.2f}%" if _day_pct is not None else None
            st.metric(
                label=t("wealth_history.day_change"),
                value=f"€ {_day_eur:+,.0f}",
                delta=_delta_str,
            )
        else:
            st.metric(label=t("wealth_history.day_change"), value="—")
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

    # Optional: relative asset-class mix (%) over time — complements the absolute stack
    if st.checkbox(t("wealth_history.mix_pct_section")):
        mix_dates, mix = asset_class_mix_series(wealth_snapshots)
        fig_mix = go.Figure()
        for asset_class, series in mix.items():
            fig_mix.add_trace(
                go.Scatter(
                    x=mix_dates,
                    y=series,
                    mode="lines",
                    name=asset_class,
                    stackgroup="one",
                    hovertemplate="<b>%{x}</b><br>" + asset_class + ": %{y:.1f}%<extra></extra>",
                )
            )
        fig_mix.update_layout(
            hovermode="x unified", height=400, margin=dict(l=50, r=50, t=20, b=50),
            xaxis_title=t("wealth_history.date_label"), yaxis_title="%", template="plotly_white",
        )
        st.plotly_chart(fig_mix, use_container_width=True)

    # Optional: position concentration over time (from holdings; forward-only)
    if st.checkbox(t("wealth_history.concentration_section"), help=t("wealth_history.concentration_help")):
        conc = concentration_series(wealth_snapshots)
        if not conc:
            st.info(t("wealth_history.concentration_building"))
        else:
            conc_dates = [r["date"] for r in conc]
            fig_conc = go.Figure()
            for key, top_n in (("top1_pct", 1), ("top3_pct", 3), ("top5_pct", 5)):
                fig_conc.add_trace(
                    go.Scatter(
                        x=conc_dates,
                        y=[r[key] for r in conc],
                        mode="lines",
                        name=t("wealth_history.concentration_top").format(n=top_n),
                        hovertemplate="<b>%{x}</b><br>%{y:.1f}%<extra></extra>",
                    )
                )
            fig_conc.update_layout(
                hovermode="x unified", height=350, margin=dict(l=50, r=50, t=20, b=50),
                xaxis_title=t("wealth_history.date_label"), yaxis_title="%", template="plotly_white",
            )
            st.plotly_chart(fig_conc, use_container_width=True)
            latest = conc[-1]
            st.caption(t("wealth_history.concentration_hhi").format(
                hhi=f"{latest['hhi']:.3f}", n=f"{latest['effective_n']:.1f}"))

    # Positions no longer held — make the survivorship blind spot visible (forward-only)
    _sold = sold_positions_summary(wealth_snapshots)
    st.markdown(f"#### {t('wealth_history.sold_section')}")
    st.caption(t("wealth_history.sold_help"))
    if not _sold:
        st.info(t("wealth_history.sold_building"))
    else:
        _sold_rows = [
            {
                t("common.name"): f"{r['name']} ({r['ticker']})",
                t("wealth_history.sold_col_period"): f"{r['first_date']} – {r['last_date']}",
                t("wealth_history.sold_col_last_value"): (
                    round(r["last_value_eur"], 2) if r["last_value_eur"] is not None else None
                ),
                t("wealth_history.sold_col_change"): (
                    f"{r['price_change_pct']:+.1f}%" if r["price_change_pct"] is not None else "—"
                ),
            }
            for r in _sold
        ]
        st.dataframe(_sold_rows, use_container_width=True, hide_index=True)

    # ── Return vs. benchmark — time-weighted, cashflow-immune (FEAT-73) ──────────
    st.markdown(f"#### {t('wealth_history.twr_section')}")
    st.caption(t("wealth_history.twr_help"))

    _market_repo = get_market_repo()
    twr = portfolio_twr_series(
        wealth_snapshots,
        price_at=lambda tk, d: _market_repo.get_price_for_date_or_prior(tk, d),
    )
    if len(twr) < 2:
        st.info(t("wealth_history.twr_building"))
    else:
        # Benchmark symbol — shared setting with Verdict Hindsight
        _cfg_repo = get_app_config_repo()
        _bench_symbol = (_cfg_repo.get(_BENCHMARK_SYMBOL_KEY) or _DEFAULT_BENCHMARK_SYMBOL).upper()
        _bc1, _bc2 = st.columns([2, 1])
        _new_symbol = _bc1.text_input(
            t("wealth_history.twr_bench_label"), value=_bench_symbol
        ).strip().upper()
        if _new_symbol and _new_symbol != _bench_symbol:
            _cfg_repo.set(_BENCHMARK_SYMBOL_KEY, _new_symbol)
            _bench_symbol = _new_symbol

        _twr_dates = [p["date"] for p in twr]
        # Benchmark must reach into our TWR window — stale index history (latest close
        # before the first holdings snapshot) would collapse to a flat 0% line.
        _bench_hist = _market_repo.get_historical(_bench_symbol, days=800)
        _latest_bench = str(_bench_hist[-1].date) if _bench_hist else None
        _bench_stale = (_latest_bench is None) or (_latest_bench < _twr_dates[0])
        if _bench_stale:
            _msg_key = "twr_bench_no_history" if _latest_bench is None else "twr_bench_stale"
            st.warning(t(f"wealth_history.{_msg_key}").format(
                symbol=_bench_symbol, latest=_latest_bench, start=_twr_dates[0]))
            if _bc2.button(t("wealth_history.twr_bench_load"), use_container_width=True):
                with st.spinner(t("wealth_history.twr_bench_loading").format(symbol=_bench_symbol)):
                    _n = get_market_agent().fetch_historical_for_symbol(_bench_symbol)
                st.session_state["wh_msg"] = {
                    "kind": "success",
                    "text": t("wealth_history.twr_bench_loaded").format(n=_n, symbol=_bench_symbol),
                }
                st.rerun()
            bench = None
        else:
            bench = benchmark_twr_series(
                _twr_dates,
                lambda d, _s=_bench_symbol: _market_repo.get_price_for_date_or_prior(_s, d, 7),
            )

        _port_last = twr[-1]["twr_pct"]
        _dd_points, _max_dd = drawdown_series(twr)
        _vol = volatility_annualized(twr)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(t("wealth_history.twr_metric_portfolio"), f"{_port_last:+.1f} %")
        if bench is not None and bench[-1]["twr_pct"] is not None:
            _bench_last = bench[-1]["twr_pct"]
            m2.metric(t("wealth_history.twr_metric_index"), f"{_bench_last:+.1f} %")
            m3.metric(
                t("wealth_history.twr_metric_excess"),
                f"{_port_last - _bench_last:+.1f} %",
                help=t("wealth_history.twr_excess_help"),
            )
        else:
            m2.metric(t("wealth_history.twr_metric_index"), "—")
            m3.metric(t("wealth_history.twr_metric_excess"), "—")
        m4.metric(
            t("wealth_history.twr_metric_vol"),
            f"{_vol:.1f} %" if _vol is not None else t("wealth_history.twr_maturing"),
            help=t("wealth_history.twr_vol_help"),
        )

        fig_twr = go.Figure()
        fig_twr.add_trace(
            go.Scatter(
                x=_twr_dates, y=[p["twr_pct"] for p in twr], mode="lines+markers",
                name=t("wealth_history.twr_metric_portfolio"),
                line=dict(color="#1f77b4", width=2),
                hovertemplate="<b>%{x|%d.%m.%Y}</b><br>%{y:+.1f} %<extra></extra>",
            )
        )
        if bench is not None:
            fig_twr.add_trace(
                go.Scatter(
                    x=_twr_dates, y=[p["twr_pct"] for p in bench], mode="lines",
                    name=f"{_bench_symbol}",
                    line=dict(color="#888888", width=2, dash="dash"),
                    hovertemplate="<b>%{x|%d.%m.%Y}</b><br>%{y:+.1f} %<extra></extra>",
                )
            )
        fig_twr.update_layout(
            hovermode="x unified", height=380, margin=dict(l=50, r=50, t=20, b=50),
            xaxis_title=t("wealth_history.date_label"), yaxis_title="%", template="plotly_white",
            xaxis_tickformat="%d.%m.%Y",
        )
        st.plotly_chart(fig_twr, use_container_width=True)

        # Drawdown (underwater) — optional, from the cashflow-immune TWR index
        if st.checkbox(t("wealth_history.twr_drawdown_section"),
                       help=t("wealth_history.twr_drawdown_help")):
            st.caption(t("wealth_history.twr_max_drawdown").format(dd=f"{_max_dd:.1f}"))
            fig_dd = go.Figure()
            fig_dd.add_trace(
                go.Scatter(
                    x=[p["date"] for p in _dd_points], y=[p["drawdown_pct"] for p in _dd_points],
                    mode="lines", fill="tozeroy", line=dict(color="#cf222e", width=1),
                    hovertemplate="<b>%{x|%d.%m.%Y}</b><br>%{y:.1f} %<extra></extra>",
                )
            )
            fig_dd.update_layout(
                hovermode="x unified", height=300, margin=dict(l=50, r=50, t=20, b=50),
                xaxis_title=t("wealth_history.date_label"), yaxis_title="%", template="plotly_white",
                xaxis_tickformat="%d.%m.%Y",
            )
            st.plotly_chart(fig_dd, use_container_width=True)

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
