"""
Watchlist Checker — evaluates which watchlist positions fit into the portfolio.
"""

import asyncio
import threading
import time
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
    get_storychecker_agent,
    get_fundamental_analyzer_agent,
    get_consensus_gap_agent,
)
from core.services.portfolio_comment_service import get_style_by_id
from agents.rebalance_agent import compute_josef_allocation


# ------------------------------------------------------------------
# Background Agent Runner
# ------------------------------------------------------------------

def _run_agents_for_watchlist(watchlist_positions, agents_to_run, job, sc_agent, fund_agent, cg_agent, analyses_repo_inst):
    """Run missing agents for watchlist positions in background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    count = 0
    try:
        # StorycheckerAgent: batch check
        if "storychecker" in agents_to_run:
            results = loop.run_until_complete(sc_agent.batch_check_all(positions=watchlist_positions))
            count += sum(1 for _, err in results if err is None)

        # FundamentalAnalyzerAgent: loop over positions
        if "fundamental" in agents_to_run:
            for pos in watchlist_positions:
                if pos.id:
                    try:
                        fund_agent.start_session(pos)
                        count += 1
                    except Exception:
                        job["errors"] = job.get("errors", 0) + 1

        # ConsensusGapAgent: batch analyze
        if "consensus_gap" in agents_to_run:
            results = loop.run_until_complete(
                cg_agent.analyze_portfolio(watchlist_positions, "", "", analyses_repo_inst)
            )
            count += len(results)

        job.update({"running": False, "done": True, "count": count, "error": None})
    except Exception as exc:
        job.update({"running": False, "done": True, "count": count, "error": str(exc)})
    finally:
        loop.close()


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

# Initialize background job state for agent runs
if "_wc_agents_job" not in st.session_state:
    st.session_state["_wc_agents_job"] = {
        "running": False, "done": False,
        "count": 0, "errors": 0, "error": None,
        "agents": [],
    }
_WC_JOB = st.session_state["_wc_agents_job"]

# Polling: Show progress while agents are running
if _WC_JOB["running"]:
    agents_running = ", ".join(_WC_JOB.get("agents", []))
    st.info(f"⏳ Analysen laufen im Hintergrund: {agents_running}...", icon=":material/hourglass_top:")
    time.sleep(5)
    st.rerun()

# Show result when done
if _WC_JOB["done"]:
    if _WC_JOB["error"]:
        st.error(f"❌ Fehler bei Analyse: {_WC_JOB['error']}")
    else:
        st.success(f"✅ {_WC_JOB['count']} Analysen abgeschlossen.")
    if st.button("✕ Schließen", key="_wc_job_dismiss"):
        st.session_state["_wc_agents_job"] = {
            "running": False, "done": False, "count": 0, "errors": 0, "error": None, "agents": []
        }
        st.rerun()
    st.divider()

if not watchlist:
    st.info("📭 Keine Watchlist-Positionen vorhanden. Starten Sie mit dem Portfolio Chat um Watchlist-Einträge hinzuzufügen.")
    st.stop()

st.caption(f"**{len(watchlist)} Positionen** auf der Watchlist")

# Pre-check: Which agents haven't analyzed watchlist positions yet?
watchlist_ids = [pos.id for pos in watchlist if pos.id]
_analyses_status = []

for agent_name, agent_label, page_path in [
    ("storychecker", "Story Checker", "pages/storychecker.py"),
    ("fundamental", "Fundamental Analyzer", "pages/fundamental.py"),
    ("consensus_gap", "Konsens-Lücken", "pages/consensus_gap.py"),
]:
    bulk = analyses_repo.get_latest_bulk(watchlist_ids, agent_name)
    n_missing = sum(1 for pid in watchlist_ids if pid not in bulk)

    # Get timestamp of latest analysis across all watchlist positions
    latest_ts = None
    for verdict_obj in bulk.values():
        if verdict_obj and hasattr(verdict_obj, 'created_at') and verdict_obj.created_at:
            if latest_ts is None or verdict_obj.created_at > latest_ts:
                latest_ts = verdict_obj.created_at

    ts_str = f" (zuletzt: {latest_ts.strftime('%d.%m. %H:%M')})" if latest_ts else " (noch nicht gelaufen)"

    _analyses_status.append({
        "label": agent_label,
        "page": page_path,
        "n_missing": n_missing,
        "total": len(watchlist_ids),
        "timestamp": ts_str,
        "agent_name": agent_name,
    })

# Show info box + action buttons if any missing
_has_missing = any(s["n_missing"] > 0 for s in _analyses_status)
if _has_missing:
    st.info(
        "💡 Für bessere Ergebnisse folgende Analysen ausführen:\n"
        + "\n".join(
            f"- {s['label']} ({s['n_missing']}/{s['total']} ausstehend){s['timestamp']}"
            for s in _analyses_status if s["n_missing"] > 0
        )
    )

    # Button to start missing analyses in background
    _agents_to_run = [s["agent_name"] for s in _analyses_status if s["n_missing"] > 0]
    n_agents = len(_agents_to_run)
    agent_labels = ", ".join(s["label"] for s in _analyses_status if s["n_missing"] > 0)

    col_btn, col_spacer = st.columns([2, 3])
    with col_btn:
        if st.button(
            f"▶️ {n_agents} Analyse{'n' if n_agents > 1 else ''} im Hintergrund starten",
            key="_wc_start_agents",
            disabled=_WC_JOB["running"],
            type="primary",
            use_container_width=True,
        ):
            _WC_JOB["running"] = True
            _WC_JOB["done"] = False
            _WC_JOB["error"] = None
            _WC_JOB["count"] = 0
            _WC_JOB["agents"] = [s["label"] for s in _analyses_status if s["n_missing"] > 0]
            threading.Thread(
                target=_run_agents_for_watchlist,
                args=(watchlist, _agents_to_run, _WC_JOB,
                      get_storychecker_agent(), get_fundamental_analyzer_agent(),
                      get_consensus_gap_agent(), analyses_repo),
                daemon=True,
            ).start()
            st.rerun()

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
