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

def _resolve_model_from_conn(conn, agent_key: str, default: str, job: dict | None = None) -> str:
    """Das Modell eines Laufs: im Durchgang das der Liste (``job["modell"]``, core/pruefung.py),
    sonst der Eintrag des Agenten."""
    if job and job.get("modell"):
        return job["modell"]
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
    from core.llm.router import (resolve_house_model, resolve_provider_kind,
                                 tavily_news_mode, tavily_search_depth)

    model = resolve_house_model(
        model, has_anthropic=bool(config.LLM_API_KEY),
        has_openai_base=bool(config.OPENAI_BASE_URL),
        fallback=config.CLAUDE_MODELS[0] if config.CLAUDE_MODELS else "")

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


def _resolve_skill(jobs_repo: ScheduledJobsRepository, skills_repo, agent_name: str,
                   job: dict | None = None) -> tuple[str, str]:
    """Der Skill eines Checks: aus dem Durchgang (``job["skill"]``), sonst aus der Auswahl der
    Listen (Einstellungen, core/pruefung.py), sonst der Standard. Die Jobs je Check sind seit
    Schritt 2 abgeschaltet und tragen keinen Skill mehr."""
    if job and job.get("skill"):
        return job["skill"]
    try:
        from core.pruefung import MOEGLICH, skill_fuer, skills
        app_cfg = AppConfigRepository(jobs_repo._conn)
        for liste in MOEGLICH:
            if agent_name in skills(app_cfg, liste):
                return skill_fuer(app_cfg, skills_repo, liste, agent_name)
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
        skill_name, _ = _resolve_skill(jobs_repo, skills_repo, "storychecker", job)
        _sc_model = _resolve_model_from_conn(conn, "storychecker", CLAUDE_HAIKU, job)
        llm = _make_bg_llm(_sc_model, "storychecker", _usage_repo)
        llm.skill_context = skill_name
        agent = StorycheckerAgent(positions_repo=positions_repo, storychecker_repo=storychecker_repo, analyses_repo=analyses_repo, llm=llm, skills_repo=skills_repo)
        pos_valid = [p for p in positions if p.id]
        _log_to_job(job, f"StorycheckerAgent: {len(pos_valid)} positions")
        results = loop.run_until_complete(agent.batch_check_all(positions=pos_valid, language=language))
        count = sum(1 for _, err in results if err is None)
        _log_to_job(job, f"StorycheckerAgent: {count}/{len(pos_valid)} completed")
        fehler = [f"Story Checker, {name}: {err}" for name, err in results if err]
        job.update({"running": False, "done": True, "count": count, "error": "; ".join(fehler) or None})
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
        skill_name, skill_prompt = _resolve_skill(jobs_repo, skills_repo, "consensus_gap", job)
        _cg_model = _resolve_model_from_conn(conn, "consensus_gap", CLAUDE_SONNET, job)
        llm = _make_bg_llm(_cg_model, "consensus_gap", _usage_repo)
        agent = ConsensusGapAgent(llm=llm, analyses_repo=analyses_repo, cg_repo=cg_repo)
        pos_valid = [p for p in positions if p.id]
        _log_to_job(job, f"ConsensusGapAgent: {len(pos_valid)} positions")
        loop.run_until_complete(agent.analyze_portfolio(pos_valid, skill_name, skill_prompt, language=language))
        count = len(pos_valid) - len(agent.fehler)
        _log_to_job(job, f"ConsensusGapAgent: {count} completed")
        fehler = "; ".join(f"Konsens, {f}" for f in agent.fehler) or None
        job.update({"running": False, "done": True, "count": count, "error": fehler})
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
        fund_skill_name, fund_skill_prompt = _resolve_skill(jobs_repo, skills_repo, "fundamental_analyzer", job)
        _log_to_job(job, f"Skill resolved: '{fund_skill_name}'")
        _usage_repo = UsageRepository(conn)
        _fa_model = _resolve_model_from_conn(conn, "fundamental_analyzer", CLAUDE_HAIKU, job)
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
            count = len(results) if results else 0
            _log_to_job(job, f"✅ FundamentalAnalyzerAgent completed: {count} analyzed")
            if fund_agent.fehler:
                error_msg = "; ".join(f"Fundamental, {f}" for f in fund_agent.fehler)
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
        ca_skill_name, ca_skill_prompt = _resolve_skill(jobs_repo, skills_repo, "capital_allocator", job)
        _log_to_job(job, f"Skill resolved: '{ca_skill_name}'")
        _usage_repo = UsageRepository(conn)
        _ca_model = _resolve_model_from_conn(conn, "capital_allocator", CLAUDE_SONNET, job)
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
                error_msg = ("; ".join(f"Kapitalallokation, {f}" for f in ca_agent.fehler) if ca_agent.fehler
                             else f"{no_verdict} von {len(valid)} Positionen ohne Verdict — ggf. DeepSeek Tool-Use erneut versuchen")
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
        da_skill_name, da_skill_prompt = _resolve_skill(jobs_repo, skills_repo, "devils_advocate", job)
        _log_to_job(job, f"Skill resolved: '{da_skill_name}'")
        _usage_repo = UsageRepository(conn)
        _da_model = _resolve_model_from_conn(conn, "devils_advocate", CLAUDE_SONNET, job)
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
                error_msg = ("; ".join(f"Devil's Advocate, {f}" for f in da_agent.fehler) if da_agent.fehler
                             else f"{no_verdict} von {len(valid)} Positionen ohne Verdict")
            _log_to_job(job, f"✅ DevilsAdvocateAgent completed: {count} analyzed")
        job.update({"running": False, "done": True, "count": count, "error": error_msg})
    except Exception as exc:
        logger.exception("Background Devils Advocate job failed")
        job.update({"running": False, "done": True, "count": count, "error": str(exc)})
    finally:
        loop.close()
        if conn:
            conn.close()


