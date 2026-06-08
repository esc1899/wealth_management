"""
Watchlist-Analyse — aggregates all 5 sub-check analyses for a single watchlist position.

Shows: Storychecker, Consensus Gap, Fundamental Analyzer, Capital Allocator, Devil's Advocate.
Pre-selection via session_state key 'wla_preselect_pos_id'.
"""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

from config import config
from core.background_jobs import (
    run_capital_allocator_job,
    run_consensus_gap_job,
    run_devils_advocate_job,
    run_fundamental_job,
    run_storychecker_job,
)
from core.i18n import current_language, t
from core.ui.verdicts import VERDICT_CONFIGS, verdict_badge, verdict_icon
from core.ui.markdown import llm_markdown
from state import (
    get_analysis_service,
    get_capital_allocator_repo,
    get_consensus_gap_agent,
    get_devils_advocate_agent,
    get_devils_advocate_repo,
    get_fundamental_analyzer_agent,
    get_market_agent,
    get_portfolio_service,
    get_storychecker_agent,
)

logger = logging.getLogger(__name__)

_STALE_DAYS = 7

st.set_page_config(page_title="Watchlist-Analyse", page_icon="🔍", layout="wide")
st.title("🔍 Watchlist-Analyse")
st.caption(t("watchlist_analysis.page_subtitle"))

portfolio_service = get_portfolio_service()
analysis_service = get_analysis_service()
ca_repo = get_capital_allocator_repo()
da_repo = get_devils_advocate_repo()
market_agent = get_market_agent()

# ------------------------------------------------------------------
# Load watchlist positions
# ------------------------------------------------------------------

all_positions = portfolio_service.get_public_positions(
    include_portfolio=False, include_watchlist=True, require_ticker=False
)

if not all_positions:
    st.info(t("watchlist_analysis.no_positions"))
    st.stop()

# ------------------------------------------------------------------
# Position selector (with pre-selection from session_state)
# ------------------------------------------------------------------

preselect_id = st.session_state.pop("wla_preselect_pos_id", None)

position_display = {
    f"{p.name} ({p.ticker})" if p.ticker else p.name: p
    for p in all_positions
}
position_names = list(position_display.keys())

default_idx = 0
if preselect_id is not None:
    for i, p in enumerate(all_positions):
        if p.id == preselect_id:
            default_idx = i
            break

selected_display = st.selectbox(
    t("watchlist_analysis.select_position"),
    options=position_names,
    index=default_idx,
)
selected_position = position_display[selected_display]

if not selected_position.id:
    st.warning(t("watchlist_analysis.no_position_id"))
    st.stop()

st.divider()

# ------------------------------------------------------------------
# Price History
# ------------------------------------------------------------------

if selected_position.ticker:
    st.subheader(t("analysis.price_history"))
    history = market_agent.get_historical(selected_position.ticker, days=365)
    if history:
        col_date = t("common.date")
        col_price = t("market_data.price_col")
        df_hist = pd.DataFrame(
            [{col_date: h.date, col_price: h.close_eur} for h in history]
        )
        fig = px.line(df_hist, x=col_date, y=col_price,
                      title=f"{selected_position.ticker} — letztes Jahr")
        fig.update_layout(margin=dict(t=40))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(t("analysis.no_history"))
    st.divider()

# ------------------------------------------------------------------
# Helper: staleness check
# ------------------------------------------------------------------

def _verdict_age_days(verdict_obj) -> "int | None":
    if verdict_obj is None or verdict_obj.created_at is None:
        return None
    now = datetime.now(timezone.utc)
    created = verdict_obj.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (now - created).days


def _is_stale(verdict_obj) -> bool:
    age = _verdict_age_days(verdict_obj)
    return age is None or age >= _STALE_DAYS


# ------------------------------------------------------------------
# Helper: render checker card
# ------------------------------------------------------------------

def _render_checker_card(title: str, verdict_obj, config_vc, full_text_fn):
    with st.container():
        if verdict_obj is None:
            st.markdown(f"**{title}**")
            st.markdown(f"_:gray[{t('watchlist_analysis.not_yet_analyzed')}]_")
            return

        badge = verdict_badge(verdict_obj.verdict, config_vc)
        title_col, date_col = st.columns([5, 1])
        with title_col:
            st.markdown(f"**{title}** {badge}")
        with date_col:
            if verdict_obj.created_at:
                age = _verdict_age_days(verdict_obj)
                date_str = verdict_obj.created_at.strftime("%d. %b %Y")
                if age is not None and age >= _STALE_DAYS:
                    st.caption(f":orange[{date_str} · {t('watchlist_analysis.stale_label')}]")
                else:
                    st.caption(date_str)

        if verdict_obj.summary:
            llm_markdown(f"_{verdict_obj.summary}_")

        full_text = None
        try:
            full_text = full_text_fn()
        except Exception:
            pass

        if full_text:
            with st.expander(t("capital_allocator.full_analysis"), expanded=False):
                llm_markdown(full_text)


# ------------------------------------------------------------------
# Fetch all verdicts
# ------------------------------------------------------------------

sc_verdict = analysis_service.get_verdict(selected_position.id, "storychecker")
cg_verdict = analysis_service.get_verdict(selected_position.id, "consensus_gap")
fa_verdict = analysis_service.get_verdict(selected_position.id, "fundamental_analyzer")
ca_verdict = analysis_service.get_verdict(selected_position.id, "capital_allocator")
da_verdict = analysis_service.get_verdict(selected_position.id, "devils_advocate")

sc_agent = get_storychecker_agent()
cg_agent = get_consensus_gap_agent()
fa_agent = get_fundamental_analyzer_agent()
da_agent = get_devils_advocate_agent()

