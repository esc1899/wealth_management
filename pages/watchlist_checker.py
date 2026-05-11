"""
Watchlist Checker — evaluates which watchlist positions fit into the portfolio.

FEAT-40 Cockpit Refactor (2026-05-11):
- Section 1: Status-Matrix (alle Kandidaten × alle 4 Sub-Checks + WC-Fit)
- Section 2: Main WatchlistCheckerAgent run (Ollama, lokal)
- Section 3: Ergebnisse (vereinfachte Position-Cards, kein 4-Spalten-Expander)
- One-Click "Alle fehlenden Checks ausführen" Button
"""

import asyncio
import json
import logging
import os
import threading
import time
import streamlit as st
from dataclasses import dataclass as _dataclass
from datetime import datetime

import pandas as pd

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
    get_positions_repo,
)
from core.services.portfolio_comment_service import get_style_by_id
from config import config
from core.storage.base import get_connection, init_db, migrate_db, build_encryption_service
from core.storage.app_config import AppConfigRepository
from core.storage.positions import PositionsRepository
from core.storage.analyses import PositionAnalysesRepository
from core.storage.storychecker import StorycheckerRepository
from core.storage.scheduled_jobs import ScheduledJobsRepository
from agents.storychecker_agent import StorycheckerAgent
from agents.consensus_gap_agent import ConsensusGapAgent
from agents.fundamental_analyzer_agent import FundamentalAnalyzerAgent
from agents.capital_allocator_agent import CapitalAllocatorAgent
from core.llm.claude import ClaudeProvider
from core.constants import CLAUDE_HAIKU, CLAUDE_SONNET, AGENT_SKILL_DEFAULTS
from core.storage.usage import UsageRepository


logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Helpers: Display normalization
# ------------------------------------------------------------------

@_dataclass
class _DisplayFit:
    """Normalized fit object for display."""
    position_id: int
    verdict: str
    summary: str


def _normalize_result(result):
    """Convert WatchlistCheckerAnalysis or WatchlistCheckResult to normalized form."""
    if hasattr(result, 'position_fits') and result.position_fits:
        return result, result.position_fits
    if hasattr(result, 'position_fits_json') and result.position_fits_json:
        try:
            fits_data = json.loads(result.position_fits_json)
            position_fits = [_DisplayFit(**fit) for fit in fits_data]
            return result, position_fits
        except Exception as e:
            logger.warning(f"Failed to deserialize position_fits_json: {e}")
            return result, []
    return result, []


def _fmt_verdict(v, config_key: str) -> str:
    """Format a verdict object as 'emoji verdict' or '⚪ —' if missing."""
    if v and v.verdict:
        icon = verdict_icon(v.verdict, VERDICT_CONFIGS[config_key])
        return f"{icon} {v.verdict}"
    return "⚪ —"


# ------------------------------------------------------------------
# Helper: Model resolution from a background-thread DB connection
# ------------------------------------------------------------------

def _resolve_model_from_conn(conn, agent_key: str, default: str) -> str:
    """Read per-agent model from app_config using the thread-local DB connection."""
    model_type = "openai" if config.OPENAI_BASE_URL else "claude"
    app_cfg = AppConfigRepository(conn)
    return (
        app_cfg.get(f"model_{model_type}_{agent_key}")
        or app_cfg.get(f"model_{model_type}")
        or config.LLM_DEFAULT_MODEL
        or default
    )


# ------------------------------------------------------------------
# Helper: Logging (write to job dict for UI visibility)
# ------------------------------------------------------------------

def _log_to_job(job: dict, msg: str) -> None:
    if "logs" not in job:
        job["logs"] = []
    job["logs"].append(msg)
    logger.info(msg)


# ------------------------------------------------------------------
# Helper: Skill Resolution
# ------------------------------------------------------------------

def _resolve_skill(
    jobs_repo: ScheduledJobsRepository,
    skills_repo,
    agent_name: str,
) -> tuple[str, str]:
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
    default_skill = AGENT_SKILL_DEFAULTS.get(agent_name, "Standard")
    return default_skill, ""


