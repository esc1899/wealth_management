"""
Watchlist Checker — evaluates which watchlist positions fit into the portfolio.

Cleanroom Neuimplementierung (2026-04-14):
- Two separate background jobs: Story+Consensus (Button 1) & Fundamental (Button 2)
- Thread-local DB connections (not Streamlit singletons)
- Skill resolution from scheduled jobs or defaults
"""

import asyncio
import logging
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
    get_storychecker_repo,
    get_skills_repo,
)
from core.services.portfolio_comment_service import get_style_by_id
from config import config
from core.storage.base import get_connection, init_db, migrate_db, build_encryption_service
from core.storage.positions import PositionsRepository
from core.storage.analyses import PositionAnalysesRepository
from core.storage.storychecker import StorycheckerRepository
from core.storage.scheduled_jobs import ScheduledJobsRepository
from agents.storychecker_agent import StorycheckerAgent
from agents.consensus_gap_agent import ConsensusGapAgent
from agents.fundamental_agent import FundamentalAgent
from core.llm.claude import ClaudeProvider
from core.constants import CLAUDE_HAIKU, CLAUDE_SONNET, AGENT_SKILL_DEFAULTS


logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helper: Skill Resolution (Modul-Level)
# ------------------------------------------------------------------

def _resolve_skill(
    jobs_repo: ScheduledJobsRepository,
    skills_repo,
    agent_name: str,
) -> tuple[str, str]:
    """
    Resolve skill_name and skill_prompt for an agent from scheduled jobs or defaults.

    Priority:
    1. First enabled scheduled job for this agent_name
    2. Default skill from AGENT_SKILL_DEFAULTS
    3. "Standard" as fallback

    Returns: (skill_name, skill_prompt)
    """
    try:
        for job in jobs_repo.get_all():
            if job.agent_name == agent_name and job.enabled:
                skill_name = job.skill_name or "Standard"
                skill_prompt = ""
                if job.skill_name:
                    skill = skills_repo.get_by_name(job.skill_name)
                    if skill:
                        skill_prompt = skill.prompt or ""
                return skill_name, skill_prompt
    except Exception as exc:
        logger.warning(f"Error resolving skill for {agent_name}: {exc}")

    # Default if no scheduled job found
    default_skill = AGENT_SKILL_DEFAULTS.get(agent_name, "Standard")
    return default_skill, ""


# ------------------------------------------------------------------
# Background Job 1: StorycheckerAgent + ConsensusGapAgent
# ------------------------------------------------------------------

