"""
Dividenden-Kalender — 12-Monats-Cashflow-Prognose aus Portfolio-Dividenden.

Lokal (Ollama). Stateless — kein DB-State.
Berechnet equal-monthly aus annual_dividend_eur (annual / 12 pro Position).
"""

import asyncio
import logging
import threading

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

logger = logging.getLogger(__name__)

from core.dividend_calendar import (
    compute_monthly_cashflow_forecast,
    compute_coverage_pct,
    get_top_contributors,
)
from core.composition_drift import (
    dividend_history_series,
    share_count_series,
    portfolio_income_series,
    value_decomposition_series,
)
from core.i18n import t, current_language
from core.ui.verdicts import cloud_notice
from core.ui.markdown import llm_markdown
from state import (
    get_market_agent,
    get_market_repo,
    get_positions_repo,
    get_dividend_calendar_agent,
    get_app_config_repo,
    get_portfolio_comment_model,
    get_portfolio_comment_service,
    get_wealth_snapshot_repo,
)

st.set_page_config(
    page_title=t("dividend_calendar.title"),
    page_icon="💰",
    layout="wide",
)
st.title(f"💰 {t('dividend_calendar.title')}")
st.caption(t("dividend_calendar.subtitle"))

# ------------------------------------------------------------------
# Data loading
# ------------------------------------------------------------------

_market_agent = get_market_agent()

with st.spinner(t("common.loading")):
    _valuations = _market_agent.get_portfolio_valuation(include_watchlist=False)

_forecasts = compute_monthly_cashflow_forecast(_valuations, months_ahead=12)
_coverage = compute_coverage_pct(_valuations, _forecasts)

_total_annual = sum(
    c.annual_dividend_eur
    for c in (_forecasts[0].contributions if _forecasts else [])
)
_monthly_avg = _total_annual / 12 if _total_annual > 0 else 0.0

# ------------------------------------------------------------------
# No-data guard
# ------------------------------------------------------------------

if not _forecasts or _total_annual == 0:
    st.info(t("dividend_calendar.no_data"))
    st.stop()

# ------------------------------------------------------------------
# Metrics row
# ------------------------------------------------------------------

_portfolio_value = sum((v.current_value_eur or 0) for v in _valuations)
_portfolio_yield = (_total_annual / _portfolio_value * 100) if _portfolio_value > 0 else 0.0

col1, col2, col3, col4 = st.columns(4)
col1.metric(t("dividend_calendar.total_annual"), f"{_total_annual:,.0f} EUR")
col2.metric(t("dividend_calendar.monthly_avg"), f"{_monthly_avg:,.0f} EUR")
col3.metric(t("dividend_calendar.portfolio_yield"), f"{_portfolio_yield:.1f}%")
col4.metric(t("dividend_calendar.coverage"), f"{_coverage:.0f}%")

st.divider()

# ------------------------------------------------------------------
# Pie chart — top contributors
# ------------------------------------------------------------------

st.subheader(t("dividend_calendar.pie_chart_title"))

_top10 = get_top_contributors(_forecasts, top_n=10)
if _top10:
    _top10_total = sum(c.annual_dividend_eur for c in _top10)
    _others = _total_annual - _top10_total

    _labels = [f"{c.name} ({c.symbol})" for c in _top10]
    _values = [c.annual_dividend_eur for c in _top10]
    if _others > 0:
        _labels.append(t("dividend_calendar.others"))
        _values.append(_others)

    _fig_pie = px.pie(names=_labels, values=_values, hole=0.35)
    _fig_pie.update_layout(
        margin=dict(t=20, b=20, l=0, r=0),
        height=360,
        showlegend=True,
        legend=dict(orientation="v", x=1.0, y=0.5),
    )
    _fig_pie.update_traces(textposition="inside", textinfo="percent")
    st.plotly_chart(_fig_pie, use_container_width=True)

st.divider()

# ------------------------------------------------------------------
# Positions table
# ------------------------------------------------------------------

st.subheader(t("dividend_calendar.positions_table"))

if _forecasts and _forecasts[0].contributions:
    _all_positions = {p.name: p for p in get_positions_repo().get_portfolio()}
    _rows = [
        {
            "": "👑" if (_all_positions.get(c.name) and (_all_positions[c.name].extra_data or {}).get("dividend_aristocrat")) else "",
            t("common.name"): f"{c.name} ({c.symbol})",
            t("common.asset_class"): c.asset_class,
            t("dividend_calendar.col_annual"): round(c.annual_dividend_eur, 2),
            t("dividend_calendar.col_monthly"): round(c.monthly_eur, 2),
            t("dividend_calendar.col_yield"): (
                f"{c.dividend_yield_pct * 100:.1f}%"
                if c.dividend_yield_pct
                else "—"
            ),
            t("dividend_calendar.col_source"): c.dividend_source or "—",
        }
        for c in sorted(
            _forecasts[0].contributions,
            key=lambda c: c.annual_dividend_eur,
            reverse=True,
        )
    ]
    st.dataframe(_rows, use_container_width=True, hide_index=True)

