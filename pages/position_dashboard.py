"""
Position Dashboard — aggregates all analyses for a single portfolio position.

Displays: Storychecker, Consensus Gap, Fundamental Analyzer verdicts,
price history (Kursverlauf), and relevant News Digest section.
"""

from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st

_POSITIVE_VERDICTS = frozenset({"intact", "wächst", "unterbewertet"})
_NEGATIVE_VERDICTS = frozenset({"gefährdet", "eingeholt", "überbewertet"})

from core.currency import symbol
from core.i18n import t
from core.ui.markdown import llm_markdown
from core.ui.research_request_form import render_research_request_form
from core.ui.verdicts import VERDICT_CONFIGS, verdict_badge
from core.accumulation import accumulation_for_position
from state import (
    get_market_agent,
    get_portfolio_service,
    get_analysis_service,
    get_news_repo,
    get_storychecker_agent,
    get_fundamental_analyzer_agent,
    get_consensus_gap_agent,
    get_research_queue_repo,
)

st.set_page_config(
    page_title="Position",
    page_icon="👤",
    layout="wide",
)

st.title(f"👤 Position")

# ------------------------------------------------------------------
# Initialize services
# ------------------------------------------------------------------

market_agent = get_market_agent()
portfolio_service = get_portfolio_service()
analysis_service = get_analysis_service()
news_repo = get_news_repo()


# ------------------------------------------------------------------
# Helper functions (must be defined before use)
# ------------------------------------------------------------------


def _render_checker_card(title: str, verdict_obj, config, full_text_fn):
    """Render a full-width analysis card: badge + summary + details expander."""
    with st.container():
        if verdict_obj is None:
            st.markdown(f"**{title}**")
            st.markdown(
                "_:gray[Noch nicht analysiert]_",
                help="Kein Verdict vorhanden. Führen Sie eine Analyse auf der Seite des Checkers durch.",
            )
            return

        badge = verdict_badge(verdict_obj.verdict, config)
        title_col, date_col = st.columns([5, 1])
        with title_col:
            st.markdown(f"**{title}** {badge}")
        with date_col:
            if verdict_obj.created_at:
                st.caption(verdict_obj.created_at.strftime("%d. %b %Y"))

        if verdict_obj.summary:
            llm_markdown(f"_{verdict_obj.summary}_")

        full_text = None
        try:
            full_text = full_text_fn()
        except Exception as e:
            st.warning(f"Could not retrieve full text: {e}")

        if full_text:
            with st.expander("▼ Vollständige Analyse"):
                llm_markdown(full_text)


def _render_confluence_score(sc_v, cg_v, fa_v) -> None:
    """Compact one-line confluence summary above the 3 checker cards."""
    def _sentiment(v):
        if v is None:
            return "none"
        if v in _POSITIVE_VERDICTS:
            return "positive"
        if v in _NEGATIVE_VERDICTS:
            return "negative"
        return "neutral"

    verdicts = [
        sc_v.verdict if sc_v else None,
        cg_v.verdict if cg_v else None,
        fa_v.verdict if fa_v else None,
    ]
    present = [(v, _sentiment(v)) for v in verdicts if v is not None]
    n = len(present)

    if n == 0:
        st.caption("Research Confluence: ⚪ Keine Daten")
        return

    pos = sum(1 for _, s in present if s == "positive")
    neg = sum(1 for _, s in present if s == "negative")

    if pos == n:
        icon, label = "🟢", "Starker Konsens"
        detail = f"{pos}/{n} bullisch"
    elif neg == n:
        icon, label = "🔴", "Starker Konsens"
        detail = f"{neg}/{n} bearish"
    elif pos >= 2 and neg == 0:
        icon, label = "🟢", "Überwiegend positiv"
        detail = f"{pos}/{n} bullisch"
    elif neg >= 2 and pos == 0:
        icon, label = "🔴", "Überwiegend negativ"
        detail = f"{neg}/{n} bearish"
    elif pos > neg:
        icon, label = "🟡", "Leicht positiv"
        detail = f"{pos}/{n} bullisch"
    elif neg > pos:
        icon, label = "🟠", "Leicht negativ"
        detail = f"{neg}/{n} bearish"
    else:
        icon, label = "⚪", "Gemischt"
        detail = "Keine klare Tendenz"

    data_note = f" _({n}/3 analysiert)_" if n < 3 else ""
    st.markdown(f"**Research Confluence:** {icon} {label} — {detail}{data_note}")


