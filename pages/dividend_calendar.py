"""
Dividenden-Kalender — 12-Monats-Cashflow-Prognose aus Portfolio-Dividenden.

Lokal (Ollama). Stateless — kein DB-State.
Berechnet equal-monthly aus annual_dividend_eur (annual / 12 pro Position).
"""

import asyncio
import logging
import threading

import plotly.express as px
import streamlit as st

logger = logging.getLogger(__name__)

from core.dividend_calendar import (
    compute_monthly_cashflow_forecast,
    compute_coverage_pct,
    get_top_contributors,
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

col1, col2, col3 = st.columns(3)
col1.metric(t("dividend_calendar.total_annual"), f"{_total_annual:,.0f} EUR")
col2.metric(t("dividend_calendar.monthly_avg"), f"{_monthly_avg:,.0f} EUR")
col3.metric(t("dividend_calendar.coverage"), f"{_coverage:.0f}%")

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
