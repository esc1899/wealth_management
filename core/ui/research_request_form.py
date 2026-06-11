"""
Reusable research request form (FEAT-54).

Creates an open research request in the queue that Claude Code picks up
via the UserPromptSubmit hook / get_research_queue() MCP tool.

Used by:
  - pages/position_dashboard.py — ticker fixed to the selected position
  - pages/research_answers.py — free-text ticker for general questions
"""

from __future__ import annotations

from typing import Optional

import streamlit as st

from core.i18n import t

REQUEST_TYPES = [
    "research_question",
    "analysis_deepdive",
    "watchlist_candidate",
    "general",
]


def render_research_request_form(
    rq_repo,
    *,
    ticker: Optional[str] = None,
    show_ticker_field: bool = False,
    key_prefix: str = "",
) -> None:
    """Render the research request form.

    With show_ticker_field=True an optional free-text ticker input is shown
    (pre-filled with `ticker` if given). Otherwise `ticker` is attached to
    the request as-is.
    """
    st.subheader(t("research_request.header"))
    st.caption(t("research_request.caption"))

    with st.form(f"{key_prefix}research_request_form", clear_on_submit=True):
        focus = st.text_area(
            t("research_request.focus_label"),
            placeholder=t("research_request.focus_placeholder"),
            height=80,
            max_chars=500,
        )
        req_type = st.selectbox(
            t("research_request.type_label"),
            REQUEST_TYPES,
            format_func=lambda x: t(f"research_request.type_{x}"),
        )
        ticker_input = None
        if show_ticker_field:
            ticker_input = st.text_input(
                t("research_request.ticker_label"),
                value=ticker or "",
                placeholder=t("research_request.ticker_placeholder"),
                max_chars=20,
            )
        context = st.text_input(
            t("research_request.context_label"),
            placeholder=t("research_request.context_placeholder"),
            max_chars=200,
        )
        submitted = st.form_submit_button(
            t("research_request.submit_btn"), type="primary"
        )

    if not submitted:
        return
    if not focus.strip():
        st.warning(t("research_request.focus_required"))
        return

    if show_ticker_field:
        effective_ticker = (ticker_input or "").strip().upper() or None
    else:
        effective_ticker = (ticker or "").strip() or None

    rq_repo.create_request(
        focus=focus.strip(),
        request_type=req_type,
        ticker=effective_ticker,
        context=context.strip() or None,
        source="manual",
    )
    if effective_ticker:
        st.success(
            t("research_request.created_success_ticker").format(ticker=effective_ticker)
        )
    else:
        st.success(t("research_request.created_success"))