def run_watchlist_checker_job(positions: list, language: str, job: dict, db_path: str, enc_key: str, api_key: str) -> None:
    """Der Watchlist Checker (lokal, Ollama) fuer diese Titel: passen sie zum Depot? Liest die
    Urteile der anderen Checks -- im Durchgang darum zuletzt (core/pruefung.py)."""
    from core.pruefung import depot_kontext
    from core.i18n import t
    from state import get_portfolio_service, get_portfolio_story_repo, get_watchlist_checker_agent
    count = 0
    try:
        job["agents"] = ["Watchlist Checker"]
        valid = [p for p in positions if p.id]
        snapshot, story = depot_kontext(
            get_portfolio_service().get_portfolio_positions(),
            get_portfolio_story_repo().get_latest_analysis(),
            stabilitaet=t("watchlist_checker.stability_label"),
            leer=t("watchlist_checker.empty_portfolio"),
        )
        _log_to_job(job, f"WatchlistCheckerAgent: {len(valid)} positions")
        result = asyncio.run(get_watchlist_checker_agent().check_watchlist(
            portfolio_snapshot=snapshot, watchlist_positions=valid,
            story_analysis_text=story, selected_skill=None, language=language,
        ))
        count = len(result.position_fits)
        error_msg = None if count else "Watchlist Checker: kein Urteil erhalten"
        job.update({"running": False, "done": True, "count": count, "error": error_msg})
    except Exception as exc:
        logger.exception("Background Watchlist Checker job failed")
        job.update({"running": False, "done": True, "count": count, "error": str(exc)})


#: Je Check der Lauf im Hintergrund; alle mit derselben Signatur.
CHECK_JOBS = {
    "storychecker": run_storychecker_job,
    "consensus_gap": run_consensus_gap_job,
    "fundamental_analyzer": run_fundamental_job,
    "capital_allocator": run_capital_allocator_job,
    "devils_advocate": run_devils_advocate_job,
    "watchlist_checker": run_watchlist_checker_job,
}


def _parallel(checks, position, language: str, db_path: str, enc_key: str, api_key: str,
              skill_je_check: dict | None = None, modell: str = "") -> list[str]:
    import threading

    zustaende, threads = [], []
    for check in checks:
        z = {"running": True, "done": False, "count": 0, "error": None}
        if skill_je_check and check in skill_je_check:
            z["skill"] = skill_je_check[check]
        if modell:
            z["modell"] = modell
        th = threading.Thread(target=CHECK_JOBS[check], daemon=True,
                              args=([position], language, z, db_path, enc_key, api_key))
        th.start()
        zustaende.append(z)
        threads.append(th)
    for th in threads:
        th.join()
    return [z["error"] for z in zustaende if z["error"]]


def run_durchgang(position, liste: str, checks, language: str, job: dict, db_path: str,
                  enc_key: str, api_key: str, ausloeser: str = "knopf") -> None:
    """Ein Durchgang fuer einen Titel: die gewaehlten Checks, ein Datum. Erst die Cloud-Checks
    parallel, dann die, die deren Urteile lesen; ein scheiternder Check haelt die anderen nicht
    auf. ``job`` wie bei den anderen Laeufen, dazu ``durchgang_id``."""
    from core.pruefung import reihenfolge
    from core.storage.durchgaenge import DurchgaengeRepository

    conn = None
    try:
        conn = get_connection(db_path)
        init_db(conn)
        migrate_db(conn)
        repo = DurchgaengeRepository(conn)
        checks = tuple(checks)
        durchgang_id = repo.beginnen(liste, position.id, ausloeser, checks)
        job["durchgang_id"] = durchgang_id
        from core.pruefung import SKILL_BEREICH, modell as modell_der_liste, skill_fuer
        from core.storage.skills import SkillsRepository
        app_cfg, skills_repo = AppConfigRepository(conn), SkillsRepository(conn)
        skill_je_check = {c: skill_fuer(app_cfg, skills_repo, liste, c)
                          for c in checks if c in SKILL_BEREICH}
        fehler: list[str] = []
        for stufe in reihenfolge(checks):
            if stufe:
                fehler += _parallel(stufe, position, language, db_path, enc_key, api_key,
                                    skill_je_check, modell_der_liste(app_cfg, liste))
        zugeordnet = repo.abschliessen(durchgang_id, "; ".join(fehler) or None)
        _log_to_job(job, f"Durchgang {durchgang_id}: {zugeordnet} Urteile, {len(fehler)} Fehler")
        job.update({"running": False, "done": True, "count": zugeordnet, "error": None, "fehler": fehler})
    except Exception as exc:
        logger.exception("Durchgang failed")
        job.update({"running": False, "done": True, "count": 0, "error": str(exc),
                    "fehler": [str(exc)]})
    finally:
        if conn:
            conn.close()
