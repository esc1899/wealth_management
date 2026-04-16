"""
Watchlist Checker — evaluates which watchlist positions fit into the portfolio.

Cleanroom Neuimplementierung (2026-04-14):
- Two separate background jobs: Story+Consensus (Button 1) & Fundamental (Button 2)
- Thread-local DB connections (not Streamlit singletons)
- Skill resolution from scheduled jobs or defaults
"""

import asyncio
import json
import logging
import threading
import time
import streamlit as st
from datetime import datetime

from core.ui.verdicts import VERDICT_CONFIGS, verdict_icon

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
    get_watchlist_checker_repo,
    get_market_agent,
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
# Helper: Logging (write to job dict for UI visibility)
# ------------------------------------------------------------------

def _log_to_job(job: dict, msg: str) -> None:
    """Add message to job logs for UI display."""
    if "logs" not in job:
        job["logs"] = []
    job["logs"].append(msg)
    logger.info(msg)  # Also log to stderr for CLI access


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
    error_msg = None

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
        _log_to_job(job, f"SC+CG job: {len(watchlist_positions)} positions, agents: {agents_to_run}")

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
                _log_to_job(job, f"Running StorycheckerAgent with skill '{sc_skill_name}'")
                results = loop.run_until_complete(sc_agent.batch_check_all(positions=watchlist_positions))
                sc_count = sum(1 for _, err in results if err is None)
                count += sc_count
                _log_to_job(job, f"StorycheckerAgent: {sc_count}/{len(watchlist_positions)} analyses completed")
            except Exception as exc:
                logger.exception("StorycheckerAgent failed")
                error_msg = f"StorycheckerAgent: {str(exc)}"
                _log_to_job(job, f"❌ StorycheckerAgent failed: {error_msg}")
                job["error"] = error_msg

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
                _log_to_job(job, f"Running ConsensusGapAgent with skill '{cg_skill_name}'")
                loop.run_until_complete(
                    cg_agent.analyze_portfolio(watchlist_positions, cg_skill_name, cg_skill_prompt, analyses_repo)
                )
                cg_count = len(watchlist_positions)
                count += cg_count
                _log_to_job(job, f"ConsensusGapAgent: {cg_count} analyses completed")
            except Exception as exc:
                logger.exception("ConsensusGapAgent failed")
                error_msg = f"ConsensusGapAgent: {str(exc)}"
                _log_to_job(job, f"❌ ConsensusGapAgent failed: {error_msg}")
                job["error"] = error_msg

        job.update({"running": False, "done": True, "count": count, "error": error_msg})

    except Exception as exc:
        error_msg = str(exc)
        logger.exception("Background SC+CG job failed")
        job.update({"running": False, "done": True, "count": count, "error": error_msg})

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
    from core.storage.analyses import PositionAnalysesRepository

    conn = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    count = 0
    error_msg = None

    try:
        # Create fresh thread-local connection
        conn = get_connection(db_path)
        init_db(conn)
        migrate_db(conn)

        # Build repos with thread-safe connection
        enc = build_encryption_service(enc_key, "data/salt.bin")
        positions_repo = PositionsRepository(conn, enc)
        analyses_repo = PositionAnalysesRepository(conn)
        skills_repo = get_skills_repo()  # Read-only for skill resolution
        jobs_repo = ScheduledJobsRepository(conn)

        # Resolve skill
        fund_skill_name, fund_skill_prompt = _resolve_skill(jobs_repo, skills_repo, "fundamental")

        _log_to_job(job, f"Skill resolved: '{fund_skill_name}'")
        if not fund_skill_prompt:
            _log_to_job(job, "⚠️ No skill prompt found, using empty")

        # Create agent with thread-safe repos (same as Scheduler does)
        fund_llm = ClaudeProvider(api_key=api_key, model=CLAUDE_SONNET)
        fund_agent = FundamentalAgent(llm=fund_llm)

        job["agents"] = ["Fundamental"]
        positions = [p for p in watchlist if p.id]

        if not positions:
            _log_to_job(job, "❌ Keine Positionen mit ID in Watchlist")
            error_msg = "Keine Positionen mit ID in Watchlist"
        else:
            _log_to_job(job, f"Running FundamentalAgent on {len(positions)} positions")
            try:
                results = loop.run_until_complete(
                    fund_agent.analyze_portfolio(
                        positions=positions,
                        skill_name=fund_skill_name,
                        skill_prompt=fund_skill_prompt,
                        analyses_repo=analyses_repo,
                    )
                )
                count = len(results) if results else len(positions)
                _log_to_job(job, f"✅ FundamentalAgent completed: {count} analyzed")
            except Exception as exc:
                error_msg = f"FundamentalAgent failed: {str(exc)}"
                _log_to_job(job, f"❌ {error_msg}")
                raise

        job.update({"running": False, "done": True, "count": count, "error": error_msg})

    except Exception as exc:
        error_msg = str(exc)
        logger.exception("Background Fundamental job failed")
        job.update({"running": False, "done": True, "count": count, "error": error_msg})

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
_JOB_DEFAULTS = {"running": False, "done": False, "count": 0, "errors": 0, "error": None, "agents": [], "logs": []}

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

        # Show logs if available
        if _job.get("logs"):
            with st.expander("📋 Logs"):
                st.text("\n".join(_job.get("logs", [])))

        if st.button("Dismiss", key=f"dismiss_{_label}"):
            # Clear repo caches so next render gets fresh data from DB
            try:
                get_analyses_repo.clear()
            except Exception:
                pass
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
                # Only run if fundamental has missing analyses
                if any(s["n_missing"] > 0 and s["agent_name"] == "fundamental" for s in _analyses_status):
                    _WC_FUND_JOB.update({**_JOB_DEFAULTS, "running": True, "agents": ["Fundamental Analyzer"]})
                    threading.Thread(
                        target=_run_fundamental_job,
                        args=(watchlist, _WC_FUND_JOB,
                              config.DB_PATH, config.ENCRYPTION_KEY, config.ANTHROPIC_API_KEY),
                        daemon=True,
                    ).start()
                    st.rerun()