# ------------------------------------------------------------------
# Background Job 1a: StorycheckerAgent
# ------------------------------------------------------------------

def _run_storychecker_job(
    positions: list,
    language: str,
    job: dict,
    db_path: str,
    enc_key: str,
    api_key: str,
) -> None:
    conn = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    count = 0
    try:
        conn = get_connection(db_path)
        init_db(conn)
        migrate_db(conn)
        salt_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), "salt.bin")
        enc = build_encryption_service(enc_key, salt_path)
        positions_repo = PositionsRepository(conn, enc)
        analyses_repo = PositionAnalysesRepository(conn)
        storychecker_repo = StorycheckerRepository(conn)
        skills_repo = get_skills_repo()
        jobs_repo = ScheduledJobsRepository(conn)
        _usage_repo = UsageRepository(conn)
        job["agents"] = ["Story Checker"]
        skill_name, _ = _resolve_skill(jobs_repo, skills_repo, "storychecker")
        _sc_model = _resolve_model_from_conn(conn, "storychecker", CLAUDE_HAIKU)
        if config.OPENAI_BASE_URL:
            from core.llm.openai_compatible import OpenAICompatibleProvider
            llm = OpenAICompatibleProvider(api_key=config.OPENAI_API_KEY, model=config.LLM_DEFAULT_MODEL or "sonar", base_url=config.OPENAI_BASE_URL)
        else:
            llm = ClaudeProvider(api_key=api_key, model=_sc_model, base_url=config.LLM_BASE_URL)
        llm.skill_context = skill_name
        llm.on_usage = lambda i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None, web_search=None, _m=llm.model, _r=_usage_repo: _r.record("storychecker", _m, i, o, skill=skill, source="manual", duration_ms=dur, position_count=pos, cache_read_tokens=cache_read, cache_write_tokens=cache_write, web_search_requests=web_search)
        agent = StorycheckerAgent(positions_repo=positions_repo, storychecker_repo=storychecker_repo, analyses_repo=analyses_repo, llm=llm, skills_repo=skills_repo)
        pos_valid = [p for p in positions if p.id]
        _log_to_job(job, f"StorycheckerAgent: {len(pos_valid)} positions")
        results = loop.run_until_complete(agent.batch_check_all(positions=pos_valid, language=language))
        count = sum(1 for _, err in results if err is None)
        _log_to_job(job, f"StorycheckerAgent: {count}/{len(pos_valid)} completed")
        job.update({"running": False, "done": True, "count": count, "error": None})
    except Exception as exc:
        logger.exception("StorycheckerAgent job failed")
        job.update({"running": False, "done": True, "count": count, "error": str(exc)})
    finally:
        loop.close()
        if conn:
            conn.close()


# ------------------------------------------------------------------
# Background Job 1b: ConsensusGapAgent
# ------------------------------------------------------------------

