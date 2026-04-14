"""
Watchlist Checker — evaluates which watchlist positions fit into the portfolio.
"""

import asyncio
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="Watchlist Checker", layout="wide")

from state import (
    get_positions_repo,
    get_watchlist_checker_agent,
    get_portfolio_story_repo,
    get_agent_runs_repo,
    get_portfolio_comment_service,
    get_app_config_repo,
    get_analyses_repo,
)
from core.services.portfolio_comment_service import get_style_by_id
from agents.rebalance_agent import compute_josef_allocation

# ─────────────────────────────────────────────────────────────────────

st.title("📋 Watchlist Checker")
st.caption("Welche Watchlist-Positionen würden gut ins Portfolio passen?")

# ─────────────────────────────────────────────────────────────────────
# Section 1: Run Watchlist Check
# ─────────────────────────────────────────────────────────────────────

st.subheader("1️⃣ Watchlist prüfen")

positions_repo = get_positions_repo()
portfolio_story_repo = get_portfolio_story_repo()
analyses_repo = get_analyses_repo()
agent = get_watchlist_checker_agent()
agent_runs_repo = get_agent_runs_repo()

watchlist = positions_repo.get_watchlist()

if not watchlist:
    st.info("📭 Keine Watchlist-Positionen vorhanden. Starten Sie mit dem Portfolio Chat um Watchlist-Einträge hinzuzufügen.")
    st.stop()

st.caption(f"**{len(watchlist)} Positionen** auf der Watchlist")

# Pre-check: Which agents haven't analyzed watchlist positions yet?
watchlist_ids = [pos.id for pos in watchlist if pos.id]
_missing_analyses = []
for agent_name, agent_label in [
    ("storychecker", "Story Checker"),
    ("fundamental", "Fundamental Analyzer"),
    ("consensus_gap", "Konsens-Lücken"),
]:
    bulk = analyses_repo.get_latest_bulk(watchlist_ids, agent_name)
    n_missing = sum(1 for pid in watchlist_ids if pid not in bulk)
    if n_missing:
        _missing_analyses.append(f"{agent_label} ({n_missing}/{len(watchlist_ids)} ausstehend)")

if _missing_analyses:
    st.info(
        "💡 Für bessere Ergebnisse zuerst folgende Analysen ausführen:\n"
        + "\n".join(f"- {m}" for m in _missing_analyses)
    )

if st.button("▶️ Watchlist prüfen", key="check_watchlist_btn"):
    with st.spinner("Watchlist wird geprüft..."):
        # Build context
        portfolio = positions_repo.get_portfolio()
        market_repo = None  # Would need to import, using placeholder

        # Portfolio snapshot (simplified)
        portfolio_snapshot = "## Portfolio\n"
        if portfolio:
            for p in portfolio[:5]:  # Show first 5
                portfolio_snapshot += f"- {p.name} ({p.ticker})\n"
            if len(portfolio) > 5:
                portfolio_snapshot += f"...\n"
        else:
            portfolio_snapshot += "(Leer)\n"

        # Story analysis context
        story_analysis_text = None
        story_analysis = portfolio_story_repo.get_latest_analysis()
        if story_analysis:
            story_analysis_text = f"""Story: {story_analysis.verdict}
Performance: {story_analysis.perf_verdict}
Stabilität: {story_analysis.stability_verdict}
"""

        # Run check
        try:
            result = asyncio.run(
                agent.check_watchlist(
                    portfolio_snapshot=portfolio_snapshot,
                    watchlist_positions=watchlist,
                    story_analysis_text=story_analysis_text,
                )
            )

            # Log to agent_runs
            agent_runs_repo.log_run(
                agent_name="watchlist_checker",
                model=agent.model,
                output_summary=f"Checked {len(watchlist)} positions",
                context_summary=f"Portfolio ({len(portfolio)} pos), Story ({bool(story_analysis)})",
            )

            st.success("✅ Watchlist-Prüfung durchgeführt!")
            st.session_state["_watchlist_check_result"] = result

        except Exception as e:
            st.error(f"❌ Fehler: {e}")
            import traceback
            st.text(traceback.format_exc())

# ─────────────────────────────────────────────────────────────────────
# Section 2: Display Results
# ─────────────────────────────────────────────────────────────────────