def _run_storychecker_consensus_job(
    watchlist: list,
    agents_to_run: list[str],  # ["storychecker", "consensus_gap"]
    job: dict,
    db_path: str,
    enc_key: str,
    api_key: str,
) -> None:
    """
    Run Story Checker and Consensus Gap agents in background.
    Thread-local connection and repos.
    """
    conn = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    count = 0

    try:
        # Create fresh thread-local connection
        conn = get_connection(db_path)
        init_db(conn)
        migrate_db(conn)

        # Build repos with thread-safe connection
        enc = build_encryption_service(enc_key, "data/salt.bin")
        positions_repo = PositionsRepository(conn, enc)
        analyses_repo = PositionAnalysesRepository(conn)
        storychecker_repo = StorycheckerRepository(conn)
        skills_repo = get_skills_repo()  # Read-only for skill resolution
        jobs_repo = ScheduledJobsRepository(conn)

        watchlist_positions = [p for p in watchlist if p.id]

        # StorycheckerAgent
        if "storychecker" in agents_to_run:
            job["agents"] = ["Story Checker"]
            sc_skill_name, sc_skill_prompt = _resolve_skill(jobs_repo, skills_repo, "storychecker")
            sc_llm = ClaudeProvider(api_key=api_key, model=CLAUDE_HAIKU)
            sc_llm.skill_context = sc_skill_name
            sc_agent = StorycheckerAgent(
                positions_repo=positions_repo,
                storychecker_repo=storychecker_repo,
                analyses_repo=analyses_repo,
                llm=sc_llm,
                skills_repo=skills_repo,
            )
            try:
                results = loop.run_until_complete(sc_agent.batch_check_all(positions=watchlist_positions))
                sc_count = sum(1 for _, err in results if err is None)
                count += sc_count
                logger.info(f"StorycheckerAgent: {sc_count} analyses completed")
            except Exception as exc:
                logger.exception("StorycheckerAgent failed")
                job["error"] = f"StorycheckerAgent: {str(exc)}"

        # ConsensusGapAgent
        if "consensus_gap" in agents_to_run:
            if "agents" not in job or not job["agents"]:
                job["agents"] = []
            if "Story Checker" not in job["agents"]:
                job["agents"].append("Konsens-Lücken")
            else:
                job["agents"] = ["Story Checker", "Konsens-Lücken"]

            cg_skill_name, cg_skill_prompt = _resolve_skill(jobs_repo, skills_repo, "consensus_gap")
            cg_llm = ClaudeProvider(api_key=api_key, model=CLAUDE_SONNET)
            cg_agent = ConsensusGapAgent(llm=cg_llm)
            try:
                loop.run_until_complete(
                    cg_agent.analyze_portfolio(watchlist_positions, cg_skill_name, cg_skill_prompt, analyses_repo)
                )
                cg_count = len(watchlist_positions)
                count += cg_count
                logger.info(f"ConsensusGapAgent: {cg_count} analyses completed")
            except Exception as exc:
                logger.exception("ConsensusGapAgent failed")
                job["error"] = f"ConsensusGapAgent: {str(exc)}"

        job.update({"running": False, "done": True, "count": count, "error": None})

    except Exception as exc:
        logger.exception("Background SC+CG job failed")
        job.update({"running": False, "done": True, "count": count, "error": str(exc)})

    finally:
        loop.close()
        if conn:
            conn.close()


# ------------------------------------------------------------------
# Background Job 2: FundamentalAgent
# ------------------------------------------------------------------

def _run_fundamental_job(
    watchlist: list,
    job: dict,
    db_path: str,
    enc_key: str,
    api_key: str,
) -> None:
    """
    Run Fundamental Agent in background (matches Scheduler pattern).
    Thread-local connection and repos.
    """
    conn = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    count = 0

    try:
        # Create fresh thread-local connection
        conn = get_connection(db_path)
        init_db(conn)
        migrate_db(conn)

        # Build repos with thread-safe connection
        from core.storage.analyses import PositionAnalysesRepository
        enc = build_encryption_service(enc_key, "data/salt.bin")
        positions_repo = PositionsRepository(conn, enc)
        analyses_repo = PositionAnalysesRepository(conn)
        skills_repo = get_skills_repo()  # Read-only for skill resolution
        jobs_repo = ScheduledJobsRepository(conn)

        # Resolve skill
        fund_skill_name, fund_skill_prompt = _resolve_skill(jobs_repo, skills_repo, "fundamental")

        # Create agent with thread-safe repos (same as Scheduler does)
        fund_llm = ClaudeProvider(api_key=api_key, model=CLAUDE_SONNET)
        fund_agent = FundamentalAgent(llm=fund_llm)

        job["agents"] = ["Fundamental"]
        positions = [p for p in watchlist if p.id]
        if positions:
            loop.run_until_complete(
                fund_agent.analyze_portfolio(
                    positions=positions,
                    skill_name=fund_skill_name,
                    skill_prompt=fund_skill_prompt,
                    analyses_repo=analyses_repo,
                )
            )
            count = len(positions)

        job.update({"running": False, "done": True, "count": count, "error": None})

    except Exception as exc:
        logger.exception("Background Fundamental job failed")
        job.update({"running": False, "done": True, "count": count, "error": str(exc)})

    finally:
        loop.close()
        if conn:
            conn.close()


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

# Initialize background job state for two separate jobs
_JOB_DEFAULTS = {"running": False, "done": False, "count": 0, "errors": 0, "error": None, "agents": []}