def _run_consensus_gap_job(
    positions: list,
    language: str,
    job: dict,
    db_path: str,
    enc_key: str,
    api_key: str,
) -> None:
    from core.storage.consensus_gap import ConsensusGapRepository
    conn = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    count = 0
    try:
        conn = get_connection(db_path)
        init_db(conn)
        migrate_db(conn)
        analyses_repo = PositionAnalysesRepository(conn)
        cg_repo = ConsensusGapRepository(conn)
        skills_repo = get_skills_repo()
        jobs_repo = ScheduledJobsRepository(conn)
        _usage_repo = UsageRepository(conn)
        job["agents"] = ["Konsens-Lücken"]
        skill_name, skill_prompt = _resolve_skill(jobs_repo, skills_repo, "consensus_gap")
        _cg_model = _resolve_model_from_conn(conn, "consensus_gap", CLAUDE_SONNET)
        if config.OPENAI_BASE_URL:
            from core.llm.openai_compatible import OpenAICompatibleProvider
            llm = OpenAICompatibleProvider(api_key=config.OPENAI_API_KEY, model=config.LLM_DEFAULT_MODEL or "sonar", base_url=config.OPENAI_BASE_URL)
        else:
            llm = ClaudeProvider(api_key=api_key, model=_cg_model, base_url=config.LLM_BASE_URL)
        llm.on_usage = lambda i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None, web_search=None, _m=llm.model, _r=_usage_repo: _r.record("consensus_gap", _m, i, o, skill=skill, source="manual", duration_ms=dur, position_count=pos, cache_read_tokens=cache_read, cache_write_tokens=cache_write, web_search_requests=web_search)
        agent = ConsensusGapAgent(llm=llm, analyses_repo=analyses_repo, cg_repo=cg_repo)
        pos_valid = [p for p in positions if p.id]
        _log_to_job(job, f"ConsensusGapAgent: {len(pos_valid)} positions")
        loop.run_until_complete(agent.analyze_portfolio(pos_valid, skill_name, skill_prompt, language=language))
        count = len(pos_valid)
        _log_to_job(job, f"ConsensusGapAgent: {count} completed")
        job.update({"running": False, "done": True, "count": count, "error": None})
    except Exception as exc:
        logger.exception("ConsensusGapAgent job failed")
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
    language: str,
    job: dict,
    db_path: str,
    enc_key: str,
    api_key: str,
) -> None:
    from core.storage.analyses import PositionAnalysesRepository

    conn = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    count = 0
    error_msg = None

    try:
        conn = get_connection(db_path)
        init_db(conn)
        migrate_db(conn)

        salt_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), "salt.bin")
        enc = build_encryption_service(enc_key, salt_path)
        positions_repo = PositionsRepository(conn, enc)
        analyses_repo = PositionAnalysesRepository(conn)
        skills_repo = get_skills_repo()
        jobs_repo = ScheduledJobsRepository(conn)

        fund_skill_name, fund_skill_prompt = _resolve_skill(jobs_repo, skills_repo, "fundamental_analyzer")
        _log_to_job(job, f"Skill resolved: '{fund_skill_name}'")

        _usage_repo = UsageRepository(conn)
        _fa_model = _resolve_model_from_conn(conn, "fundamental_analyzer", CLAUDE_HAIKU)

        if config.OPENAI_BASE_URL:
            from core.llm.openai_compatible import OpenAICompatibleProvider
            fund_llm = OpenAICompatibleProvider(api_key=config.OPENAI_API_KEY, model=config.LLM_DEFAULT_MODEL or "sonar", base_url=config.OPENAI_BASE_URL)
        else:
            fund_llm = ClaudeProvider(api_key=api_key, model=_fa_model, base_url=config.LLM_BASE_URL)
        fund_llm.on_usage = lambda i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None, web_search=None, _m=fund_llm.model, _r=_usage_repo: _r.record("fundamental_analyzer", _m, i, o, skill=skill, source="manual", duration_ms=dur, position_count=pos, cache_read_tokens=cache_read, cache_write_tokens=cache_write, web_search_requests=web_search)
        from core.storage.fundamental_analyzer import FundamentalAnalyzerRepository
        fund_repo = FundamentalAnalyzerRepository(conn)
        fund_agent = FundamentalAnalyzerAgent(positions_repo=positions_repo, analyses_repo=analyses_repo, fa_repo=fund_repo, llm=fund_llm)

        job["agents"] = ["Fundamental"]
        positions = [p for p in watchlist if p.id]
        from core.storage.models import PublicPosition
        pub_positions = [PublicPosition(id=p.id, name=p.name, ticker=p.ticker, isin=p.isin, asset_class=p.asset_class, anlageart=p.anlageart, story=p.story, story_skill=p.story_skill) for p in positions]

        if not positions:
            error_msg = "Keine Positionen mit ID in Watchlist"
            _log_to_job(job, f"❌ {error_msg}")
        else:
            _log_to_job(job, f"Running FundamentalAnalyzerAgent on {len(positions)} positions")
            try:
                results = loop.run_until_complete(
                    fund_agent.analyze_portfolio(
                        positions=pub_positions,
                        skill_name=fund_skill_name,
                        skill_prompt=fund_skill_prompt,
                        language=language,
                    )
                )
                count = len(results) if results else len(positions)
                _log_to_job(job, f"✅ FundamentalAnalyzerAgent completed: {count} analyzed")
            except Exception as exc:
                error_msg = f"FundamentalAnalyzerAgent failed: {str(exc)}"
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


