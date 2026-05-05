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

from core.currency import symbol
from core.i18n import t
from core.ui.verdicts import VERDICT_CONFIGS, verdict_badge
from state import (
    get_market_agent,
    get_portfolio_service,
    get_analysis_service,
    get_news_repo,
    get_storychecker_agent,
    get_fundamental_analyzer_agent,
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
    """Render a single checker card: badge + summary + details expander."""
    if verdict_obj is None:
        st.markdown(f"**{title}**")
        st.markdown(
            "_:gray[Noch nicht analysiert]_",
            help="Kein Verdict vorhanden. Führen Sie eine Analyse auf der Seite des Checkers durch.",
        )
        return

    # Header: title + badge
    badge = verdict_badge(verdict_obj.verdict, config)
    st.markdown(f"**{title}** {badge}")

    # Metadata
    if verdict_obj.created_at:
        date_str = verdict_obj.created_at.strftime("%d. %b %Y")
        st.caption(f"{date_str}")

    # Summary
    if verdict_obj.summary:
        st.markdown(f"_{verdict_obj.summary}_")

    # Full-text expander
    full_text = None
    try:
        full_text = full_text_fn()
    except Exception as e:
        st.warning(f"Could not retrieve full text: {e}")

    if full_text:
        with st.expander("▼ Vollständige Analyse"):
            st.markdown(full_text)


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

selected_display = st.selectbox(
    t("position_dashboard.select_position"),
    list(position_display.keys()),
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
fa_agent = get_fundamental_analyzer_agent()

# Render 3 checker cards in columns
col1, col2, col3 = st.columns(3)

with col1:
    _render_checker_card(
        "Storychecker",
        sc_verdict,
        VERDICT_CONFIGS["storychecker"],
        lambda: sc_agent.get_messages(sc_verdict.session_id)[0].content
        if sc_verdict and sc_verdict.session_id
        else None,
    )

with col2:
    _render_checker_card(
        "Consensus Gap",
        cg_verdict,
        VERDICT_CONFIGS["consensus_gap"],
        lambda: cg_verdict.analysis_text if cg_verdict and cg_verdict.analysis_text else None,
    )

with col3:
    _render_checker_card(
        "Fundamental Analyzer",
        fa_verdict,
        VERDICT_CONFIGS["fundamental_analyzer"],
        lambda: fa_agent.get_messages(fa_verdict.session_id)[0].content
        if fa_verdict and fa_verdict.session_id
        else None,
    )

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