def _extract_ticker_section(digest: str, ticker: str) -> Optional[str]:
    """
    Extract the section for a specific ticker from a news digest.
    Pattern: "## TICKER —" ... until next "##" or end of string.
    """
    if not digest or not ticker:
        return None

    # Normalize ticker to uppercase
    ticker = ticker.upper()

    lines = digest.split("\n")
    start_idx = None
    end_idx = None

    # Find the header line matching "## TICKER"
    for i, line in enumerate(lines):
        if line.strip().startswith("##"):
            # Extract the ticket from this line: "## AAPL —" or "## AAPL"
            header_content = line.replace("##", "").strip()
            # Check if the first token (before space/dash) matches our ticker
            first_token = header_content.split()[0] if header_content else ""
            if first_token.upper() == ticker:
                start_idx = i
                break

    if start_idx is None:
        return None

    # Find the end: next "##" or end of digest
    for i in range(start_idx + 1, len(lines)):
        if lines[i].strip().startswith("##"):
            end_idx = i
            break

    if end_idx is None:
        end_idx = len(lines)

    section_lines = lines[start_idx:end_idx]
    section = "\n".join(section_lines).strip()

    # Remove the "---" separator at the end if present
    if section.endswith("---"):
        section = section[:-3].strip()

    return section if section else None


# ------------------------------------------------------------------
# Get portfolio positions and selector
# ------------------------------------------------------------------

portfolio_positions = portfolio_service.get_portfolio_positions()

if not portfolio_positions:
    st.info(t("position_dashboard.no_positions"))
    st.stop()

# Format positions as "Name (TICKER)" for dropdown
position_display = {
    f"{p.name} ({p.ticker})" if p.ticker else p.name: p
    for p in portfolio_positions
}

# Pre-selection from Portfolio Story deeplink (via session_state)
preselect_id = st.session_state.pop("pd_preselect_position_id", None)
position_keys = list(position_display.keys())

default_index = 0
if preselect_id is not None:
    for i, p in enumerate(portfolio_positions):
        if p.id == preselect_id:
            default_index = i
            break

selected_display = st.selectbox(
    t("position_dashboard.select_position"),
    position_keys,
    index=default_index,
)

if not selected_display:
    st.stop()

selected_position = position_display[selected_display]

st.divider()

# ------------------------------------------------------------------
# Section 1: Price History (Kursverlauf)
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
        fig_hist = px.line(
            df_hist,
            x=col_date,
            y=col_price,
            title=f"{selected_position.ticker} — letztes Jahr",
        )
        fig_hist.update_layout(margin=dict(t=40))
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.info(t("analysis.no_history"))
else:
    st.info(
        t("position_dashboard.no_ticker")
    )

st.divider()

# ------------------------------------------------------------------
# Section 2: Analyses (Storychecker, Consensus Gap, Fundamental)
# ------------------------------------------------------------------

st.subheader("🔍 Analysen")

if not selected_position.id:
    st.warning("Position has no ID, cannot retrieve analyses.")
    st.stop()

# Fetch all verdicts for the position
sc_verdict = analysis_service.get_verdict(selected_position.id, "storychecker")
cg_verdict = analysis_service.get_verdict(selected_position.id, "consensus_gap")
fa_verdict = analysis_service.get_verdict(
    selected_position.id, "fundamental_analyzer"
)

# Get agents for full-text retrieval
sc_agent = get_storychecker_agent()
cg_agent = get_consensus_gap_agent()
fa_agent = get_fundamental_analyzer_agent()

# Confluence summary
_render_confluence_score(sc_verdict, cg_verdict, fa_verdict)

st.write("")