# ------------------------------------------------------------------
# Update button
# ------------------------------------------------------------------

_stale_count = sum(_is_stale(v) for v in [sc_verdict, cg_verdict, fa_verdict, ca_verdict, da_verdict])
_btn_label = (
    t("watchlist_analysis.update_button_stale").format(n=_stale_count)
    if _stale_count > 0
    else t("watchlist_analysis.update_button")
)
_btn_type = "primary" if _stale_count > 0 else "secondary"

if st.button(_btn_label, key="wla_update_btn", type=_btn_type):
    _lang = current_language()
    _pos = [selected_position]
    _args = (config.DB_PATH, config.ENCRYPTION_KEY, config.LLM_API_KEY)
    _errors: list[str] = []
    _states = []

    for _fn in [run_storychecker_job, run_consensus_gap_job, run_fundamental_job, run_capital_allocator_job, run_devils_advocate_job]:
        _j = {"running": True, "done": False, "count": 0, "error": None}
        threading.Thread(target=_fn, args=(_pos, _lang, _j) + _args, daemon=True).start()
        _states.append(_j)

    with st.spinner(t("watchlist_checker.running_parallel_spinner").format(n=5)):
        while any(j["running"] for j in _states):
            time.sleep(1)

    _errors = [f"Fehler bei Analyse {i+1}: {j['error']}" for i, j in enumerate(_states) if j["error"]]
    if _errors:
        for _e in _errors:
            st.error(_e)
    else:
        st.toast(t("watchlist_analysis.update_done"), icon="✅")
    st.rerun()

st.divider()

# ------------------------------------------------------------------
# Section: Story, Consensus, Fundamental (3 columns)
# ------------------------------------------------------------------

st.subheader(t("watchlist_analysis.checks_header"))

_render_checker_card(
    "Storychecker",
    sc_verdict,
    VERDICT_CONFIGS["storychecker"],
    lambda: sc_agent.get_messages(sc_verdict.session_id)[-1].content
    if sc_verdict and sc_verdict.session_id else None,
)

st.write("")

_render_checker_card(
    "Consensus Gap",
    cg_verdict,
    VERDICT_CONFIGS["consensus_gap"],
    lambda: cg_agent.get_messages(cg_verdict.session_id)[-1].content
    if cg_verdict and cg_verdict.session_id else None,
)

st.write("")

_render_checker_card(
    "Fundamental Analyzer",
    fa_verdict,
    VERDICT_CONFIGS["fundamental_analyzer"],
    lambda: fa_agent.get_messages(fa_verdict.session_id)[-1].content
    if fa_verdict and fa_verdict.session_id else None,
)

st.divider()

# ------------------------------------------------------------------
# Section: Capital Allocator (full-width, richer text)
# ------------------------------------------------------------------

st.subheader(t("watchlist_analysis.ca_header"))

if ca_verdict:
    badge = verdict_badge(ca_verdict.verdict, VERDICT_CONFIGS["capital_allocator"])
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"### {badge} {ca_verdict.verdict}")
        if ca_verdict.created_at:
            age = _verdict_age_days(ca_verdict)
            date_str = ca_verdict.created_at.strftime("%d. %b %Y, %H:%M")
            if age is not None and age >= _STALE_DAYS:
                st.caption(f":orange[{date_str} · {t('watchlist_analysis.stale_label')}]")
            else:
                st.caption(date_str)
        if ca_verdict.summary:
            llm_markdown(f"_{ca_verdict.summary}_")
    with col2:
        icon = verdict_icon(ca_verdict.verdict, VERDICT_CONFIGS["capital_allocator"])
        st.metric(t("capital_allocator.verdict_label"), f"{icon} {ca_verdict.verdict}")

    if ca_verdict.session_id:
        try:
            messages = ca_repo.get_messages(ca_verdict.session_id)
            assistant_msgs = [m for m in messages if m.role == "assistant"]
            if assistant_msgs:
                with st.expander(t("capital_allocator.full_analysis"), expanded=True):
                    llm_markdown(assistant_msgs[-1].content)
        except Exception:
            pass
else:
    st.info(t("capital_allocator.no_analysis"))

st.divider()

# ------------------------------------------------------------------
# Section: Devil's Advocate (full-width)
# ------------------------------------------------------------------

st.subheader(t("devils_advocate.da_header"))

if da_verdict:
    badge = verdict_badge(da_verdict.verdict, VERDICT_CONFIGS["devils_advocate"])
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"### {badge}")
        if da_verdict.created_at:
            age = _verdict_age_days(da_verdict)
            date_str = da_verdict.created_at.strftime("%d. %b %Y, %H:%M")
            if age is not None and age >= _STALE_DAYS:
                st.caption(f":orange[{date_str} · {t('watchlist_analysis.stale_label')}]")
            else:
                st.caption(date_str)
        if da_verdict.summary:
            llm_markdown(f"_{da_verdict.summary}_")
    with col2:
        icon = verdict_icon(da_verdict.verdict, VERDICT_CONFIGS["devils_advocate"])
        st.metric(t("devils_advocate.verdict_label"), f"{icon} {da_verdict.verdict}")

    if da_verdict.session_id:
        try:
            messages = da_repo.get_messages(da_verdict.session_id)
            assistant_msgs = [m for m in messages if m.role == "assistant"]
            if assistant_msgs:
                with st.expander(t("devils_advocate.full_analysis"), expanded=True):
                    llm_markdown(assistant_msgs[-1].content)
        except Exception:
            pass
else:
    st.info(t("devils_advocate.no_analysis"))
