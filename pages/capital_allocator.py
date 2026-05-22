"""
Capital Allocator — management quality analysis history viewer.

Shows stored CA analyses per position. No new analysis runs here —
runs happen via Watchlist Checker (FEAT-40) or Scheduler.

Pre-selection via session_state key 'ca_preselect_pos_id'.
"""

import logging

import streamlit as st

from core.i18n import t, current_language
from core.ui.verdicts import VERDICT_CONFIGS, verdict_badge, verdict_icon, cloud_notice
from core.ui.markdown import llm_markdown
from state import (
    get_capital_allocator_agent,
    get_capital_allocator_repo,
    get_analysis_service,
    get_portfolio_service,
    get_analyses_repo,
)

logger = logging.getLogger(__name__)

st.set_page_config(page_title="Capital Allocator", page_icon="🏦", layout="wide")
st.title("🏦 Capital Allocator")
st.caption(t("capital_allocator.page_subtitle"))

agent = get_capital_allocator_agent()
ca_repo = get_capital_allocator_repo()
analysis_service = get_analysis_service()
portfolio_service = get_portfolio_service()
analyses_repo = get_analyses_repo()

cloud_notice(agent.model)

_VERDICT_CONFIG = VERDICT_CONFIGS.get("capital_allocator", {})

# ------------------------------------------------------------------
# Load positions (portfolio + watchlist, ticker required)
# ------------------------------------------------------------------

all_positions = portfolio_service.get_public_positions(
    include_portfolio=False, include_watchlist=True, require_ticker=True
)

if not all_positions:
    st.info("📭 Keine Watchlist-Positionen mit Ticker vorhanden.")
    st.stop()

# ------------------------------------------------------------------
# Position selector (with pre-selection from session_state)
# ------------------------------------------------------------------

preselect_id = st.session_state.pop("ca_preselect_pos_id", None)

position_display = {f"{p.name} ({p.ticker})": p for p in all_positions}
position_names = list(position_display.keys())

default_idx = 0
if preselect_id is not None:
    for i, p in enumerate(all_positions):
        if p.id == preselect_id:
            default_idx = i
            break

selected_display = st.selectbox(
    t("capital_allocator.select_position"),
    options=position_names,
    index=default_idx,
)
selected_position = position_display[selected_display]

if not selected_position.id:
    st.warning("Position hat keine ID — keine Analyse verfügbar.")
    st.stop()

# ------------------------------------------------------------------
# Load CA analyses for selected position
# ------------------------------------------------------------------

all_sessions = ca_repo.list_sessions(limit=200)
pos_sessions = [s for s in all_sessions if s.position_id == selected_position.id]

_all_pos_analyses = analyses_repo.get_for_position(selected_position.id, limit=50)
all_analyses = [a for a in _all_pos_analyses if a.agent == "capital_allocator"]

if not pos_sessions and not all_analyses:
    st.info(t("capital_allocator.no_analysis"))
    st.stop()

# ------------------------------------------------------------------
# Latest analysis card
# ------------------------------------------------------------------

latest_verdict = analysis_service.get_verdict(selected_position.id, "capital_allocator")

st.divider()
st.subheader(t("capital_allocator.latest_analysis"))

if latest_verdict:
    badge = verdict_badge(latest_verdict.verdict, _VERDICT_CONFIG)
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(f"### {selected_position.name} {badge}")
        if selected_position.ticker:
            st.caption(f"`{selected_position.ticker}`")
        if latest_verdict.created_at:
            st.caption(latest_verdict.created_at.strftime("%d. %b %Y, %H:%M"))
    with col2:
        icon = verdict_icon(latest_verdict.verdict, _VERDICT_CONFIG)
        st.metric(t("capital_allocator.verdict_label"), f"{icon} {latest_verdict.verdict}")

    if latest_verdict.summary:
        llm_markdown(f"_{latest_verdict.summary}_")

    # Full analysis text from the latest session's assistant message
    if latest_verdict.session_id and pos_sessions:
        latest_session = next((s for s in pos_sessions if s.id == latest_verdict.session_id), None)
        if latest_session is None:
            latest_session = pos_sessions[0]
        messages = ca_repo.get_messages(latest_session.id)
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        if assistant_msgs:
            with st.expander(t("capital_allocator.full_analysis"), expanded=True):
                llm_markdown(assistant_msgs[-1].content)
else:
    st.info(t("capital_allocator.no_analysis"))

# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------

if len(all_analyses) > 1:
    st.divider()
    with st.expander(f"📋 {t('capital_allocator.history')} ({len(all_analyses) - 1})", expanded=False):
        for analysis in all_analyses[1:]:
            session = next((s for s in pos_sessions if s.id == analysis.session_id), None)
            icon = verdict_icon(analysis.verdict, _VERDICT_CONFIG)
            ts = analysis.created_at.strftime("%d. %b %Y, %H:%M") if analysis.created_at else "—"
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{ts}** — {analysis.skill_name or 'Standard'}")
                if analysis.summary:
                    st.caption(analysis.summary)
            with col2:
                st.markdown(f"{icon} {analysis.verdict}")

            if session:
                messages = ca_repo.get_messages(session.id)
                assistant_msgs = [m for m in messages if m.role == "assistant"]
                if assistant_msgs:
                    with st.expander("Vollständige Analyse", expanded=False):
                        llm_markdown(assistant_msgs[-1].content)
            st.divider()
