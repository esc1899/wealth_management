"""
Research Answers — answers submitted via MCP from Claude Code.

Shows non-watchlist research results: factual answers, deep-dive analyses,
follow-up findings. Read-only (watchlist proposals go to Research Inbox).

Sections:
  1. Open Requests — pending research queue items
  2. Answers — submitted answers, filterable by ticker
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from core.i18n import t
from core.ui.markdown import llm_markdown
from core.ui.research_request_form import render_research_request_form
from state import get_portfolio_service, get_research_queue_repo

st.set_page_config(
    page_title="Research Answers",
    page_icon=":material/question_answer:",
    layout="wide",
)

st.title("🔬 Research Answers")
st.caption("Antworten von Claude Code auf Research-Anfragen aus der App.")

rq_repo = get_research_queue_repo()

# Ticker → Portfolio-Position für "Zur Position"-Deeplinks (FEAT-55).
# Nur Portfolio-Positionen: das Position Dashboard zeigt keine Watchlist.
_portfolio_by_ticker = {
    p.ticker.upper(): p
    for p in get_portfolio_service().get_portfolio_positions()
    if p.ticker
}


def _position_for_ticker(ticker):
    if not ticker:
        return None
    return _portfolio_by_ticker.get(ticker.upper())

# ------------------------------------------------------------------
# Tab layout
# ------------------------------------------------------------------

tab_answers, tab_queue, tab_new = st.tabs(
    ["💬 Antworten", "📋 Offene Anfragen", t("research_request.tab_new")]
)

# ------------------------------------------------------------------
# Tab 1: Answers
# ------------------------------------------------------------------

with tab_answers:
    answers = rq_repo.list_answers()

    if not answers:
        st.info("Noch keine Antworten vorhanden. Benutze `submit_research_answer()` in Claude Code.")
    else:
        # Ticker filter
        tickers = sorted({a.ticker for a in answers if a.ticker})
        ticker_filter = None
        if tickers:
            col_filter, col_spacer = st.columns([2, 4])
            with col_filter:
                ticker_filter = st.selectbox(
                    "Ticker filtern",
                    ["Alle"] + tickers,
                    label_visibility="collapsed",
                )
            if ticker_filter == "Alle":
                ticker_filter = None

        filtered = [a for a in answers if ticker_filter is None or a.ticker == ticker_filter]

        st.caption(f"{len(filtered)} Antwort(en)")

        for answer in filtered:
            ticker_label = f" — {answer.ticker}" if answer.ticker else ""
            req_label = f" _(Request #{answer.request_id})_" if answer.request_id else ""
            ts = answer.created_at[:10] if answer.created_at else ""

            with st.expander(
                f"**Antwort #{answer.id}**{ticker_label} {req_label} · {ts}",
                expanded=len(filtered) == 1,
            ):
                llm_markdown(answer.answer_md)

                col_del, col_pos, col_spacer = st.columns([1, 1, 4])
                with col_del:
                    if st.button("🗑️ Löschen", key=f"del_answer_{answer.id}", type="secondary"):
                        rq_repo.delete_answer(answer.id)
                        st.rerun()
                _pos = _position_for_ticker(answer.ticker)
                if _pos:
                    with col_pos:
                        if st.button(
                            t("research_request.to_position_btn"),
                            key=f"to_pos_{answer.id}",
                        ):
                            st.session_state["pd_preselect_position_id"] = _pos.id
                            st.switch_page("pages/position_dashboard.py")

# ------------------------------------------------------------------
# Tab 2: Open Queue
# ------------------------------------------------------------------

with tab_queue:
    all_requests = rq_repo.list_all_requests()
    open_requests = [r for r in all_requests if r.status == "open"]
    done_requests = [r for r in all_requests if r.status == "done"]

    # Request → Antwort Verknüpfung sichtbar machen (FEAT-55)
    _answers_by_request = {a.request_id: a for a in rq_repo.list_answers() if a.request_id}

    if not all_requests:
        st.info(
            "Keine offenen Anfragen. Erstelle eine über den **Research anfordern**-Button "
            "auf der Positionsanalyse-Seite."
        )
    else:
        if open_requests:
            st.subheader(f"📋 Offen ({len(open_requests)})")
            for req in open_requests:
                ticker_label = f" [{req.ticker}]" if req.ticker else ""
                type_labels = {
                    "research_question": "Recherche",
                    "analysis_deepdive": "Vertiefung",
                    "watchlist_candidate": "Kandidat",
                    "general": "Allgemein",
                }
                type_label = type_labels.get(req.request_type, req.request_type)
                ts = req.created_at[:10] if req.created_at else ""

                with st.container(border=True):
                    col_info, col_actions = st.columns([5, 1])
                    with col_info:
                        st.markdown(f"**#{req.id}** `{type_label}`{ticker_label} · {ts}")
                        st.markdown(req.focus)
                        if req.context:
                            st.caption(f"Kontext: {req.context}")
                    with col_actions:
                        if st.button("✅ Erledigt", key=f"done_req_{req.id}"):
                            rq_repo.complete_request(req.id)
                            st.rerun()
                        if st.button("🗑️", key=f"del_req_{req.id}", help="Löschen"):
                            rq_repo.delete_request(req.id)
                            st.rerun()
                    _ans = _answers_by_request.get(req.id)
                    if _ans:
                        with st.expander(
                            t("research_request.linked_answer").format(id=_ans.id),
                            expanded=False,
                        ):
                            llm_markdown(_ans.answer_md)

        if done_requests:
            with st.expander(f"✅ Erledigt ({len(done_requests)})", expanded=False):
                for req in done_requests:
                    ticker_label = f" [{req.ticker}]" if req.ticker else ""
                    ts = req.updated_at[:10] if req.updated_at else ""
                    st.markdown(f"~~**#{req.id}**{ticker_label} — {req.focus}~~ _(erledigt {ts})_")
                    # Kein verschachtelter Expander erlaubt → Toggle (FEAT-55)
                    _ans = _answers_by_request.get(req.id)
                    if _ans:
                        if st.toggle(
                            t("research_request.linked_answer").format(id=_ans.id),
                            key=f"show_answer_{req.id}",
                        ):
                            with st.container(border=True):
                                llm_markdown(_ans.answer_md)

# ------------------------------------------------------------------
# Tab 3: New Request (FEAT-54)
# ------------------------------------------------------------------

with tab_new:
    render_research_request_form(rq_repo, show_ticker_field=True)