# ------------------------------------------------------------------
# Background Job 3: CapitalAllocatorAgent
# ------------------------------------------------------------------

def _run_capital_allocator_job(
    watchlist: list,
    language: str,
    job: dict,
    db_path: str,
    enc_key: str,
    api_key: str,
) -> None:
    conn = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    count = 0
    error_msg = None

    try:
        conn = get_connection(db_path)
        init_db(conn)
        migrate_db(conn)

        analyses_repo = PositionAnalysesRepository(conn)
        skills_repo = get_skills_repo()
        jobs_repo = ScheduledJobsRepository(conn)

        ca_skill_name, ca_skill_prompt = _resolve_skill(jobs_repo, skills_repo, "capital_allocator")
        _log_to_job(job, f"Skill resolved: '{ca_skill_name}'")

        _usage_repo = UsageRepository(conn)
        _ca_model = _resolve_model_from_conn(conn, "capital_allocator", CLAUDE_SONNET)

        if config.OPENAI_BASE_URL:
            from core.llm.openai_compatible import OpenAICompatibleProvider
            ca_llm = OpenAICompatibleProvider(api_key=config.OPENAI_API_KEY, model=config.LLM_DEFAULT_MODEL or "sonar", base_url=config.OPENAI_BASE_URL)
        else:
            ca_llm = ClaudeProvider(api_key=api_key, model=_ca_model, base_url=config.LLM_BASE_URL)
        ca_llm.on_usage = lambda i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None, web_search=None, _m=ca_llm.model, _r=_usage_repo: _r.record("capital_allocator", _m, i, o, skill=skill, source="manual", duration_ms=dur, position_count=pos, cache_read_tokens=cache_read, cache_write_tokens=cache_write, web_search_requests=web_search)

        from core.storage.capital_allocator import CapitalAllocatorRepository
        ca_repo = CapitalAllocatorRepository(conn)
        ca_agent = CapitalAllocatorAgent(llm=ca_llm, analyses_repo=analyses_repo, ca_repo=ca_repo)

        job["agents"] = ["Kapitalallokator"]
        positions = [p for p in watchlist if p.id]
        from core.storage.models import PublicPosition
        pub_positions = [PublicPosition(id=p.id, name=p.name, ticker=p.ticker, isin=p.isin, asset_class=p.asset_class, anlageart=p.anlageart, story=p.story, story_skill=p.story_skill) for p in positions]

        if not positions:
            error_msg = "Keine Positionen mit ID in Watchlist"
            _log_to_job(job, f"❌ {error_msg}")
        else:
            _log_to_job(job, f"Running CapitalAllocatorAgent on {len(positions)} positions")
            try:
                results = loop.run_until_complete(
                    ca_agent.analyze_portfolio(
                        positions=pub_positions,
                        skill_name=ca_skill_name,
                        skill_prompt=ca_skill_prompt,
                        language=language,
                    )
                )
                count = len(results) if results else len(positions)
                _log_to_job(job, f"✅ CapitalAllocatorAgent completed: {count} analyzed")
            except Exception as exc:
                error_msg = f"CapitalAllocatorAgent failed: {str(exc)}"
                _log_to_job(job, f"❌ {error_msg}")
                raise

        job.update({"running": False, "done": True, "count": count, "error": error_msg})

    except Exception as exc:
        error_msg = str(exc)
        logger.exception("Background Capital Allocator job failed")
        job.update({"running": False, "done": True, "count": count, "error": error_msg})
    finally:
        loop.close()
        if conn:
            conn.close()


# ─────────────────────────────────────────────────────────────────────
# Page Header
# ─────────────────────────────────────────────────────────────────────