# Skill selector for Watchlist Checker
st.divider()
skills_repo = get_skills_repo()
watchlist_skills = skills_repo.get_by_area("watchlist_checker")
skill_options = {s.name: s for s in watchlist_skills if not s.hidden}

if skill_options:
    skill_names = list(skill_options.keys())
    selected_skill_name = st.selectbox(
        "Fokus-Bereich",
        options=skill_names,
        index=0,  # Default to first skill (Josef's Regel)
        key="watchlist_checker_skill",
    )
    selected_skill = skill_options[selected_skill_name]
else:
    selected_skill = None

if st.button("▶️ Watchlist prüfen", key="check_watchlist_btn"):
    with st.spinner("Watchlist wird geprüft..."):
        # Build complete context (analog to Portfolio Story)
        portfolio = positions_repo.get_portfolio()
        market_agent = get_market_agent()

        # Get valuations as dict (ticker -> PortfolioValuation)
        valuations_list = market_agent.get_portfolio_valuation() if market_agent else []
        valuations = {v.symbol: v for v in valuations_list} if valuations_list else {}

        # Portfolio snapshot with values + Josef-Regel categories
        portfolio_snapshot = "## Portfolio\n"
        if portfolio:
            for p in portfolio:
                val = valuations.get(p.ticker) if p.ticker else None
                val_eur = val.current_value_eur if val and val.current_value_eur else 0
                portfolio_snapshot += f"- {p.name} ({p.ticker}, {p.asset_class}): {val_eur:.0f}€\n"
        else:
            portfolio_snapshot += "(Leer)\n"

        # Complete story analysis context with full_text
        story_analysis_text = None
        story_analysis = portfolio_story_repo.get_latest_analysis()
        if story_analysis:
            story_analysis_text = f"""## Portfolio Story Context
Story: {story_analysis.verdict}
Summary: {story_analysis.summary}
Performance: {story_analysis.perf_verdict} - {story_analysis.perf_summary}
Stabilität: {story_analysis.stability_verdict} - {story_analysis.stability_summary}

Full Analysis:
{story_analysis.full_text}
"""

        # Run check
        try:
            result = asyncio.run(
                agent.check_watchlist(
                    portfolio_snapshot=portfolio_snapshot,
                    watchlist_positions=watchlist,
                    story_analysis_text=story_analysis_text,
                    selected_skill=selected_skill,
                )
            )

            # Calculate fit counts from result
            fit_counts = {
                "sehr_passend": sum(1 for f in result.position_fits if f.verdict == "sehr_passend"),
                "passend": sum(1 for f in result.position_fits if f.verdict == "passend"),
                "neutral": sum(1 for f in result.position_fits if f.verdict == "neutral"),
                "nicht_passend": sum(1 for f in result.position_fits if f.verdict == "nicht_passend"),
            }

            # Serialize position fits
            position_fits_json = json.dumps([{
                "position_id": fit.position_id,
                "verdict": fit.verdict,
                "summary": fit.summary,
            } for fit in result.position_fits])

            # Save to DB
            from core.storage.models import WatchlistCheckerAnalysis

            # Extract summary from "## Zusammenfassung" section if present
            # Fallback: use fit_counts summary if Zusammenfassung not found
            summary = None
            if result.full_text:
                zusammenfassung_idx = result.full_text.find("## Zusammenfassung")
                if zusammenfassung_idx != -1:
                    # Get text after the "## Zusammenfassung" header
                    after = result.full_text[zusammenfassung_idx:].split('\n', 1)
                    if len(after) > 1:
                        body = after[1].strip()
                        # First non-empty line is the summary
                        first_line = next((l.strip() for l in body.split('\n') if l.strip()), None)
                        summary = first_line[:200] if first_line else None

            # Fallback: if no Zusammenfassung section found, create summary from fit counts
            if not summary:
                summary = f"Geprüft: {fit_counts['sehr_passend']} sehr passend, {fit_counts['passend']} passend, {fit_counts['neutral']} neutral, {fit_counts['nicht_passend']} nicht passend"

            analysis = WatchlistCheckerAnalysis(
                summary=summary,
                full_text=result.full_text,
                fit_counts=fit_counts,  # Already a dict
                position_fits_json=position_fits_json,
                skill_name=selected_skill.name if selected_skill else "",
                model=agent.model,
                created_at=datetime.now(),
            )
            wc_repo = get_watchlist_checker_repo()
            saved_analysis = wc_repo.save_analysis(analysis)

            # Log to agent_runs
            agent_runs_repo.log_run(
                agent_name="watchlist_checker",
                model=agent.model,
                output_summary=f"Checked {len(watchlist)} positions: {fit_counts['sehr_passend']} sehr passend, {fit_counts['passend']} passend",
                context_summary=f"Portfolio ({len(portfolio)} pos), Story ({bool(story_analysis)}), Skill ({selected_skill.name if selected_skill else 'Standard'})",
            )

            st.success("✅ Watchlist-Prüfung durchgeführt!")
            # Store the saved analysis from DB (has summary + fit_counts fields)
            st.session_state["_watchlist_check_result"] = saved_analysis
            st.session_state["_watchlist_check_analysis_id"] = saved_analysis.id

        except Exception as e:
            st.error(f"❌ Fehler: {e}")
            import traceback
            st.text(traceback.format_exc())