st.divider()

# ------------------------------------------------------------------
# Dividend development per position (from snapshot holdings; forward-only)
# ------------------------------------------------------------------

st.subheader(t("dividend_calendar.history_section"))
st.caption(t("dividend_calendar.history_help"))

_snapshots = get_wealth_snapshot_repo().list(days=None) or []
_div_hist = dividend_history_series(_snapshots)
if not _div_hist:
    st.info(t("dividend_calendar.history_building"))
else:
    _current_div = {
        c.symbol: c.annual_dividend_eur
        for c in (_forecasts[0].contributions if _forecasts else [])
    }
    _avail = sorted(_div_hist.keys(), key=lambda tk: _current_div.get(tk, 0.0), reverse=True)
    _labels = {tk: f"{_div_hist[tk]['name']} ({tk})" for tk in _avail}
    _sel = st.multiselect(
        t("dividend_calendar.history_select"),
        options=_avail,
        default=_avail[:5],
        format_func=lambda tk: _labels.get(tk, tk),
    )
    if _sel:
        _fig_hist = go.Figure()
        for tk in _sel:
            _pts = _div_hist[tk]["points"]
            _fig_hist.add_trace(
                go.Scatter(
                    x=[p["date"] for p in _pts],
                    y=[p["annual_dividend_eur"] for p in _pts],
                    mode="lines+markers",
                    name=_labels.get(tk, tk),
                    hovertemplate="<b>%{x}</b><br>%{y:,.0f} €<extra></extra>",
                )
            )
        _fig_hist.update_layout(
            hovermode="x unified", height=400, margin=dict(l=50, r=50, t=20, b=50),
            xaxis_title=t("wealth_history.date_label"),
            yaxis_title=t("dividend_calendar.history_yaxis"),
            template="plotly_white",
        )
        st.plotly_chart(_fig_hist, use_container_width=True)

st.divider()

# ------------------------------------------------------------------
# Accumulation — making the invisible iterations visible (forward-only)
# ------------------------------------------------------------------

st.subheader(t("dividend_calendar.accumulation_section"))

_share_hist = share_count_series(_snapshots)
_income_ts = portfolio_income_series(_snapshots)
_decomp = value_decomposition_series(_snapshots)

if not _share_hist and not _income_ts:
    st.info(t("dividend_calendar.history_building"))
else:
    _cur_div = {
        c.symbol: c.annual_dividend_eur
        for c in (_forecasts[0].contributions if _forecasts else [])
    }

    # --- Share ratchet (per position) ---
    st.markdown(f"**{t('dividend_calendar.shares_section')}**")
    st.caption(t("dividend_calendar.shares_help"))
    if _share_hist:
        _sc_avail = sorted(_share_hist.keys(), key=lambda tk: _cur_div.get(tk, 0.0), reverse=True)
        _sc_labels = {tk: f"{_share_hist[tk]['name']} ({tk})" for tk in _sc_avail}
        _sc_sel = st.multiselect(
            t("dividend_calendar.shares_select"),
            options=_sc_avail,
            default=_sc_avail[:5],
            format_func=lambda tk: _sc_labels.get(tk, tk),
            key="_div_shares_select",
        )
        if _sc_sel:
            _fig_sc = go.Figure()
            for tk in _sc_sel:
                _pts = _share_hist[tk]["points"]
                _fig_sc.add_trace(
                    go.Scatter(
                        x=[p["date"] for p in _pts],
                        y=[p["quantity"] for p in _pts],
                        mode="lines+markers",
                        name=_sc_labels.get(tk, tk),
                        hovertemplate="<b>%{x}</b><br>%{y:,.4g}<extra></extra>",
                    )
                )
            _fig_sc.update_layout(
                hovermode="x unified", height=400, margin=dict(l=50, r=50, t=20, b=50),
                xaxis_title=t("wealth_history.date_label"),
                yaxis_title=t("dividend_calendar.shares_yaxis"),
                template="plotly_white",
            )
            st.plotly_chart(_fig_sc, use_container_width=True)

    # --- Forward income over time (portfolio) ---
    if _income_ts:
        st.markdown(f"**{t('dividend_calendar.income_ts_section')}**")
        st.caption(t("dividend_calendar.income_ts_help"))
        _fig_inc = go.Figure()
        _fig_inc.add_trace(
            go.Scatter(
                x=[p["date"] for p in _income_ts],
                y=[p["total_annual_dividend_eur"] for p in _income_ts],
                mode="lines+markers",
                fill="tozeroy",
                name=t("dividend_calendar.income_ts_section"),
                hovertemplate="<b>%{x}</b><br>%{y:,.0f} €<extra></extra>",
            )
        )
        _fig_inc.update_layout(
            hovermode="x unified", height=360, margin=dict(l=50, r=50, t=20, b=50),
            xaxis_title=t("wealth_history.date_label"),
            yaxis_title=t("dividend_calendar.income_ts_yaxis"),
            template="plotly_white", showlegend=False,
        )
        st.plotly_chart(_fig_inc, use_container_width=True)

    # --- Value decomposition: price vs. share accumulation ---
    if _decomp:
        st.markdown(f"**{t('dividend_calendar.decomp_section')}**")
        st.caption(t("dividend_calendar.decomp_help"))
        _dates = [p["date"] for p in _decomp]
        _fig_dec = go.Figure()
        _fig_dec.add_trace(go.Scatter(
            x=_dates, y=[p["cum_price_effect"] for p in _decomp],
            mode="lines", stackgroup="one", name=t("dividend_calendar.decomp_price"),
            hovertemplate="<b>%{x}</b><br>%{y:,.0f} €<extra></extra>",
        ))
        _fig_dec.add_trace(go.Scatter(
            x=_dates, y=[p["cum_quantity_effect"] for p in _decomp],
            mode="lines", stackgroup="one", name=t("dividend_calendar.decomp_quantity"),
            hovertemplate="<b>%{x}</b><br>%{y:,.0f} €<extra></extra>",
        ))
        _fig_dec.update_layout(
            hovermode="x unified", height=360, margin=dict(l=50, r=50, t=20, b=50),
            xaxis_title=t("wealth_history.date_label"),
            yaxis_title=t("dividend_calendar.decomp_yaxis"),
            template="plotly_white",
        )
        st.plotly_chart(_fig_dec, use_container_width=True)

