"""
Scheduler run hygiene:
  * orphaned 'running' rows are closed on startup instead of hanging forever
  * the daily wealth snapshot job tolerates the snapshot MarketDataAgent already
    took after the price fetch (idempotent instead of permanently failing)

Uses an in-memory SQLite database — no file I/O.
"""

import sqlite3
from datetime import date
from unittest.mock import MagicMock, Mock, patch

import pytest

from core.scheduler import AgentSchedulerService
from core.storage.base import init_db, migrate_db
from core.storage.models import ScheduledJob, WealthSnapshot
from core.storage.scheduled_jobs import ScheduledJobRunsRepository, ScheduledJobsRepository


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    migrate_db(c)
    return c


@pytest.fixture
def runs_repo(conn):
    return ScheduledJobRunsRepository(conn)


@pytest.fixture
def job_id(conn):
    job = ScheduledJobsRepository(conn).add(
        ScheduledJob(
            agent_name="storychecker",
            skill_name="",
            skill_prompt="",
            frequency="monthly",
            run_hour=8,
            run_minute=0,
        )
    )
    return job.id


@pytest.fixture
def scheduler():
    return AgentSchedulerService(
        db_path=":memory:",
        encryption_key="test-key",
        anthropic_api_key="test-api",
        default_claude_model="claude-haiku-4-5-20251001",
    )


# ------------------------------------------------------------------
# Orphaned runs
# ------------------------------------------------------------------

def test_fail_orphaned_closes_running_rows(runs_repo, job_id):
    """A run whose process died stays 'running' — startup must close it."""
    run = runs_repo.create(job_id)

    closed = runs_repo.fail_orphaned()

    assert closed == 1
    stored = runs_repo.get_for_job(job_id)[0]
    assert stored.status == "failed"
    assert stored.completed_at is not None
    assert "Neustart" in stored.error_msg


def test_fail_orphaned_leaves_finished_runs_untouched(runs_repo, job_id):
    """Success and failure rows must keep their status and error message."""
    ok = runs_repo.create(job_id)
    runs_repo.complete(ok.id)
    bad = runs_repo.create(job_id)
    runs_repo.fail(bad.id, "Boom")

    assert runs_repo.fail_orphaned() == 0

    by_id = {r.id: r for r in runs_repo.get_for_job(job_id)}
    assert by_id[ok.id].status == "success"
    assert by_id[bad.id].status == "failed"
    assert by_id[bad.id].error_msg == "Boom"


def test_fail_orphaned_is_idempotent(runs_repo, job_id):
    """Second startup finds nothing left to close."""
    runs_repo.create(job_id)

    assert runs_repo.fail_orphaned() == 1
    assert runs_repo.fail_orphaned() == 0


def test_start_closes_orphaned_runs(scheduler, conn, job_id):
    """AgentSchedulerService.start() wires the cleanup in."""
    runs_repo = ScheduledJobRunsRepository(conn)
    runs_repo.create(job_id)

    # The scheduler closes the connection it opened — that would drop the :memory:
    # DB before we can assert, so hand it a proxy whose close() is a no-op.
    class _KeepAlive:
        def __init__(self, real):
            self._real = real

        def __getattr__(self, name):
            return getattr(self._real, name)

        def close(self):
            pass

    scheduler._open_conn = Mock(return_value=_KeepAlive(conn))
    scheduler._scheduler = MagicMock()
    scheduler._reload_jobs = Mock()

    with patch.object(scheduler, "_catchup_missed_jobs"):
        scheduler.start()

    assert runs_repo.get_for_job(job_id)[0].status == "failed"


# ------------------------------------------------------------------
# Daily wealth snapshot job
# ------------------------------------------------------------------

def _snapshot(is_manual: bool = False, is_edited: bool = False) -> WealthSnapshot:
    from datetime import datetime

    return WealthSnapshot(
        id=1,
        date=date.today().isoformat(),
        total_eur=2_000_000.0,
        breakdown={"Aktie": 2_000_000.0},
        coverage_pct=100.0,
        is_manual=is_manual,
        is_edited=is_edited,
        created_at=datetime.now(),
    )


async def _run_snapshot_job(scheduler, existing):
    """Run _run_wealth_snapshot_job with all collaborators mocked.

    Returns the mocked WealthSnapshotAgent instance and the collected log lines.
    """
    wealth_repo = MagicMock()
    wealth_repo.get_by_date.return_value = existing

    snapshot_agent = MagicMock()
    snapshot_agent.take_snapshot.return_value = _snapshot()

    logs: list = []
    job = ScheduledJob(
        id=14,
        agent_name="wealth_snapshot",
        skill_name="",
        skill_prompt="",
        frequency="daily",
        run_hour=20,
        run_minute=0,
    )

    with patch("core.scheduler.build_encryption_service"), \
         patch("core.scheduler.PositionsRepository"), \
         patch("core.storage.market_data.MarketDataRepository"), \
         patch("core.storage.wealth_snapshots.WealthSnapshotRepository", return_value=wealth_repo), \
         patch("agents.market_data_fetcher.MarketDataFetcher"), \
         patch("agents.market_data_agent.MarketDataAgent"), \
         patch("agents.wealth_snapshot_agent.WealthSnapshotAgent", return_value=snapshot_agent):
        await scheduler._run_wealth_snapshot_job(job, MagicMock(), logs.append)

    return snapshot_agent, logs


@pytest.mark.asyncio
async def test_snapshot_job_creates_snapshot_when_none_exists(scheduler):
    agent, logs = await _run_snapshot_job(scheduler, existing=None)

    agent.take_snapshot.assert_called_once_with(is_manual=False, overwrite=False)
    assert "aktualisiert" not in logs[0]


@pytest.mark.asyncio
async def test_snapshot_job_refreshes_existing_automatic_snapshot(scheduler):
    """MarketDataAgent already snapshotted after the 18:00 fetch — refresh, don't fail."""
    agent, logs = await _run_snapshot_job(scheduler, existing=_snapshot())

    agent.take_snapshot.assert_called_once_with(is_manual=False, overwrite=True)
    assert "aktualisiert" in logs[0]


@pytest.mark.asyncio
async def test_snapshot_job_overwrites_intraday_manual_snapshot(scheduler):
    """An intraday 'Snapshot jetzt' must not stay the day's record — 20:00 wins."""
    agent, logs = await _run_snapshot_job(scheduler, existing=_snapshot(is_manual=True))

    agent.take_snapshot.assert_called_once_with(is_manual=False, overwrite=True)
    assert "aktualisiert" in logs[0]


@pytest.mark.asyncio
async def test_snapshot_job_never_overwrites_hand_entered_total(scheduler):
    """A total typed in by hand cannot be recomputed — it must survive."""
    agent, logs = await _run_snapshot_job(
        scheduler, existing=_snapshot(is_manual=True, is_edited=True)
    )

    agent.take_snapshot.assert_not_called()
    assert "von Hand" in logs[0]