# ─────────────────────────────────────────────────────────────────────
# Section 2: Display Results (persistent from DB)
# ─────────────────────────────────────────────────────────────────────

from dataclasses import dataclass as _dataclass

@_dataclass
class _DisplayFit:
    """Normalized fit object for display."""
    position_id: int
    verdict: str
    summary: str


def _normalize_result(result):
    """Convert WatchlistCheckerAnalysis or WatchlistCheckResult to normalized form."""
    # If it has position_fits directly (fresh from agent), return as-is
    if hasattr(result, 'position_fits') and result.position_fits:
        return result, result.position_fits

    # If it has position_fits_json (from DB), deserialize
    if hasattr(result, 'position_fits_json') and result.position_fits_json:
        try:
            fits_data = json.loads(result.position_fits_json)
            position_fits = [_DisplayFit(**fit) for fit in fits_data]
            return result, position_fits
        except Exception as e:
            logger.warning(f"Failed to deserialize position_fits_json: {e}")
            return result, []

    return result, []


wc_repo = get_watchlist_checker_repo()

# Try to load from session_state first, else from DB
if not st.session_state.get("_watchlist_check_result"):
    latest_analysis = wc_repo.get_latest_analysis()
    if latest_analysis:
        # Reconstruct result from DB (for display purposes)
        st.session_state["_watchlist_check_result"] = latest_analysis
    else:
        latest_analysis = None
