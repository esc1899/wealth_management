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
import os
import threading
import time
import streamlit as st
from datetime import datetime

from core.ui.verdicts import VERDICT_CONFIGS, verdict_icon, cloud_notice
from core.i18n import t, current_language

st.set_page_config(page_title="Watchlist Checker", layout="wide")

from state import (
    get_analysis_service,
    get_portfolio_service,
    get_watchlist_checker_agent,
    get_portfolio_story_repo,
    get_agent_runs_repo,
    get_portfolio_comment_model,
    get_portfolio_comment_service,
    get_app_config_repo,
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
    language: str,
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
        salt_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), "salt.bin")
        enc = build_encryption_service(enc_key, salt_path)
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
                results = loop.run_until_complete(sc_agent.batch_check_all(positions=watchlist_positions, language=language))
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
            cg_agent = ConsensusGapAgent(llm=cg_llm, analyses_repo=analyses_repo)
            try:
                _log_to_job(job, f"Running ConsensusGapAgent with skill '{cg_skill_name}'")
                loop.run_until_complete(
                    cg_agent.analyze_portfolio(watchlist_positions, cg_skill_name, cg_skill_prompt, language=language)
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
    language: str,
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
        salt_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), "salt.bin")
        enc = build_encryption_service(enc_key, salt_path)
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
        fund_agent = FundamentalAgent(llm=fund_llm, analyses_repo=analyses_repo)

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
                        language=language,
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

st.title(f"📋 {t('watchlist_checker.title')}")
st.caption(t("watchlist_checker.subtitle"))

# ─────────────────────────────────────────────────────────────────────
# Section 1: Run Watchlist Check
# ─────────────────────────────────────────────────────────────────────

st.subheader(t("watchlist_checker.check_section"))

_portfolio_service = get_portfolio_service()
_analysis_service = get_analysis_service()
portfolio_story_repo = get_portfolio_story_repo()
agent = get_watchlist_checker_agent()
agent_runs_repo = get_agent_runs_repo()
cloud_notice(agent.model, provider="ollama")

watchlist = _portfolio_service.get_watchlist_positions()

if not watchlist:
    st.info(t("watchlist_checker.no_watchlist"))
    st.stop()

st.caption(t("watchlist_checker.watchlist_count").format(n=len(watchlist)))

# Ermittle offene Checks — analog Portfolio Story
watchlist_ids = [pos.id for pos in watchlist if pos.id]
sc_verdicts = _analysis_service.get_verdicts(watchlist_ids, "storychecker")
cg_verdicts = _analysis_service.get_verdicts(watchlist_ids, "consensus_gap")
fund_verdicts = _analysis_service.get_verdicts(watchlist_ids, "fundamental")

n_missing_sc_cg = sum(1 for pid in watchlist_ids if pid not in sc_verdicts or pid not in cg_verdicts)
n_missing_fund = sum(1 for pid in watchlist_ids if pid not in fund_verdicts)

# Timestamps
latest_sc_ts = max((v.created_at for v in sc_verdicts.values() if v and hasattr(v, 'created_at') and v.created_at), default=None)
latest_fund_ts = max((v.created_at for v in fund_verdicts.values() if v and hasattr(v, 'created_at') and v.created_at), default=None)
sc_ts_str = t("watchlist_checker.ts_last_run").format(ts=latest_sc_ts.strftime('%d.%m. %H:%M')) if latest_sc_ts else t("watchlist_checker.ts_never")
fund_ts_str = t("watchlist_checker.ts_last_run").format(ts=latest_fund_ts.strftime('%d.%m. %H:%M')) if latest_fund_ts else t("watchlist_checker.ts_never")

# Info-Meldungen
if n_missing_sc_cg > 0:
    st.info(t("watchlist_checker.pending_story_info").format(n=n_missing_sc_cg, total=len(watchlist_ids), ts=sc_ts_str))
if n_missing_fund > 0:
    st.info(t("watchlist_checker.pending_fund_info").format(n=n_missing_fund, total=len(watchlist_ids), ts=fund_ts_str))