st.title(f"📋 {t('watchlist_checker.title')}")
st.caption(t("watchlist_checker.subtitle"))

# ─────────────────────────────────────────────────────────────────────
# Init: Services + Data
# ─────────────────────────────────────────────────────────────────────

_portfolio_service = get_portfolio_service()
_analysis_service = get_analysis_service()
portfolio_story_repo = get_portfolio_story_repo()
agent = get_watchlist_checker_agent()
agent_runs_repo = get_agent_runs_repo()
wc_repo = get_watchlist_checker_repo()

watchlist = _portfolio_service.get_watchlist_positions()

if not watchlist:
    st.info(t("watchlist_checker.no_watchlist"))
    st.stop()

st.caption(t("watchlist_checker.watchlist_count").format(n=len(watchlist)))

# Pre-fetch all sub-check verdicts
watchlist_ids = [pos.id for pos in watchlist if pos.id]
sc_verdicts = _analysis_service.get_verdicts(watchlist_ids, "storychecker")
cg_verdicts = _analysis_service.get_verdicts(watchlist_ids, "consensus_gap")
fund_verdicts = _analysis_service.get_verdicts(watchlist_ids, "fundamental_analyzer")
ca_verdicts = _analysis_service.get_verdicts(watchlist_ids, "capital_allocator")

# Pre-load WC fits for matrix WC-Fit column
_latest_wc_result = wc_repo.get_latest_analysis()
_wc_fits: dict[int, _DisplayFit] = {}
if _latest_wc_result:
    _, _fits_list = _normalize_result(_latest_wc_result)
    _wc_fits = {f.position_id: f for f in _fits_list}

# Missing counts
n_missing_sc = sum(1 for pid in watchlist_ids if pid not in sc_verdicts)
n_missing_cg = sum(1 for pid in watchlist_ids if pid not in cg_verdicts)
n_missing_fund = sum(1 for pid in watchlist_ids if pid not in fund_verdicts)
n_missing_ca = sum(1 for pid in watchlist_ids if pid not in ca_verdicts)
n_total_missing = n_missing_sc + n_missing_cg + n_missing_fund + n_missing_ca

# Post-run success toast (set by cockpit button, shown after st.rerun())
if cockpit_msg := st.session_state.pop("_cockpit_done_msg", None):
    st.success(cockpit_msg)
if cockpit_errors := st.session_state.pop("_cockpit_errors", None):
    for _err in cockpit_errors:
        st.error(f"❌ {_err}")

# ─────────────────────────────────────────────────────────────────────
# Section 1: Status-Matrix (NEU, FEAT-40)
# ─────────────────────────────────────────────────────────────────────

st.subheader(t("watchlist_checker.cockpit_section"))

# Build matrix
matrix_rows = []
for pos in watchlist:
    if not pos.id:
        continue
    wc_fit = _wc_fits.get(pos.id)
    matrix_rows.append({
        "name": pos.name,
        "ticker": pos.ticker or "—",
        "sc": _fmt_verdict(sc_verdicts.get(pos.id), "storychecker"),
        "fa": _fmt_verdict(fund_verdicts.get(pos.id), "fundamental_analyzer"),
        "cg": _fmt_verdict(cg_verdicts.get(pos.id), "consensus_gap"),
        "ca": _fmt_verdict(ca_verdicts.get(pos.id), "capital_allocator"),
        "wc": (_fmt_verdict(wc_fit, "watchlist_checker") if wc_fit else "⚪ —"),
    })

_matrix_selection = st.dataframe(
    pd.DataFrame(matrix_rows),
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "name": st.column_config.TextColumn("Position", width="medium"),
        "ticker": st.column_config.TextColumn("Ticker", width="small"),
        "sc": st.column_config.TextColumn(t("watchlist_checker.cockpit_col_sc"), width="medium"),
        "fa": st.column_config.TextColumn(t("watchlist_checker.cockpit_col_fa"), width="medium"),
        "cg": st.column_config.TextColumn(t("watchlist_checker.cockpit_col_cg"), width="medium"),
        "ca": st.column_config.TextColumn(t("watchlist_checker.cockpit_col_ca"), width="medium"),
        "wc": st.column_config.TextColumn(t("watchlist_checker.cockpit_col_wc"), width="medium"),
    },
)