else:
    latest_analysis = st.session_state.get("_watchlist_check_result")

if st.session_state.get("_watchlist_check_result"):
    st.divider()
    st.subheader("2️⃣ Ergebnisse")

    result = st.session_state["_watchlist_check_result"]
    result, position_fits = _normalize_result(result)

    # Summary shown via AI comment below (not redundant with verdict counts)

    # Parse fit_counts if stored in DB (JSON string)
    if hasattr(result, 'fit_counts'):
        try:
            if isinstance(result.fit_counts, str):
                fit_counts = json.loads(result.fit_counts)
            else:
                fit_counts = result.fit_counts or {}
        except:
            fit_counts = {
                "sehr_passend": sum(1 for f in position_fits if f.verdict == "sehr_passend"),
                "passend": sum(1 for f in position_fits if f.verdict == "passend"),
                "neutral": sum(1 for f in position_fits if f.verdict == "neutral"),
                "nicht_passend": sum(1 for f in position_fits if f.verdict == "nicht_passend"),
            }
    else:
        fit_counts = {
            "sehr_passend": sum(1 for f in position_fits if f.verdict == "sehr_passend"),
            "passend": sum(1 for f in position_fits if f.verdict == "passend"),
            "neutral": sum(1 for f in position_fits if f.verdict == "neutral"),
            "nicht_passend": sum(1 for f in position_fits if f.verdict == "nicht_passend"),
        }

    _wc_config = VERDICT_CONFIGS["watchlist_checker"]
    st.markdown(
        f"{verdict_icon('sehr_passend', _wc_config)} Sehr passend: {fit_counts.get('sehr_passend', 0)} | "
        f"{verdict_icon('passend', _wc_config)} Passend: {fit_counts.get('passend', 0)} | "
        f"{verdict_icon('neutral', _wc_config)} Neutral: {fit_counts.get('neutral', 0)} | "
        f"{verdict_icon('nicht_passend', _wc_config)} Nicht passend: {fit_counts.get('nicht_passend', 0)}"
    )

    st.divider()
    st.markdown("**Position-Details**")

    # Bulk-fetch analyses for all watchlist positions (used in expanders below)
    _all_fit_ids = [fit.position_id for fit in position_fits if fit.position_id]
    _bulk_story = analyses_repo.get_latest_bulk(_all_fit_ids, "storychecker") if _all_fit_ids else {}
    _bulk_fund = analyses_repo.get_latest_bulk(_all_fit_ids, "fundamental") if _all_fit_ids else {}
    _bulk_consensus = analyses_repo.get_latest_bulk(_all_fit_ids, "consensus_gap") if _all_fit_ids else {}

    # Display position fits
    for fit in position_fits:
        pos = next((p for p in watchlist if p.id == fit.position_id), None)
        if pos:
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])

                with col1:
                    # Verdict emoji
                    _wc_config = VERDICT_CONFIGS["watchlist_checker"]
                    verdict_emoji = verdict_icon(fit.verdict, _wc_config)
                    st.markdown(f"**{verdict_emoji} {pos.name}** ({pos.ticker})")
                    st.caption(fit.summary)

                with col2:
                    st.metric("Fit", fit.verdict.replace("_", " ").title())

                # Position details (Story, Fundamental Analysis, Consensus Gap)
                with st.expander("📋 Position-Details"):
                    detail_cols = st.columns(3)

                    # Story Analysis (pre-fetched in bulk above)
                    with detail_cols[0]:
                        st.caption("**Story Checker**")
                        latest_story = _bulk_story.get(pos.id) if pos.id in _bulk_story else None
                        if latest_story and latest_story.verdict:
                            _sc_config = VERDICT_CONFIGS["storychecker"]
                            _icon = verdict_icon(latest_story.verdict, _sc_config)
                            st.markdown(f"{_icon} {latest_story.verdict}")
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
                            _fa_config = VERDICT_CONFIGS["fundamental_analyzer"]
                            _icon = verdict_icon(verdict, _fa_config)
                            st.markdown(f"{_icon} {verdict or 'unbekannt'}")
                            if latest_fund.summary:
                                st.caption(latest_fund.summary)
                        else:
                            st.caption("⚪ Noch nicht analysiert")

                    # Consensus Gap (pre-fetched in bulk above)
                    with detail_cols[2]:
                        st.caption("**Konsens-Lücke**")
                        latest_consensus = _bulk_consensus.get(pos.id) if pos.id in _bulk_consensus else None
                        if latest_consensus and latest_consensus.verdict:
                            verdict = latest_consensus.verdict
                            _cg_config = VERDICT_CONFIGS["consensus_gap"]
                            _icon = verdict_icon(verdict, _cg_config)
                            st.markdown(f"{_icon} {verdict or 'unbekannt'}")
                            if latest_consensus.summary:
                                st.caption(latest_consensus.summary)
                        else:
                            st.caption("⚪ Noch nicht analysiert")

    # --- KI-Kommentar (Auto-generated) --

    _comment_style_id = get_app_config_repo().get("comment_style") or "humorvoll"
    _comment_style = get_style_by_id(_comment_style_id)
    comment_service = get_portfolio_comment_service()

    # Auto-generate comment with current context
    with st.spinner(f"{_comment_style['emoji']} Generiere Kommentar..."):
        full_text = result.full_text if hasattr(result, 'full_text') else ""
        _ctx = f"Watchlist-Check Ergebnis:\n{full_text}"
        st.session_state["_watchlist_comment"] = comment_service.generate_comment(_ctx, _comment_style_id)

    st.divider()
    st.subheader("3️⃣ KI-Kommentar")

    if st.session_state.get("_watchlist_comment"):
        with st.container(border=True):
            st.caption(f"{_comment_style['emoji']} **{_comment_style['name']}**")
            st.markdown(st.session_state["_watchlist_comment"])

    # --- Details (Metadata + Full Analysis) --

    st.divider()
    with st.expander("📋 Vollständige Analyse & Metadaten"):
        st.caption("**Vollständige LLM-Analyse**")
        st.text(result.full_text if hasattr(result, 'full_text') else "")

        st.divider()
        st.caption("**Agent Metadata**")
        latest_run = agent_runs_repo.get_latest_run("watchlist_checker")
        if latest_run:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Agent", latest_run["agent_name"])
            with col2:
                st.metric("Model", latest_run["model"])
            with col3:
                st.metric("Timestamp", latest_run["created_at"][:10])  # Just date
            st.caption(f"Context: {latest_run['context_summary']}")
