"""
AgentSchedulerService — runs cloud agent jobs on a cron schedule.

Each ScheduledJob in the DB maps to an APScheduler job. On startup, all enabled
jobs are loaded and registered. Settings changes call reload_jobs() to sync.

Background thread safety: the service creates its own DB connection and agent
instances — it does NOT use Streamlit's @st.cache_resource singletons.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from core.storage.base import build_encryption_service, get_connection, init_db, migrate_db
from core.storage.models import ScheduledJob
from core.storage.news import NewsRepository
from core.storage.positions import PositionsRepository
from core.storage.scheduled_jobs import ScheduledJobsRepository
from core.storage.usage import UsageRepository

logger = logging.getLogger(__name__)

_JOB_ID_PREFIX = "agent_job_"


class AgentSchedulerService:
    """
    Singleton service that drives scheduled agent runs via APScheduler.

    Intentionally decoupled from Streamlit state — holds its own DB connection
    so background threads can safely access the database.
    """

    def __init__(
        self,
        db_path: str,
        encryption_key: str,
        anthropic_api_key: str,
        default_claude_model: str,
        timezone: str = "Europe/Berlin",
        llm_base_url: str = "",
        openai_api_key: str = "",
        openai_base_url: str = "",
    ):
        import os
        self._db_path = db_path
        self._salt_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), "salt.bin")
        self._enc_key = encryption_key
        self._anthropic_key = anthropic_api_key
        self._llm_base_url = llm_base_url
        self._openai_api_key = openai_api_key
        self._openai_base_url = openai_base_url
        self._default_claude_model = default_claude_model
        self._timezone = timezone
        self._scheduler = BackgroundScheduler(timezone=timezone)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._scheduler.start()
        self._reload_jobs()
        logger.info("AgentSchedulerService started")

    def reload_jobs(self) -> None:
        """Call after DB changes to re-sync APScheduler with stored jobs."""
        self._reload_jobs()

    def run_job_now(self, job_id: int) -> None:
        """Trigger a job immediately in a background thread, bypassing enabled check."""
        import threading

        def _run():
            try:
                asyncio.run(self._execute_job_force(job_id))
            except Exception:
                logger.exception("Manual job trigger %s failed", job_id)

        threading.Thread(target=_run, daemon=True).start()

    async def _execute_job_force(self, job_id: int) -> None:
        """Like _execute_job but runs regardless of enabled flag."""
        conn = self._open_conn()
        try:
            jobs_repo = ScheduledJobsRepository(conn)
            job = jobs_repo.get(job_id)
            if not job:
                return
            await self._dispatch_agent(job, conn)
            jobs_repo.update_last_run(job_id)
        except Exception as exc:
            logger.exception("Job force-run %s failed: %s", job_id, exc)
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _reload_jobs(self) -> None:
        # Remove all existing agent jobs
        for job in self._scheduler.get_jobs():
            if job.id.startswith(_JOB_ID_PREFIX):
                job.remove()

        conn = self._open_conn()
        try:
            jobs_repo = ScheduledJobsRepository(conn)
            for job in jobs_repo.get_enabled():
                trigger = self._build_trigger(job)
                self._scheduler.add_job(
                    func=self._dispatch_job,
                    trigger=trigger,
                    id=f"{_JOB_ID_PREFIX}{job.id}",
                    args=[job.id],
                    replace_existing=True,
                    misfire_grace_time=3600,
                )
                logger.info("Scheduled agent job %s (%s %s)", job.id, job.agent_name, job.frequency)
        finally:
            conn.close()

    def _build_trigger(self, job: ScheduledJob) -> CronTrigger:
        if job.frequency == "daily":
            return CronTrigger(
                hour=job.run_hour, minute=job.run_minute, timezone=self._timezone
            )
        elif job.frequency == "weekly":
            return CronTrigger(
                day_of_week=job.run_weekday or 0,
                hour=job.run_hour,
                minute=job.run_minute,
                timezone=self._timezone,
            )
        else:  # monthly
            return CronTrigger(
                day=job.run_day or 1,
                hour=job.run_hour,
                minute=job.run_minute,
                timezone=self._timezone,
            )

    def _dispatch_job(self, job_id: int) -> None:
        """Called by APScheduler in a background thread."""
        try:
            asyncio.run(self._execute_job(job_id))
        except Exception:
            logger.exception("Scheduled job %s failed", job_id)

    async def _execute_job(self, job_id: int) -> None:
        conn = self._open_conn()
        try:
            jobs_repo = ScheduledJobsRepository(conn)
            job = jobs_repo.get(job_id)
            if not job or not job.enabled:
                return
            await self._dispatch_agent(job, conn)
            jobs_repo.update_last_run(job_id)
        finally:
            conn.close()

    async def _dispatch_agent(self, job: ScheduledJob, conn) -> None:
        if job.agent_name == "news":
            await self._run_news_job(job, conn)
        elif job.agent_name == "structural_scan":
            await self._run_structural_scan_job(job, conn)
        elif job.agent_name == "consensus_gap":
            await self._run_consensus_gap_job(job, conn)
        elif job.agent_name == "storychecker":
            await self._run_storychecker_job(job, conn)
        elif job.agent_name == "fundamental":
            await self._run_fundamental_job(job, conn)
        elif job.agent_name == "wealth_snapshot":
            await self._run_wealth_snapshot_job(job, conn)
        else:
            logger.warning("Unknown agent_name '%s' in job %s", job.agent_name, job.id)

    def _make_scheduled_llm(self, agent_name: str, model: str, conn):
        from core.llm.claude import ClaudeProvider
        from core.llm.openai_compatible import OpenAICompatibleProvider
        usage_repo = UsageRepository(conn)
        if self._openai_base_url:
            llm = OpenAICompatibleProvider(api_key=self._openai_api_key, model=model, base_url=self._openai_base_url)
        else:
            llm = ClaudeProvider(api_key=self._anthropic_key, model=model, base_url=self._llm_base_url)
        llm.on_usage = lambda i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None: usage_repo.record(
            agent_name, model, i, o, skill=skill, source="scheduled", duration_ms=dur, position_count=pos, cache_read_tokens=cache_read, cache_write_tokens=cache_write
        )
        return llm

    async def _run_news_job(self, job: ScheduledJob, conn) -> None:
        from agents.news_agent import NewsAgent

        enc = build_encryption_service(self._enc_key, self._salt_path)
        positions_repo = PositionsRepository(conn, enc)
        news_repo = NewsRepository(conn)

        model = job.model or self._default_claude_model
        llm = self._make_scheduled_llm("news_digest", model, conn)
        agent = NewsAgent(llm=llm)

        positions = positions_repo.get_portfolio()
        tickers = [p.ticker for p in positions if p.ticker]
        if not tickers:
            logger.info("News job %s: no tickers in portfolio, skipping", job.id)
            return

        ticker_names = {p.ticker: p.name for p in positions if p.ticker}
        await agent.start_run(
            tickers=tickers,
            ticker_names=ticker_names,
            skill_name=job.skill_name,
            skill_prompt=job.skill_prompt,
            user_context="Automatisch geplanter News-Digest.",
            repo=news_repo,
        )
        logger.info("News job %s completed for %d tickers", job.id, len(tickers))

    async def _run_structural_scan_job(self, job, conn) -> None:
        from agents.structural_change_agent import StructuralChangeAgent
        from agents.storychecker_agent import StorycheckerAgent
        from core.storage.analyses import PositionAnalysesRepository
        from core.storage.skills import SkillsRepository
        from core.storage.storychecker import StorycheckerRepository
        from core.storage.structural_scans import StructuralScansRepository

        enc = build_encryption_service(self._enc_key, self._salt_path)
        model = job.model or self._default_claude_model
        llm = self._make_scheduled_llm("structural_scan", model, conn)
        positions_repo = PositionsRepository(conn, enc)
        scans_repo = StructuralScansRepository(conn)
        agent = StructuralChangeAgent(positions_repo=positions_repo, llm=llm)
        _, _, new_candidates = await agent.start_scan(
            skill_name=job.skill_name,
            skill_prompt=job.skill_prompt,
            user_focus=None,
            repo=scans_repo,
            language="de",
        )
        logger.info("Structural scan job %s completed — %d new candidates", job.id, len(new_candidates))

        if new_candidates:
            logger.info("Structural scan job %s: running story checks on %d candidates", job.id, len(new_candidates))
            sc_llm = self._make_scheduled_llm("storychecker", model, conn)
            storychecker = StorycheckerAgent(
                positions_repo=positions_repo,
                storychecker_repo=StorycheckerRepository(conn),
                analyses_repo=PositionAnalysesRepository(conn),
                llm=sc_llm,
                skills_repo=SkillsRepository(conn),
            )
            await storychecker.batch_check_all(positions=new_candidates, language="de")
            logger.info("Story checks done for structural scan job %s", job.id)

    async def _run_consensus_gap_job(self, job, conn) -> None:
        from agents.consensus_gap_agent import ConsensusGapAgent
        from core.storage.analyses import PositionAnalysesRepository

        enc = build_encryption_service(self._enc_key, self._salt_path)
        model = job.model or self._default_claude_model
        llm = self._make_scheduled_llm("consensus_gap", model, conn)
        positions_repo = PositionsRepository(conn, enc)
        analyses_repo = PositionAnalysesRepository(conn)
        agent = ConsensusGapAgent(llm=llm, analyses_repo=analyses_repo)
        positions = positions_repo.get_portfolio()
        await agent.analyze_portfolio(
            positions=positions,
            skill_name=job.skill_name,
            skill_prompt=job.skill_prompt,
            language="de",
        )
        logger.info("Consensus gap job %s completed", job.id)

    async def _run_storychecker_job(self, job, conn) -> None:
        from agents.storychecker_agent import StorycheckerAgent
        from core.storage.analyses import PositionAnalysesRepository
        from core.storage.skills import SkillsRepository
        from core.storage.storychecker import StorycheckerRepository

        enc = build_encryption_service(self._enc_key, self._salt_path)
        model = job.model or self._default_claude_model
        llm = self._make_scheduled_llm("storychecker", model, conn)
        positions_repo = PositionsRepository(conn, enc)
        analyses_repo = PositionAnalysesRepository(conn)
        storychecker_repo = StorycheckerRepository(conn)
        skills_repo = SkillsRepository(conn)
        agent = StorycheckerAgent(
            positions_repo=positions_repo,
            storychecker_repo=storychecker_repo,
            analyses_repo=analyses_repo,
            llm=llm,
            skills_repo=skills_repo,
        )
        positions = [p for p in positions_repo.get_all() if p.story]
        if not positions:
            logger.info("Storychecker job %s: no positions with story, skipping", job.id)
            return
        await agent.batch_check_all(positions=positions, language="de")
        logger.info("Storychecker job %s completed for %d positions", job.id, len(positions))

    async def _run_fundamental_job(self, job, conn) -> None:
        from agents.fundamental_agent import FundamentalAgent
        from core.storage.analyses import PositionAnalysesRepository

        enc = build_encryption_service(self._enc_key, self._salt_path)
        model = job.model or self._default_claude_model
        llm = self._make_scheduled_llm("fundamental", model, conn)
        positions_repo = PositionsRepository(conn, enc)
        analyses_repo = PositionAnalysesRepository(conn)
        agent = FundamentalAgent(llm=llm, analyses_repo=analyses_repo)
        positions = positions_repo.get_portfolio()
        await agent.analyze_portfolio(
            positions=positions,
            skill_name=job.skill_name,
            skill_prompt=job.skill_prompt,
            language="de",
        )
        logger.info("Fundamental job %s completed for %d positions", job.id, len(positions))

    async def _run_wealth_snapshot_job(self, job: ScheduledJob, conn) -> None:
        """Create a periodic wealth snapshot (no LLM needed)."""
        from agents.wealth_snapshot_agent import WealthSnapshotAgent
        from core.storage.market_data import MarketDataRepository
        from core.storage.wealth_snapshots import WealthSnapshotRepository

        enc = build_encryption_service(self._enc_key, self._salt_path)
        positions_repo = PositionsRepository(conn, enc)
        market_repo = MarketDataRepository(conn)
        wealth_repo = WealthSnapshotRepository(conn)

        # Create a temporary market data agent for portfolio valuation
        from agents.market_data_fetcher import MarketDataFetcher, RateLimiter
        fetcher = MarketDataFetcher(rate_limiter=RateLimiter(calls_per_second=1))
        market_data_agent = MarketDataAgent(
            positions_repo=positions_repo,
            market_repo=market_repo,
            fetcher=fetcher,
            db_path=self._db_path,
            encryption_key=self._enc_key,
        )

        # Take snapshot
        agent = WealthSnapshotAgent(
            positions_repo=positions_repo,
            market_repo=market_repo,
            wealth_repo=wealth_repo,
            market_data_agent=market_data_agent,
        )

        snapshot = agent.take_snapshot(is_manual=False)
        logger.info(
            "Wealth snapshot job %s completed: %s EUR (%d%% coverage)",
            job.id,
            f"{snapshot.total_eur:,.0f}",
            int(snapshot.coverage_pct),
        )

    def _open_conn(self):
        conn = get_connection(self._db_path)
        init_db(conn)
        migrate_db(conn)
        return conn