# Checkboxen für Pre-Checks
run_sc_cg_checks = st.checkbox(
    t("watchlist_checker.run_story_checkbox"),
    value=False,
    key="_wc_run_sc_cg",
    disabled=n_missing_sc_cg == 0,
)
run_fund_checks = st.checkbox(
    t("watchlist_checker.run_fund_checkbox"),
    value=False,
    key="_wc_run_fund",
    disabled=n_missing_fund == 0,
)

if st.button(t("watchlist_checker.run_button"), key="check_watchlist_btn"):
    _lang = current_language()

    # Pre-Check 1: Story + Konsens (blocking, nur offene)
    if run_sc_cg_checks and n_missing_sc_cg > 0:
        _missing_sc_cg = [p for p in watchlist if p.id and (p.id not in sc_verdicts or p.id not in cg_verdicts)]
        _job = {"running": True, "done": False, "count": 0, "error": None, "logs": []}
        agents_to_run = ["storychecker", "consensus_gap"]
        threading.Thread(
            target=_run_storychecker_consensus_job,
            args=(_missing_sc_cg, agents_to_run, _lang, _job,
                  config.DB_PATH, config.ENCRYPTION_KEY, config.ANTHROPIC_API_KEY),
            daemon=True,
        ).start()
        with st.spinner(t("watchlist_checker.running_story_spinner").format(n=len(_missing_sc_cg))):
            while _job["running"]:
                time.sleep(1)
        if _job["error"]:
            st.error(f"❌ {_job['error']}")
        else:
            st.success(t("watchlist_checker.story_checks_done").format(n=_job['count']))

    # Pre-Check 2: Fundamental (blocking, nur offene)
    if run_fund_checks and n_missing_fund > 0:
        _missing_fund = [p for p in watchlist if p.id and p.id not in fund_verdicts]
        _fund_job = {"running": True, "done": False, "count": 0, "error": None, "logs": []}
        threading.Thread(
            target=_run_fundamental_job,
            args=(_missing_fund, _lang, _fund_job,
                  config.DB_PATH, config.ENCRYPTION_KEY, config.ANTHROPIC_API_KEY),
            daemon=True,
        ).start()
        with st.spinner(t("watchlist_checker.running_fund_spinner").format(n=len(_missing_fund))):
            while _fund_job["running"]:
                time.sleep(1)
        if _fund_job["error"]:
            st.error(f"❌ {_fund_job['error']}")
        else:
            st.success(t("watchlist_checker.fund_checks_done").format(n=_fund_job['count']))

    # Hauptcheck
    with st.spinner(t("watchlist_checker.checking_spinner")):
        # Build complete context (analog to Portfolio Story)
        portfolio = _portfolio_service.get_portfolio_positions()
        market_agent = get_market_agent()

        # Get valuations as dict (ticker -> PortfolioValuation)
        valuations_list = market_agent.get_portfolio_valuation() if market_agent else []
        valuations = {v.symbol: v for v in valuations_list} if valuations_list else {}

        # Portfolio snapshot with values
        portfolio_snapshot = "## Portfolio\n"
        if portfolio:
            for p in portfolio:
                val = valuations.get(p.ticker) if p.ticker else None
                val_eur = val.current_value_eur if val and val.current_value_eur else 0
                div_str = ""
                if val and val.annual_dividend_eur and val.annual_dividend_eur > 0:
                    div_str = t("watchlist_checker.dividend_label").format(val=f"{val.annual_dividend_eur:.0f}€/Jahr ({(val.dividend_yield_pct or 0) * 100:.1f}%)", source=val.dividend_source or 'unbekannt')
                portfolio_snapshot += f"- {p.name} ({p.ticker}, {p.asset_class}): {val_eur:.0f}€{div_str}\n"
        else:
            portfolio_snapshot += t("watchlist_checker.empty_portfolio") + "\n"

        # Complete story analysis context with full_text
        story_analysis_text = None
        story_analysis = portfolio_story_repo.get_latest_analysis()
        if story_analysis:
            story_analysis_text = f"""## Portfolio Story Context
Story: {story_analysis.verdict}
Summary: {story_analysis.summary}
Performance: {story_analysis.perf_verdict} - {story_analysis.perf_summary}
{t("watchlist_checker.stability_label")} {story_analysis.stability_verdict} - {story_analysis.stability_summary}

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
                    selected_skill=None,
                    language=_lang,
                )
            )

            st.success(t("watchlist_checker.check_done"))
            st.session_state["_watchlist_check_result"] = result

        except Exception as e:
            st.error(t("watchlist_checker.error").format(error=str(e)))

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
    st.subheader(t("watchlist_checker.results_section"))

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
        except (json.JSONDecodeError, ValueError):
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
        f"{verdict_icon('sehr_passend', _wc_config)} {t('watchlist_checker.very_fitting')}: {fit_counts.get('sehr_passend', 0)} | "
        f"{verdict_icon('passend', _wc_config)} {t('watchlist_checker.fitting')}: {fit_counts.get('passend', 0)} | "
        f"{verdict_icon('neutral', _wc_config)} {t('watchlist_checker.neutral')}: {fit_counts.get('neutral', 0)} | "
        f"{verdict_icon('nicht_passend', _wc_config)} {t('watchlist_checker.not_fitting')}: {fit_counts.get('nicht_passend', 0)}"
    )

    st.divider()
    st.markdown(t("watchlist_checker.position_details_header"))

    # Bulk-fetch analyses for all watchlist positions (used in expanders below)
    _all_fit_ids = [fit.position_id for fit in position_fits if fit.position_id]
    _bulk_story = _analysis_service.get_verdicts(_all_fit_ids, "storychecker") if _all_fit_ids else {}
    _bulk_fund = _analysis_service.get_verdicts(_all_fit_ids, "fundamental") if _all_fit_ids else {}
    _bulk_consensus = _analysis_service.get_verdicts(_all_fit_ids, "consensus_gap") if _all_fit_ids else {}

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
                with st.expander(t("watchlist_checker.position_details_label")):
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
                            st.caption(t("watchlist_checker.not_analyzed"))

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
                            st.caption(t("watchlist_checker.not_analyzed"))

    # --- KI-Kommentar (Auto-generated, cached) --

    from core.services.portfolio_comment_service import get_style_by_id
    import hashlib

    _comment_style_id = get_app_config_repo().get("comment_style") or "humorvoll"
    _comment_style = get_style_by_id(_comment_style_id)
    comment_service = get_portfolio_comment_service(get_portfolio_comment_model())

    # Cache by context + style hash (regenerate only if input changes)
    full_text = result.full_text if hasattr(result, 'full_text') else ""
    _ctx = f"Watchlist-Check Ergebnis:\n{full_text}"
    _ctx_hash = hashlib.md5((_ctx + _comment_style_id).encode()).hexdigest()

    if st.session_state.get("_watchlist_comment_hash") != _ctx_hash:
        with st.spinner(f"{_comment_style['emoji']} {t('watchlist_checker.ai_comment_spinner')}"):
            try:
                st.session_state["_watchlist_comment"] = comment_service.generate_comment(_ctx, _comment_style_id)
                st.session_state["_watchlist_comment_hash"] = _ctx_hash
            except Exception as _e:
                logger.warning("KI-Kommentar fehlgeschlagen: %s", _e)
                st.warning(t("watchlist_checker.ai_comment_unavailable"))

    st.divider()
    st.subheader(t("watchlist_checker.ai_comment_section"))

    if st.session_state.get("_watchlist_comment"):
        with st.container(border=True):
            st.caption(f"{_comment_style['emoji']} **{_comment_style['name']}**")
            st.markdown(st.session_state["_watchlist_comment"])

    # --- Details (Metadata + Full Analysis) --

    st.divider()
    with st.expander(t("watchlist_checker.full_analysis_label")):
        st.caption(t("watchlist_checker.full_llm_label"))
        st.text(result.full_text if hasattr(result, 'full_text') else "")

        st.divider()
        st.caption(t("watchlist_checker.metadata_label"))
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
