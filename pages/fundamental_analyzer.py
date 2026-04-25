"""
Fundamental Analyzer — in-depth analysis of individual positions via chat.

Cloud ☁️ agent: analyzes valuation, business quality, competitive position, risks.
Interactive chat interface for following up on specific questions.
"""

import asyncio
import threading
import time

import streamlit as st

from core.i18n import t, current_language
from core.ui.verdicts import cloud_notice
from state import get_analyses_repo, get_fundamental_analyzer_agent, get_portfolio_service

st.set_page_config(page_title="Fundamental Analyzer", page_icon="📊", layout="wide")
st.title(f"📊 {t('fundamental.title')}")
st.caption(t("fundamental.subtitle"))

agent = get_fundamental_analyzer_agent()
analyses_repo = get_analyses_repo()
cloud_notice(agent.model)

with st.expander(t("fundamental.how_to_use"), expanded=False):
    st.markdown(t("fundamental.how_to_use_text"))

# ------------------------------------------------------------------
# Load data
# ------------------------------------------------------------------

portfolio_service = get_portfolio_service()
all_positions = portfolio_service.get_public_positions(
    include_portfolio=True, include_watchlist=True
)
positions_with_required_fields = [p for p in all_positions if p.name]

# ------------------------------------------------------------------
# Layout: left control panel | right chat
# ------------------------------------------------------------------

col_left, col_right = st.columns([0.8, 2.2], gap="medium")

# ------------------------------------------------------------------
# Left: position selection + past sessions
# ------------------------------------------------------------------

with col_left:
    st.subheader(t("fundamental.select_header"))

    if not positions_with_required_fields:
        st.warning(t("fundamental.no_positions"))
        st.stop()
    else:
        pos_labels = [
            f"{p.name} ({p.ticker})" if p.ticker else p.name
            for p in positions_with_required_fields
        ]

        with st.form("new_analysis_form"):
            selected_idx = st.selectbox(
                t("fundamental.position_label"),
                options=range(len(positions_with_required_fields)),
                format_func=lambda i: pos_labels[i],
            )
            selected_position = positions_with_required_fields[selected_idx]

            submitted = st.form_submit_button(t("fundamental.start_button"), use_container_width=True, type="primary")

        # Show position details as reference
        if selected_position:
            with st.expander(f"📋 {selected_position.name}", expanded=False):
                if selected_position.ticker:
                    st.caption(f"{t('fundamental.ticker_label')} {selected_position.ticker}")
                if selected_position.asset_class:
                    st.caption(f"{t('fundamental.asset_class_label')} {selected_position.asset_class}")
                if selected_position.anlageart:
                    st.caption(f"{t('fundamental.investment_type_label')} {selected_position.anlageart}")
                if selected_position.story:
                    st.caption(t("fundamental.thesis_label"))
                    st.markdown(selected_position.story)

        # Past analyses
        past_sessions = agent.list_sessions(limit=5)
        if past_sessions:
            with st.expander("📊 Letzte Analysen", expanded=False):
                for s in past_sessions:
                    date_str = ""
                    if s.messages and len(s.messages) > 0:
                        date_str = " · gerade eben"
                    btn_label = f"📊 **{s.position_name}**{date_str}"
                    active = st.session_state.get("fa_session_id") == s.id
                    if st.button(
                        btn_label,
                        key=f"fa_sess_{s.id}",
                        use_container_width=True,
                        type="primary" if active else "secondary",
                    ):
                        st.session_state["fa_session_id"] = s.id
                        st.rerun()

        if st.session_state.get("fa_start_error"):
            st.error(t("fundamental.start_error").format(error=st.session_state.pop('fa_start_error')))

        if submitted:
            with st.spinner(t("fundamental.starting")):
                try:
                    # Clear old session if position changed
                    current_session = agent.get_session(st.session_state.get("fa_session_id")) if st.session_state.get("fa_session_id") else None
                    if current_session and current_session.position_id != selected_position.id:
                        st.session_state.pop("fa_session_id", None)

                    session = agent.start_session(position=selected_position, language=current_language())
                    st.session_state["fa_session_id"] = session.id
                except Exception as exc:
                    st.session_state["fa_start_error"] = str(exc)
            st.rerun()

# ------------------------------------------------------------------
# Right: chat interface
# ------------------------------------------------------------------

with col_right:
    session_id = st.session_state.get("fa_session_id")

    if session_id is None:
        st.info(t("fundamental.select_prompt"))
    else:
        session = agent.get_session(session_id)
        if session is None:
            st.warning(t("fundamental.session_not_found"))
            st.session_state.pop("fa_session_id", None)
        else:
            st.markdown(f"### {session.position_name}")
            if session.ticker:
                st.caption(f"`{session.ticker}`")

            messages = agent.get_messages(session_id)
            for msg in messages:
                if msg["role"] == "user":
                    # Skip the initial verbose system message (first user message)
                    if len(messages) > 1 and msg == messages[0]:
                        continue
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
                    if msg["role"] == "assistant":
                        st.caption(t("fundamental.web_search_info"))

            if prompt := st.chat_input(t("fundamental.chat_placeholder")):
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner(t("fundamental.analyzing")):
                        try:
                            response = agent.chat(session_id, prompt)
                        except Exception as exc:
                            response = t("fundamental.start_error").format(error=str(exc))
                    st.markdown(response)
                    st.caption(t("fundamental.web_search_info"))
                st.rerun()
