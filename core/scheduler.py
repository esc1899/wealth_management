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
    ):
        self._db_path = db_path
        self._enc_key = encryption_key
        self._anthropic_key = anthropic_api_key
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
        """Trigger a job immediately in a background thread."""
        import threading
        threading.Thread(target=self._dispatch_job, args=[job_id], daemon=True).start()

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

            if job.agent_name == "news":
                await self._run_news_job(job, conn)
            elif job.agent_name == "structural_scan":
                await self._run_structural_scan_job(job, conn)
            elif job.agent_name == "consensus_gap":
                await self._run_consensus_gap_job(job, conn)
            else:
                logger.warning("Unknown agent_name '%s' in job %s", job.agent_name, job_id)
                return
            jobs_repo.update_last_run(job_id)
        finally:
            conn.close()

    def _make_scheduled_llm(self, agent_name: str, model: str, conn) -> "ClaudeProvider":
        from core.llm.claude import ClaudeProvider
        usage_repo = UsageRepository(conn)
        llm = ClaudeProvider(api_key=self._anthropic_key, model=model)
        llm.on_usage = lambda i, o, skill=None, dur=None: usage_repo.record(
            agent_name, model, i, o, skill=skill, source="scheduled", duration_ms=dur
        )
        return llm

    async def _run_news_job(self, job: ScheduledJob, conn) -> None:
        from agents.news_agent import NewsAgent

        enc = build_encryption_service(self._enc_key, "data/salt.bin")
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
        from core.storage.structural_scans import StructuralScansRepository

        enc = build_encryption_service(self._enc_key, "data/salt.bin")
        model = job.model or self._default_claude_model
        llm = self._make_scheduled_llm("structural_scan", model, conn)
        positions_repo = PositionsRepository(conn, enc)
        scans_repo = StructuralScansRepository(conn)
        agent = StructuralChangeAgent(positions_repo=positions_repo, llm=llm)
        await agent.start_scan(
            skill_name=job.skill_name,
            skill_prompt=job.skill_prompt,
            user_focus=None,
            repo=scans_repo,
        )
        logger.info("Structural scan job %s completed", job.id)

    async def _run_consensus_gap_job(self, job, conn) -> None:
        from agents.consensus_gap_agent import ConsensusGapAgent
        from core.storage.analyses import PositionAnalysesRepository

        enc = build_encryption_service(self._enc_key, "data/salt.bin")
        model = job.model or self._default_claude_model
        llm = self._make_scheduled_llm("consensus_gap", model, conn)
        positions_repo = PositionsRepository(conn, enc)
        analyses_repo = PositionAnalysesRepository(conn)
        agent = ConsensusGapAgent(llm=llm)
        positions = positions_repo.get_portfolio()
        await agent.analyze_portfolio(
            positions=positions,
            skill_name=job.skill_name,
            skill_prompt=job.skill_prompt,
            analyses_repo=analyses_repo,
        )
        logger.info("Consensus gap job %s completed", job.id)

    def _open_conn(self):
        conn = get_connection(self._db_path)
        init_db(conn)
        migrate_db(conn)
        return conn