st.divider()

# ------------------------------------------------------------------
# Dividend data refresh
# ------------------------------------------------------------------

_div_records = get_market_repo().get_all_dividends()
_latest_fetch = (
    max((r.fetched_at for r in _div_records.values() if r.fetched_at), default=None)
    if _div_records
    else None
)

_btn_col, _info_col = st.columns([1, 4])
with _btn_col:
    if st.button("🔄 Dividenden aktualisieren", use_container_width=True):
        with st.spinner("Dividendendaten werden abgerufen..."):
            _errors = _market_agent.fetch_dividends_now()
            if _errors:
                st.warning(f"Fehler bei {len(_errors)} Symbolen: {', '.join(_errors.keys())[:100]}")
            else:
                st.success("Dividendendaten aktualisiert.")
            st.rerun()
with _info_col:
    if _latest_fetch:
        st.caption(f"Zuletzt aktualisiert: {_latest_fetch.strftime('%d.%m.%Y %H:%M')} UTC")

st.divider()

# ------------------------------------------------------------------
# AI Analysis (Ollama, one-shot)
# ------------------------------------------------------------------

st.subheader("🤖 KI-Analyse")
_dc_agent = get_dividend_calendar_agent()
cloud_notice(_dc_agent._llm.model, provider="ollama")

if "_dc_job" not in st.session_state:
    st.session_state["_dc_job"] = {
        "running": False,
        "done": False,
        "error": None,
        "result": None,
    }

_JOB = st.session_state["_dc_job"]


def _run_analysis(agent, forecasts, valuations, language, job):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            agent.analyze(
                forecasts=forecasts,
                valuations=valuations,
                language=language,
            )
        )
        job["result"] = result
        job.update({"running": False, "done": True, "error": None})
    except Exception as exc:
        job.update({"running": False, "done": True, "error": str(exc)})
    finally:
        loop.close()


if not _JOB["running"] and not _JOB["done"]:
    if st.button(t("dividend_calendar.run_analysis"), type="primary"):
        _language = current_language()
        _JOB.update({"running": True, "done": False, "error": None, "result": None})
        _thread = threading.Thread(
            target=_run_analysis,
            args=(_dc_agent, _forecasts, _valuations, _language, _JOB),
            daemon=False,
        )
        _thread.start()
        st.rerun()

if _JOB["running"]:
    with st.spinner(t("dividend_calendar.analysis_running")):
        st.rerun()

if _JOB["done"]:
    if _JOB["error"]:
        st.error(f"{t('common.agent_error')}: {_JOB['error']}")
    elif _JOB["result"]:
        _result = _JOB["result"]
        if _result.summary:
            st.info(f"**Fazit:** {_result.summary}")
        llm_markdown(_result.full_text)
        st.caption(t("common.ai_disclaimer"))

        # KI-Kommentarstil
        from core.ui.ai_comment import render_ai_comment

        render_ai_comment(
            state_key="_dc",
            ctx=f"Dividenden-Portfolio Analyse:\n{_result.full_text}",
            style_id=get_app_config_repo().get("comment_style") or "humorvoll",
            comment_service=get_portfolio_comment_service(get_portfolio_comment_model()),
            section_title=t("dividend_calendar.ai_comment_section"),
        )

    if st.button(t("dividend_calendar.run_analysis") + " ↺"):
        st.session_state["_dc_job"] = {
            "running": False,
            "done": False,
            "error": None,
            "result": None,
        }
        st.rerun()