# Delete dialog for selected position
@st.dialog(t("watchlist_checker.delete_confirm_title"))
def _show_delete_dialog(pos_id: int, pos_name: str) -> None:
    st.warning(t("watchlist_checker.delete_confirm_warning").format(name=pos_name))
    col_yes, col_no = st.columns(2)
    if col_yes.button(t("watchlist_checker.delete_confirm_yes"), type="primary", use_container_width=True):
        get_positions_repo().delete(pos_id)
        st.toast(t("watchlist_checker.delete_done"), icon="🗑️")
        st.rerun()
    if col_no.button(t("watchlist_checker.delete_confirm_no"), use_container_width=True):
        st.rerun()


if del_pending := st.session_state.pop("_wc_delete_pending", None):
    _show_delete_dialog(del_pending["id"], del_pending["name"])

# Navigation für ausgewählte Zeile
_selected_rows = _matrix_selection.selection.rows if _matrix_selection.selection else []
_valid_positions = [p for p in watchlist if p.id]
if _selected_rows and _selected_rows[0] < len(_valid_positions):
    _sel_pos = _valid_positions[_selected_rows[0]]
    _nav_col1, _nav_col2, _nav_spacer = st.columns([1, 1, 3])
    with _nav_col1:
        if st.button(t("watchlist_analysis.nav_button"), key="nav_to_wla_btn", use_container_width=True):
            st.session_state["wla_preselect_pos_id"] = _sel_pos.id
            st.switch_page("pages/watchlist_analysis.py")
    with _nav_col2:
        if st.button(t("watchlist_checker.delete_button"), key="nav_delete_btn", use_container_width=True):
            st.session_state["_wc_delete_pending"] = {"id": _sel_pos.id, "name": _sel_pos.name}
            st.rerun()

# One-click button
if n_total_missing > 0:
    n_incomplete_positions = sum(
        1 for pid in watchlist_ids
        if pid not in sc_verdicts or pid not in cg_verdicts
        or pid not in fund_verdicts or pid not in ca_verdicts
    )
    st.caption(t("watchlist_checker.cockpit_missing_summary").format(
        n=n_total_missing,
        positions=n_incomplete_positions,
    ))

    if st.button(t("watchlist_checker.cockpit_run_all_missing"), key="cockpit_run_all_btn"):
        _lang = current_language()
        total_done = 0
        _errors: list[str] = []

        def _run_job(target, positions, spinner_text, label, *extra_args):
            _job = {"running": True, "done": False, "count": 0, "error": None, "logs": []}
            threading.Thread(target=target, args=(positions, _lang, _job, config.DB_PATH, config.ENCRYPTION_KEY, config.LLM_API_KEY) + extra_args, daemon=True).start()
            with st.spinner(spinner_text):
                while _job["running"]:
                    time.sleep(1)
            if _job["error"]:
                _errors.append(f"{label}: {_job['error']}")
                return 0
            return _job["count"]

        if n_missing_sc > 0:
            _missing_sc = [p for p in watchlist if p.id and p.id not in sc_verdicts]
            total_done += _run_job(_run_storychecker_job, _missing_sc,
                t("watchlist_checker.running_story_spinner").format(n=len(_missing_sc)), "Story Checker")

        if n_missing_cg > 0:
            _missing_cg = [p for p in watchlist if p.id and p.id not in cg_verdicts]
            total_done += _run_job(_run_consensus_gap_job, _missing_cg,
                t("watchlist_checker.running_consensus_spinner").format(n=len(_missing_cg)), "Konsens-Lücken")

        if n_missing_fund > 0:
            _missing_fa = [p for p in watchlist if p.id and p.id not in fund_verdicts]
            total_done += _run_job(_run_fundamental_job, _missing_fa,
                t("watchlist_checker.running_fund_spinner").format(n=len(_missing_fa)), "Fundamental")

        if n_missing_ca > 0:
            _missing_ca = [p for p in watchlist if p.id and p.id not in ca_verdicts]
            total_done += _run_job(_run_capital_allocator_job, _missing_ca,
                t("capital_allocator.running_spinner").format(n=len(_missing_ca)), "Capital Allocator")

        if _errors:
            st.session_state["_cockpit_errors"] = _errors
        st.session_state["_cockpit_done_msg"] = t("watchlist_checker.cockpit_done").format(n=total_done)
        st.rerun()