# Render 3 checker cards vertically (full-width)
_render_checker_card(
    "Storychecker",
    sc_verdict,
    VERDICT_CONFIGS["storychecker"],
    lambda: sc_agent.get_messages(sc_verdict.session_id)[-1].content
    if sc_verdict and sc_verdict.session_id
    else None,
)

st.write("")

_render_checker_card(
    "Consensus Gap",
    cg_verdict,
    VERDICT_CONFIGS["consensus_gap"],
    lambda: cg_agent.get_messages(cg_verdict.session_id)[-1].content
    if cg_verdict and cg_verdict.session_id
    else None,
)

st.write("")

_render_checker_card(
    "Fundamental Analyzer",
    fa_verdict,
    VERDICT_CONFIGS["fundamental_analyzer"],
    lambda: fa_agent.get_messages(fa_verdict.session_id)[-1].content
    if fa_verdict and fa_verdict.session_id
    else None,
)

st.write("")

# Accumulation indicator (FEAT-68 B1) — deterministic, derived from yield + SC/FA verdicts.
# Yield from the valuation layer (overrides + cross-currency), not the raw dividend_data table.
_acc_yields = {
    v.symbol.upper(): v.dividend_yield_pct
    for v in market_agent.get_portfolio_valuation(include_watchlist=True)
    if v.symbol
}
_acc = accumulation_for_position(
    selected_position.ticker, sc_verdict, fa_verdict, _acc_yields
)
with st.container():
    _badge = verdict_badge(_acc.verdict, VERDICT_CONFIGS["accumulation"])
    st.markdown(f"**{t('accumulation.section')}** {_badge}", help=t("accumulation.help"))
    st.dataframe(
        [
            {
                t("accumulation.comp_col_name"): t(c.name),
                t("accumulation.comp_col_value"): c.value,
                t("accumulation.comp_col_rating"): c.rating,
            }
            for c in _acc.components
        ],
        use_container_width=True,
        hide_index=True,
    )
    if _acc.binding:
        st.caption(f"**{t('accumulation.binding_label')}** {t(_acc.binding)}")

st.divider()

# ------------------------------------------------------------------
# Section 3: News Digest Section
# ------------------------------------------------------------------

st.subheader("📰 News Digest")

if selected_position.ticker:
    news_runs = news_repo.list_runs(limit=1)
    if news_runs:
        latest_run = news_runs[0]
        ticker_section = _extract_ticker_section(latest_run.result, selected_position.ticker)

        if ticker_section:
            st.caption(
                f"Letzter Run: {latest_run.created_at.strftime('%d. %b %Y') if latest_run.created_at else 'unknown'}"
            )
            # Extract first sentence as summary
            first_line = ticker_section.split("\n")[1] if len(ticker_section.split("\n")) > 1 else ""
            if first_line:
                st.markdown(f"_{first_line}_")

            # Full text expandable
            with st.expander(
                f"▼ Vollständige News für {selected_position.ticker}", expanded=False
            ):
                st.markdown(ticker_section)
        else:
            st.info(
                f"Kein News-Abschnitt für {selected_position.ticker} im letzten Digest gefunden."
            )
    else:
        st.info("Kein News Digest vorhanden.")
else:
    st.info("Position hat kein Ticker — keine News verfügbar.")

st.divider()

# ------------------------------------------------------------------
# Section 4: Research Answers für diesen Ticker (FEAT-55)
# ------------------------------------------------------------------

_rq_repo = get_research_queue_repo()

if selected_position.ticker:
    _answers = _rq_repo.list_answers_for_ticker(selected_position.ticker)
    if _answers:
        st.subheader(t("research_request.answers_header").format(n=len(_answers)))
        for _answer in _answers:
            _ts = _answer.created_at[:10] if _answer.created_at else ""
            _req_label = f" · Request #{_answer.request_id}" if _answer.request_id else ""
            _label = t("research_request.answer_label").format(id=_answer.id)
            with st.expander(f"**{_label}** · {_ts}{_req_label}", expanded=False):
                llm_markdown(_answer.answer_md)
        st.divider()

# ------------------------------------------------------------------
# Section 5: Research anfordern (FEAT-50)
# ------------------------------------------------------------------

render_research_request_form(_rq_repo, ticker=selected_position.ticker)