if "_wc_agents_job" not in st.session_state:
    st.session_state["_wc_agents_job"] = dict(_JOB_DEFAULTS)
if "_wc_fund_job" not in st.session_state:
    st.session_state["_wc_fund_job"] = dict(_JOB_DEFAULTS)

_WC_JOB = st.session_state["_wc_agents_job"]
_WC_FUND_JOB = st.session_state["_wc_fund_job"]

# Polling: Show progress while ANY job is running
if _WC_JOB["running"] or _WC_FUND_JOB["running"]:
    labels = _WC_JOB.get("agents", []) + _WC_FUND_JOB.get("agents", [])
    st.info(f"⏳ Analysen laufen: {', '.join(labels) or '...'}", icon=":material/hourglass_top:")
    time.sleep(5)
    st.rerun()

# Done-Block: Show results for each job separately
for _job, _label in [(_WC_JOB, "Story+Konsens"), (_WC_FUND_JOB, "Fundamental")]:
    if _job["done"]:
        if _job["error"]:
            st.error(f"❌ {_label}: {_job['error']}")
        else:
            st.success(f"✅ {_label}: {_job['count']} Analysen abgeschlossen.")
        if st.button("Dismiss", key=f"dismiss_{_label}"):
            _job.update(dict(_JOB_DEFAULTS))
            st.rerun()
        st.divider()

if not watchlist:
    st.info("📭 Keine Watchlist-Positionen vorhanden. Starten Sie mit dem Portfolio Chat um Watchlist-Einträge hinzuzufügen.")
    st.stop()

st.caption(f"**{len(watchlist)} Positionen** auf der Watchlist")

# Pre-check: Which agents haven't analyzed watchlist positions yet?
# (Only show if no job is currently running)
if not _WC_JOB["running"] and not _WC_FUND_JOB["running"]:
    watchlist_ids = [pos.id for pos in watchlist if pos.id]
    _analyses_status = []

    for agent_name, agent_label, page_path in [
        ("storychecker", "Story Checker", "pages/storychecker.py"),
        ("fundamental_analyzer", "Fundamental Analyzer", "pages/fundamental.py"),
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

        # Two separate buttons: Story+Consensus vs. Fundamental
        col1, col2 = st.columns(2)

        with col1:
            if st.button(
                "Story + Konsens starten",
                key="_wc_start_sc_cg",
                disabled=_WC_JOB["running"] or _WC_FUND_JOB["running"],
                type="primary",
                use_container_width=True,
            ):
                # Filter agents to run (only those with missing analyses)
                agents_to_run = [s["agent_name"] for s in _analyses_status
                                if s["n_missing"] > 0 and s["agent_name"] in ["storychecker", "consensus_gap"]]
                if agents_to_run:
                    _WC_JOB.update({**_JOB_DEFAULTS, "running": True, "agents": ["Story Checker", "Konsens-Lücken"]})
                    threading.Thread(
                        target=_run_storychecker_consensus_job,
                        args=(watchlist, agents_to_run, _WC_JOB,
                              config.DB_PATH, config.ENCRYPTION_KEY, config.ANTHROPIC_API_KEY),
                        daemon=True,
                    ).start()
                    st.rerun()

        with col2:
            if st.button(
                "Fundamental-Analysen starten",
                key="_wc_start_fund",
                disabled=_WC_JOB["running"] or _WC_FUND_JOB["running"],
                type="primary",
                use_container_width=True,
            ):
                # Only run if fundamental_analyzer has missing analyses
                if any(s["n_missing"] > 0 and s["agent_name"] == "fundamental_analyzer" for s in _analyses_status):
                    _WC_FUND_JOB.update({**_JOB_DEFAULTS, "running": True, "agents": ["Fundamental Analyzer"]})
                    threading.Thread(
                        target=_run_fundamental_job,
                        args=(watchlist, _WC_FUND_JOB,
                              config.DB_PATH, config.ENCRYPTION_KEY, config.ANTHROPIC_API_KEY),
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
