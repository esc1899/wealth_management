"""
Shared background job functions for running agent checks in background threads.

Used by portfolio_story.py and watchlist_checker.py to avoid code duplication.
All functions follow the same signature: (positions, language, job, db_path, enc_key, api_key).
The job dict is mutated in-place: {"running", "done", "count", "error", "logs"}.
"""

from __future__ import annotations

import asyncio
import logging
import os

from config import config
from core.constants import CLAUDE_HAIKU, CLAUDE_SONNET, AGENT_SKILL_DEFAULTS
from core.llm.claude import ClaudeProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.app_config import AppConfigRepository
from core.storage.base import get_connection, init_db, migrate_db, build_encryption_service
from core.storage.positions import PositionsRepository
from core.storage.scheduled_jobs import ScheduledJobsRepository
from core.storage.storychecker import StorycheckerRepository
from core.storage.usage import UsageRepository
from agents.storychecker_agent import StorycheckerAgent
from agents.consensus_gap_agent import ConsensusGapAgent
from agents.fundamental_analyzer_agent import FundamentalAnalyzerAgent
from agents.capital_allocator_agent import CapitalAllocatorAgent
from agents.devils_advocate_agent import DevilsAdvocateAgent

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Internal helpers (shared with both callers)
# ------------------------------------------------------------------

def _resolve_model_from_conn(conn, agent_key: str, default: str) -> str:
    model_type = "openai" if config.OPENAI_BASE_URL else "claude"
    app_cfg = AppConfigRepository(conn)
    return (
        app_cfg.get(f"model_public_{agent_key}")
        or app_cfg.get(f"model_{model_type}_{agent_key}")
        or app_cfg.get(f"model_{model_type}")
        or config.LLM_DEFAULT_MODEL
        or default
    )


def _make_bg_llm(model: str, agent_name: str, usage_repo: UsageRepository):
    """Create the correct LLM provider for a model — routing delegated to core.llm.router."""
    from core.llm.router import resolve_provider_kind, tavily_news_mode, tavily_search_depth

    def _on_usage(i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None, web_search=None):
        usage_repo.record(agent_name, model, i, o, skill=skill, source="manual", duration_ms=dur,
                          position_count=pos, cache_read_tokens=cache_read,
                          cache_write_tokens=cache_write, web_search_requests=web_search)

    kind = resolve_provider_kind(
        model,
        has_anthropic=bool(config.LLM_API_KEY),
        has_deepseek=bool(config.DEEPSEEK_API_KEY),
        has_openai_base=bool(config.OPENAI_BASE_URL),
    )
    if kind == "claude":
        llm = ClaudeProvider(api_key=config.LLM_API_KEY, model=model, base_url=config.LLM_BASE_URL)
    elif kind == "deepseek":
        from core.llm.openai_compatible import OpenAICompatibleProvider
        llm = OpenAICompatibleProvider(api_key=config.DEEPSEEK_API_KEY, model=model, base_url=config.DEEPSEEK_BASE_URL)
    else:
        from core.llm.openai_compatible import OpenAICompatibleProvider
        llm = OpenAICompatibleProvider(
            api_key=config.OPENAI_API_KEY, model=model, base_url=config.OPENAI_BASE_URL,
            tavily_news_mode=tavily_news_mode(agent_name), tavily_search_depth=tavily_search_depth(agent_name),
        )
    llm.on_usage = _on_usage
    return llm


def _log_to_job(job: dict, msg: str) -> None:
    if "logs" not in job:
        job["logs"] = []
    job["logs"].append(msg)
    logger.info(msg)


def _resolve_skill(jobs_repo: ScheduledJobsRepository, skills_repo, agent_name: str) -> tuple[str, str]:
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
    return AGENT_SKILL_DEFAULTS.get(agent_name, "Standard"), ""


# ------------------------------------------------------------------
# Public background job functions
# ------------------------------------------------------------------

def run_storychecker_job(positions: list, language: str, job: dict, db_path: str, enc_key: str, api_key: str) -> None:
    from state import get_skills_repo
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
        llm = _make_bg_llm(_sc_model, "storychecker", _usage_repo)
        llm.skill_context = skill_name
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


def run_consensus_gap_job(positions: list, language: str, job: dict, db_path: str, enc_key: str, api_key: str) -> None:
    from core.storage.consensus_gap import ConsensusGapRepository
    from state import get_skills_repo
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
        llm = _make_bg_llm(_cg_model, "consensus_gap", _usage_repo)
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


def run_fundamental_job(positions: list, language: str, job: dict, db_path: str, enc_key: str, api_key: str) -> None:
    from core.storage.fundamental_analyzer import FundamentalAnalyzerRepository
    from core.storage.models import PublicPosition
    from state import get_skills_repo
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
        fund_llm = _make_bg_llm(_fa_model, "fundamental_analyzer", _usage_repo)
        fund_repo = FundamentalAnalyzerRepository(conn)
        fund_agent = FundamentalAnalyzerAgent(positions_repo=positions_repo, analyses_repo=analyses_repo, fa_repo=fund_repo, llm=fund_llm)
        job["agents"] = ["Fundamental"]
        valid = [p for p in positions if p.id]
        pub_positions = [PublicPosition(id=p.id, name=p.name, ticker=p.ticker, isin=p.isin, asset_class=p.asset_class, anlageart=p.anlageart, story=p.story, story_skill=p.story_skill) for p in valid]
        if not valid:
            error_msg = "Keine Positionen mit ID"
            _log_to_job(job, f"❌ {error_msg}")
        else:
            _log_to_job(job, f"Running FundamentalAnalyzerAgent on {len(valid)} positions")
            results = loop.run_until_complete(
                fund_agent.analyze_portfolio(positions=pub_positions, skill_name=fund_skill_name, skill_prompt=fund_skill_prompt, language=language)
            )
            count = len(results) if results else len(valid)
            _log_to_job(job, f"✅ FundamentalAnalyzerAgent completed: {count} analyzed")
        job.update({"running": False, "done": True, "count": count, "error": error_msg})
    except Exception as exc:
        logger.exception("Background Fundamental job failed")
        job.update({"running": False, "done": True, "count": count, "error": str(exc)})
    finally:
        loop.close()
        if conn:
            conn.close()