else:
    st.success(t("watchlist_checker.cockpit_all_complete"))

# ─────────────────────────────────────────────────────────────────────
# Section 2: Watchlist prüfen (Main WatchlistCheckerAgent, Ollama)
# ─────────────────────────────────────────────────────────────────────

st.divider()
st.subheader(t("watchlist_checker.check_section"))
cloud_notice(agent.model, provider="ollama")

if st.button(t("watchlist_checker.run_button"), key="check_watchlist_btn"):
    _lang = current_language()

    with st.spinner(t("watchlist_checker.checking_spinner")):
        from collections import Counter
        portfolio = _portfolio_service.get_portfolio_positions()

        portfolio_snapshot = "## Portfolio Allocation (Josef's Regel)\n"
        if portfolio:
            counts = Counter(p.asset_class for p in portfolio if p.asset_class)
            total = len(portfolio)
            for asset_class, count in counts.most_common():
                pct = 100 * count / total if total else 0
                portfolio_snapshot += f"- {asset_class}: {count} Positionen ({pct:.0f}%)\n"
        else:
            portfolio_snapshot += t("watchlist_checker.empty_portfolio") + "\n"

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
# Section 3: Ergebnisse
# ─────────────────────────────────────────────────────────────────────

# Load result from session_state or DB
if not st.session_state.get("_watchlist_check_result"):
    if _latest_wc_result:
        st.session_state["_watchlist_check_result"] = _latest_wc_result

if st.session_state.get("_watchlist_check_result"):
    st.divider()
    st.subheader(t("watchlist_checker.results_section"))

    result = st.session_state["_watchlist_check_result"]
    result, position_fits = _normalize_result(result)

    # Fit-counts summary
    if hasattr(result, 'fit_counts'):
        try:
            fit_counts = json.loads(result.fit_counts) if isinstance(result.fit_counts, str) else (result.fit_counts or {})
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
        f"{verdict_icon('sehr_passend', _wc_config)} {t('watchlist_checker.very_fitting')} {fit_counts.get('sehr_passend', 0)} | "
        f"{verdict_icon('passend', _wc_config)} {t('watchlist_checker.fitting')} {fit_counts.get('passend', 0)} | "
        f"{verdict_icon('neutral', _wc_config)} {t('watchlist_checker.neutral')} {fit_counts.get('neutral', 0)} | "
        f"{verdict_icon('nicht_passend', _wc_config)} {t('watchlist_checker.not_fitting')} {fit_counts.get('nicht_passend', 0)}"
    )

    st.divider()
    st.markdown(t("watchlist_checker.position_details_header"))

    # Simplified position-fit cards (sub-check details are visible in matrix above)
    for fit in position_fits:
        pos = next((p for p in watchlist if p.id == fit.position_id), None)
        if pos:
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    verdict_emoji = verdict_icon(fit.verdict, _wc_config)
                    st.markdown(f"**{verdict_emoji} {pos.name}** ({pos.ticker})")
                    st.caption(fit.summary)
                with col2:
                    st.metric("Fit", fit.verdict.replace("_", " ").title())

    # KI-Kommentar
    import hashlib
    _comment_style_id = get_app_config_repo().get("comment_style") or "humorvoll"
    _comment_style = get_style_by_id(_comment_style_id)
    comment_service = get_portfolio_comment_service(get_portfolio_comment_model())

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
                st.metric("Timestamp", latest_run["created_at"][:10])
            st.caption(f"Context: {latest_run['context_summary']}")