if st.session_state.get("_watchlist_check_result"):
    st.divider()
    st.subheader("2️⃣ Ergebnisse")

    result = st.session_state["_watchlist_check_result"]

    # Bulk-fetch analyses for all watchlist positions (used in expanders below)
    _all_fit_ids = [fit.position_id for fit in result.position_fits if fit.position_id]
    _bulk_story = analyses_repo.get_latest_bulk(_all_fit_ids, "storychecker") if _all_fit_ids else {}
    _bulk_fund = analyses_repo.get_latest_bulk(_all_fit_ids, "fundamental") if _all_fit_ids else {}

    # Display position fits
    for fit in result.position_fits:
        pos = next((p for p in watchlist if p.id == fit.position_id), None)
        if pos:
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])

                with col1:
                    # Verdict emoji
                    verdict_emoji = "🟢" if fit.verdict == "sehr_passend" else "🟡" if fit.verdict == "passend" else "⚪" if fit.verdict == "neutral" else "🔴"
                    st.markdown(f"**{verdict_emoji} {pos.name}** ({pos.ticker})")
                    st.caption(fit.summary)

                with col2:
                    st.metric("Fit", fit.verdict.replace("_", " ").title())

                # Position details (Story, Fundamental Analysis)
                with st.expander("📋 Position-Details"):
                    detail_cols = st.columns(2)

                    # Story Analysis (pre-fetched in bulk above)
                    with detail_cols[0]:
                        st.caption("**Story Checker**")
                        latest_story = _bulk_story.get(pos.id) if pos.id in _bulk_story else None
                        if latest_story and latest_story.verdict:
                            verdict_icon = "🟢" if latest_story.verdict == "intact" else "🟡" if latest_story.verdict == "gemischt" else "🔴"
                            st.markdown(f"{verdict_icon} {latest_story.verdict}")
                            if latest_story.summary:
                                st.caption(latest_story.summary)
                        else:
                            st.caption("⚪ Noch nicht analysiert")

                    # Fundamental Analysis (pre-fetched in bulk above)
                    with detail_cols[1]:
                        st.caption("**Fundamentalwert**")
                        latest_fund = _bulk_fund.get(pos.id) if pos.id in _bulk_fund else None
                        if latest_fund and latest_fund.verdict:
                            verdict = latest_fund.verdict
                            verdict_icon = "🟢" if verdict == "unterbewertet" else "🟡" if verdict == "fair" else "🔴" if verdict == "überbewertet" else "⚪"
                            st.markdown(f"{verdict_icon} {verdict or 'unbekannt'}")
                            if latest_fund.summary:
                                st.caption(latest_fund.summary)
                        else:
                            st.caption("⚪ Noch nicht analysiert")

    # --- KI-Kommentar --

    st.divider()
    st.subheader("3️⃣ KI-Kommentar")

    _comment_style_id = get_app_config_repo().get("comment_style") or "humorvoll"
    _comment_style = get_style_by_id(_comment_style_id)
    comment_service = get_portfolio_comment_service()

    if st.button(f"{_comment_style['emoji']} KI-Kommentar", key="_watchlist_comment_btn"):
        with st.spinner("..."):
            _ctx = f"Watchlist-Check Ergebnis:\n{result.full_text[:500]}"
            st.session_state["_watchlist_comment"] = comment_service.generate_comment(_ctx, _comment_style_id)

    if st.session_state.get("_watchlist_comment"):
        with st.container(border=True):
            st.caption(f"{_comment_style['emoji']} **{_comment_style['name']}**")
            st.markdown(st.session_state["_watchlist_comment"])

    # --- Details --

    with st.expander("📊 Kontext-Details"):
        st.caption("**Agent Metadata**")
        latest_run = agent_runs_repo.get_latest_run("watchlist_checker")
        if latest_run:
            st.json({
                "agent": latest_run["agent_name"],
                "model": latest_run["model"],
                "timestamp": latest_run["created_at"],
                "context": latest_run["context_summary"],
            })

        st.divider()
        st.caption("**Portfolio Story Context**")
        story_analysis = portfolio_story_repo.get_latest_analysis()
        if story_analysis:
            st.markdown(f"**Story Verdict:** {story_analysis.verdict}")
            st.caption(f"Performance: {story_analysis.perf_verdict}")
            st.caption(f"Stabilität: {story_analysis.stability_verdict}")
        else:
            st.caption("(Noch keine Portfolio-Story erstellt)")

        st.divider()
        st.caption("**Watchlist-Positionen: Zusammenfassung**")
        st.caption(f"Gesamt: {len(watchlist)} Positionen analysiert")
        fit_counts = {
            "sehr_passend": sum(1 for f in result.position_fits if f.verdict == "sehr_passend"),
            "passend": sum(1 for f in result.position_fits if f.verdict == "passend"),
            "neutral": sum(1 for f in result.position_fits if f.verdict == "neutral"),
            "nicht_passend": sum(1 for f in result.position_fits if f.verdict == "nicht_passend"),
        }
        st.markdown(
            f"🟢 Sehr passend: {fit_counts['sehr_passend']} | "
            f"🟡 Passend: {fit_counts['passend']} | "
            f"⚪ Neutral: {fit_counts['neutral']} | "
            f"🔴 Nicht passend: {fit_counts['nicht_passend']}"
        )

        st.divider()
        st.caption("**Vollständige LLM-Analyse**")
        st.text(result.full_text)