def run_capital_allocator_job(positions: list, language: str, job: dict, db_path: str, enc_key: str, api_key: str) -> None:
    from core.storage.capital_allocator import CapitalAllocatorRepository
    from core.storage.models import PublicPosition
    from state import get_skills_repo
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
        ca_llm = _make_bg_llm(_ca_model, "capital_allocator", _usage_repo)
        ca_repo = CapitalAllocatorRepository(conn)
        ca_agent = CapitalAllocatorAgent(llm=ca_llm, analyses_repo=analyses_repo, ca_repo=ca_repo)
        job["agents"] = ["Kapitalallokator"]
        valid = [p for p in positions if p.id]
        pub_positions = [PublicPosition(id=p.id, name=p.name, ticker=p.ticker, isin=p.isin, asset_class=p.asset_class, anlageart=p.anlageart, story=p.story, story_skill=p.story_skill) for p in valid]
        if not valid:
            error_msg = "Keine Positionen mit ID"
            _log_to_job(job, f"❌ {error_msg}")
        else:
            _log_to_job(job, f"Running CapitalAllocatorAgent on {len(valid)} positions")
            results = loop.run_until_complete(
                ca_agent.analyze_portfolio(positions=pub_positions, skill_name=ca_skill_name, skill_prompt=ca_skill_prompt, language=language)
            )
            count = len(results) if results else 0
            no_verdict = len(valid) - count
            if no_verdict > 0:
                _log_to_job(job, f"⚠️ {no_verdict} position(s) got no verdict (LLM didn't call submit_ca_verdict)")
                error_msg = f"{no_verdict} von {len(valid)} Positionen ohne Verdict — ggf. DeepSeek Tool-Use erneut versuchen"
            _log_to_job(job, f"✅ CapitalAllocatorAgent completed: {count} analyzed")
        job.update({"running": False, "done": True, "count": count, "error": error_msg})
    except Exception as exc:
        logger.exception("Background Capital Allocator job failed")
        job.update({"running": False, "done": True, "count": count, "error": str(exc)})
    finally:
        loop.close()
        if conn:
            conn.close()


def run_devils_advocate_job(positions: list, language: str, job: dict, db_path: str, enc_key: str, api_key: str) -> None:
    from core.storage.devils_advocate import DevilsAdvocateRepository
    from core.storage.models import PublicPosition
    from state import get_skills_repo
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
        da_skill_name, da_skill_prompt = _resolve_skill(jobs_repo, skills_repo, "devils_advocate")
        _log_to_job(job, f"Skill resolved: '{da_skill_name}'")
        _usage_repo = UsageRepository(conn)
        _da_model = _resolve_model_from_conn(conn, "devils_advocate", CLAUDE_SONNET)
        da_llm = _make_bg_llm(_da_model, "devils_advocate", _usage_repo)
        da_repo = DevilsAdvocateRepository(conn)
        da_agent = DevilsAdvocateAgent(llm=da_llm, analyses_repo=analyses_repo, da_repo=da_repo)
        job["agents"] = ["Devil's Advocate"]
        valid = [p for p in positions if p.id and not getattr(p, "in_portfolio", False)]
        pub_positions = [PublicPosition(id=p.id, name=p.name, ticker=p.ticker, isin=p.isin, asset_class=p.asset_class, anlageart=p.anlageart, story=p.story, story_skill=p.story_skill) for p in valid]
        if not valid:
            error_msg = "Keine Watchlist-Positionen (ohne Portfolio) mit ID"
            _log_to_job(job, f"❌ {error_msg}")
        else:
            _log_to_job(job, f"Running DevilsAdvocateAgent on {len(valid)} watchlist positions")
            results = loop.run_until_complete(
                da_agent.analyze_portfolio(positions=pub_positions, skill_name=da_skill_name, skill_prompt=da_skill_prompt, language=language)
            )
            count = len(results) if results else 0
            no_verdict = len(valid) - count
            if no_verdict > 0:
                _log_to_job(job, f"⚠️ {no_verdict} position(s) got no verdict")
                error_msg = f"{no_verdict} von {len(valid)} Positionen ohne Verdict"
            _log_to_job(job, f"✅ DevilsAdvocateAgent completed: {count} analyzed")
        job.update({"running": False, "done": True, "count": count, "error": error_msg})
    except Exception as exc:
        logger.exception("Background Devils Advocate job failed")
        job.update({"running": False, "done": True, "count": count, "error": str(exc)})
    finally:
        loop.close()
        if conn:
            conn.close()
