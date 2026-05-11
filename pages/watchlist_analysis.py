"""
Watchlist-Analyse — aggregates all 4 sub-check analyses for a single watchlist position.

Shows: Storychecker, Consensus Gap, Fundamental Analyzer, Capital Allocator.
Pre-selection via session_state key 'wla_preselect_pos_id'.
"""

import logging

import pandas as pd
import plotly.express as px
import streamlit as st

from core.i18n import t
from core.ui.verdicts import VERDICT_CONFIGS, verdict_badge, verdict_icon
from state import (
    get_analysis_service,
    get_capital_allocator_repo,
    get_consensus_gap_agent,
    get_fundamental_analyzer_agent,
    get_market_agent,
    get_portfolio_service,
    get_storychecker_agent,
)

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Watchlist-Analyse", page_icon="🔍", layout="wide")
st.title("🔍 Watchlist-Analyse")
st.caption(t("watchlist_analysis.page_subtitle"))

portfolio_service = get_portfolio_service()
analysis_service = get_analysis_service()
ca_repo = get_capital_allocator_repo()
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
    st.warning("Position hat keine ID — keine Analyse verfügbar.")
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
# Helper: render checker card
# ------------------------------------------------------------------

def _render_checker_card(title: str, verdict_obj, config, full_text_fn):
    if verdict_obj is None:
        st.markdown(f"**{title}**")
        st.markdown("_:gray[Noch nicht analysiert]_")
        return

    badge = verdict_badge(verdict_obj.verdict, config)
    st.markdown(f"**{title}** {badge}")
    if verdict_obj.created_at:
        st.caption(verdict_obj.created_at.strftime("%d. %b %Y"))
    if verdict_obj.summary:
        st.markdown(f"_{verdict_obj.summary}_")

    full_text = None
    try:
        full_text = full_text_fn()
    except Exception:
        pass

    if full_text:
        with st.expander(t("capital_allocator.full_analysis"), expanded=False):
            st.markdown(full_text)


# ------------------------------------------------------------------
# Fetch all verdicts
# ------------------------------------------------------------------

sc_verdict = analysis_service.get_verdict(selected_position.id, "storychecker")
cg_verdict = analysis_service.get_verdict(selected_position.id, "consensus_gap")
fa_verdict = analysis_service.get_verdict(selected_position.id, "fundamental_analyzer")
ca_verdict = analysis_service.get_verdict(selected_position.id, "capital_allocator")

sc_agent = get_storychecker_agent()
cg_agent = get_consensus_gap_agent()
fa_agent = get_fundamental_analyzer_agent()

# ------------------------------------------------------------------
# Section: Story, Consensus, Fundamental (3 columns)
# ------------------------------------------------------------------

st.subheader(t("watchlist_analysis.checks_header"))

col1, col2, col3 = st.columns(3)

with col1:
    _render_checker_card(
        "Storychecker",
        sc_verdict,
        VERDICT_CONFIGS["storychecker"],
        lambda: sc_agent.get_messages(sc_verdict.session_id)[-1].content
        if sc_verdict and sc_verdict.session_id else None,
    )

with col2:
    _render_checker_card(
        "Consensus Gap",
        cg_verdict,
        VERDICT_CONFIGS["consensus_gap"],
        lambda: cg_agent.get_messages(cg_verdict.session_id)[-1].content
        if cg_verdict and cg_verdict.session_id else None,
    )

with col3:
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
            st.caption(ca_verdict.created_at.strftime("%d. %b %Y, %H:%M"))
        if ca_verdict.summary:
            st.markdown(f"_{ca_verdict.summary}_")
    with col2:
        icon = verdict_icon(ca_verdict.verdict, VERDICT_CONFIGS["capital_allocator"])
        st.metric(t("capital_allocator.verdict_label"), f"{icon} {ca_verdict.verdict}")

    if ca_verdict.session_id:
        try:
            messages = ca_repo.get_messages(ca_verdict.session_id)
            assistant_msgs = [m for m in messages if m.role == "assistant"]
            if assistant_msgs:
                with st.expander(t("capital_allocator.full_analysis"), expanded=True):
                    st.markdown(assistant_msgs[-1].content)
        except Exception:
            pass
else:
    st.info(t("capital_allocator.no_analysis"))
