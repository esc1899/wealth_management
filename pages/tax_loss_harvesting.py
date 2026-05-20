"""
Tax Loss Harvesting — identifiziert Verlustpositionen für steueroptimiertes Jahresend-Verkaufen.

Lokal (Ollama). Stateless — kein DB-State.
"""

import asyncio
import threading
import time

import streamlit as st

from core.i18n import t, current_language
from core.ui.verdicts import cloud_notice
from state import (
    get_market_agent,
    get_portfolio_service,
    get_analysis_service,
    get_tax_loss_harvesting_agent,
)

st.set_page_config(page_title="Tax Loss Harvesting", page_icon="📉", layout="wide")
st.title(f"📉 {t('tax_loss_harvesting.title')}")

_agent = get_tax_loss_harvesting_agent()
cloud_notice(_agent.model)

# ------------------------------------------------------------------
# Help
# ------------------------------------------------------------------

with st.expander(t("tax_loss_harvesting.help_title"), expanded=False):
    st.markdown(
        t("tax_loss_harvesting.help_text")
    )

# ------------------------------------------------------------------
# Background job state
# ------------------------------------------------------------------

if "_tlh_job" not in st.session_state:
    st.session_state["_tlh_job"] = {
        "running": False,
        "done": False,
        "error": None,
        "result": None,
    }

_JOB = st.session_state["_tlh_job"]


def _run_background(ag, loss_positions, watchlist, verdicts, wash_sale_tickers, language, job):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            ag.analyze(
                loss_positions=loss_positions,
                watchlist_positions=watchlist,
                verdicts=verdicts,
                wash_sale_tickers=wash_sale_tickers,
                language=language,
            )
        )
        job["result"] = result
        job.update({"running": False, "done": True, "error": None})
    except Exception as exc:
        job.update({"running": False, "done": True, "error": str(exc)})
    finally:
        loop.close()


# ------------------------------------------------------------------
# Data loading + filtering
# ------------------------------------------------------------------

_market_agent = get_market_agent()
_portfolio_service = get_portfolio_service()
_analysis_service = get_analysis_service()

_valuations = _market_agent.get_portfolio_valuation()

# ------------------------------------------------------------------
# Threshold slider
# ------------------------------------------------------------------

_threshold = st.slider(
    t("tax_loss_harvesting.threshold_label"),
    min_value=500,
    max_value=5000,
    value=1000,
    step=100,
    format="€%d",
    key="_tlh_threshold",
)

_loss_positions = [
    v for v in _valuations
    if v.pnl_eur is not None and v.pnl_eur < -_threshold and not v.analysis_excluded
]

if not _loss_positions:
    st.info(t("tax_loss_harvesting.no_candidates"))
else:
    st.caption(
        t("tax_loss_harvesting.candidates_found").format(n=len(_loss_positions))
    )

# ------------------------------------------------------------------
# Run button
# ------------------------------------------------------------------

_lang = current_language()

_col_btn, _col_status = st.columns([2, 5])
with _col_btn:
    if st.button(
        t("tax_loss_harvesting.run_button"),
        type="primary",
        disabled=_JOB["running"] or not _loss_positions,
        key="_tlh_run",
    ):
        _watchlist = _portfolio_service.get_watchlist_positions()
        _wl_ids = [p.id for p in _watchlist if p.id]
        _verdicts = _analysis_service.get_all_verdicts(_wl_ids) if _wl_ids else {}

        _portfolio_tickers = {v.symbol for v in _loss_positions if v.symbol}
        _wl_tickers = {p.ticker for p in _watchlist if p.ticker}
        _wash_sale = sorted(_portfolio_tickers & _wl_tickers)

        _JOB.update({"running": True, "done": False, "error": None, "result": None})
        threading.Thread(
            target=_run_background,
            args=(_agent, _loss_positions, _watchlist, _verdicts, _wash_sale, _lang, _JOB),
            daemon=True,
        ).start()
        st.rerun()

with _col_status:
    if _JOB.get("error") and not _JOB["running"]:
        st.error(f"{t('common.agent_error')}: {_JOB['error']}")

if _JOB["running"]:
    st.info(f"⏳ {t('common.loading')}")
    time.sleep(5)
    st.rerun()

# ------------------------------------------------------------------
# Results
# ------------------------------------------------------------------

_RESULT = _JOB.get("result")

if _RESULT is not None:
    st.divider()

    _m1, _m2, _m3 = st.columns(3)
    _m1.metric(t("tax_loss_harvesting.metric_candidates"), _RESULT.candidate_count)
    _m2.metric(t("tax_loss_harvesting.metric_loss"), f"€{_RESULT.total_loss_eur:,.0f}")
    _m3.metric(t("tax_loss_harvesting.metric_tax_benefit"), f"€{_RESULT.total_tax_benefit_eur:,.0f}")

    if _RESULT.wash_sale_tickers:
        st.warning(
            "⚠️ Wash-Sale: " + ", ".join(_RESULT.wash_sale_tickers)
            + " — Ticker sowohl im Verlust-Portfolio als auch auf der Watchlist."
        )

    st.markdown(_RESULT.report_markdown)

    st.download_button(
        label=t("tax_loss_harvesting.download_label"),
        data=_RESULT.report_markdown,
        file_name="tax_loss_harvesting.md",
        mime="text/markdown",
    )
