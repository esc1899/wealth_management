"""Tests for AgentSchedulerService catchup logic."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, AsyncMock, patch

from core.scheduler import AgentSchedulerService
from core.storage.models import ScheduledJob


@pytest.fixture
def scheduler():
    """Create a scheduler instance with mocked DB path and keys."""
    return AgentSchedulerService(
        db_path=":memory:",
        encryption_key="test-key",
        anthropic_api_key="test-api",
        default_claude_model="claude-haiku-4-5-20251001",
    )


@pytest.fixture
def mock_repos(scheduler):
    """Mock DB connection and repos for scheduler."""
    mock_conn = MagicMock()
    scheduler._open_conn = Mock(return_value=mock_conn)

    mock_jobs_repo = MagicMock()
    scheduler._ScheduledJobsRepository = patch("core.scheduler.ScheduledJobsRepository")

    return {
        "conn": mock_conn,
        "jobs_repo_cls": scheduler._ScheduledJobsRepository,
    }


# ------------------------------------------------------------------
# Test catchup logic: grace period conditions
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_catchup_runs_overdue_monthly_job():
    """Monthly job created 10 days ago (last_run=NULL) must be caught up.

    Grace period is 7 days, so time_since=10d > 7d → should run.
    """
    scheduler = AgentSchedulerService(
        db_path=":memory:",
        encryption_key="test-key",
        anthropic_api_key="test-api",
        default_claude_model="claude-haiku-4-5-20251001",
    )

    mock_conn = MagicMock()
    scheduler._open_conn = Mock(return_value=mock_conn)

    mock_jobs_repo = Mock()
    job = ScheduledJob(
        id=1,
        agent_name="news",
        skill_name="",
        skill_prompt="",
        frequency="monthly",
        run_hour=8,
        run_minute=0,
        enabled=True,
        last_run=None,
        created_at=datetime.now() - timedelta(days=10),
    )
    mock_jobs_repo.get_enabled.return_value = [job]

    # Mock _execute_job to track calls
    execute_job_calls = []
    async def mock_execute_job(job_id):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs()

    assert len(execute_job_calls) == 1
    assert execute_job_calls[0] == 1


@pytest.mark.asyncio
async def test_catchup_skips_fresh_monthly_job():
    """Job created 2 hours ago (last_run=NULL) must NOT be caught up.

    Grace period is 7 days, so time_since=2h <= 7d → should NOT run.
    """
    scheduler = AgentSchedulerService(
        db_path=":memory:",
        encryption_key="test-key",
        anthropic_api_key="test-api",
        default_claude_model="claude-haiku-4-5-20251001",
    )

    mock_conn = MagicMock()
    scheduler._open_conn = Mock(return_value=mock_conn)

    mock_jobs_repo = Mock()
    job = ScheduledJob(
        id=2,
        agent_name="news",
        skill_name="",
        skill_prompt="",
        frequency="monthly",
        run_hour=8,
        run_minute=0,
        enabled=True,
        last_run=None,
        created_at=datetime.now() - timedelta(hours=2),
    )
    mock_jobs_repo.get_enabled.return_value = [job]

    execute_job_calls = []
    async def mock_execute_job(job_id):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs()

    assert len(execute_job_calls) == 0


@pytest.mark.asyncio
async def test_catchup_skips_daily_jobs():
    """Daily jobs have no grace period — never caught up."""
    scheduler = AgentSchedulerService(
        db_path=":memory:",
        encryption_key="test-key",
        anthropic_api_key="test-api",
        default_claude_model="claude-haiku-4-5-20251001",
    )

    mock_conn = MagicMock()
    scheduler._open_conn = Mock(return_value=mock_conn)

    mock_jobs_repo = Mock()
    job = ScheduledJob(
        id=3,
        agent_name="news",
        skill_name="",
        skill_prompt="",
        frequency="daily",
        run_hour=8,
        run_minute=0,
        enabled=True,
        last_run=None,
        created_at=datetime.now() - timedelta(days=5),
    )
    mock_jobs_repo.get_enabled.return_value = [job]

    execute_job_calls = []
    async def mock_execute_job(job_id):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs()

    assert len(execute_job_calls) == 0


@pytest.mark.asyncio
async def test_catchup_runs_overdue_weekly_job():
    """Weekly job not run for 4 days (grace period = 3 days) must be caught up."""
    scheduler = AgentSchedulerService(
        db_path=":memory:",
        encryption_key="test-key",
        anthropic_api_key="test-api",
        default_claude_model="claude-haiku-4-5-20251001",
    )

    mock_conn = MagicMock()
    scheduler._open_conn = Mock(return_value=mock_conn)

    mock_jobs_repo = Mock()
    job = ScheduledJob(
        id=4,
        agent_name="consensus_gap",
        skill_name="",
        skill_prompt="",
        frequency="weekly",
        run_hour=8,
        run_minute=0,
        enabled=True,
        last_run=datetime.now() - timedelta(days=4),
        created_at=datetime.now() - timedelta(days=30),
    )
    mock_jobs_repo.get_enabled.return_value = [job]

    execute_job_calls = []
    async def mock_execute_job(job_id):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs()

    assert len(execute_job_calls) == 1
    assert execute_job_calls[0] == 4


@pytest.mark.asyncio
async def test_catchup_skips_recent_weekly_job():
    """Weekly job run 2 days ago (grace period = 3 days) must NOT be caught up."""
    scheduler = AgentSchedulerService(
        db_path=":memory:",
        encryption_key="test-key",
        anthropic_api_key="test-api",
        default_claude_model="claude-haiku-4-5-20251001",
    )

    mock_conn = MagicMock()
    scheduler._open_conn = Mock(return_value=mock_conn)

    mock_jobs_repo = Mock()
    job = ScheduledJob(
        id=5,
        agent_name="consensus_gap",
        skill_name="",
        skill_prompt="",
        frequency="weekly",
        run_hour=8,
        run_minute=0,
        enabled=True,
        last_run=datetime.now() - timedelta(days=2),
        created_at=datetime.now() - timedelta(days=30),
    )
    mock_jobs_repo.get_enabled.return_value = [job]

    execute_job_calls = []
    async def mock_execute_job(job_id):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs()

    assert len(execute_job_calls) == 0


@pytest.mark.asyncio
async def test_catchup_handles_no_reference_time():
    """Job with both last_run=NULL and created_at=NULL should be skipped."""
    scheduler = AgentSchedulerService(
        db_path=":memory:",
        encryption_key="test-key",
        anthropic_api_key="test-api",
        default_claude_model="claude-haiku-4-5-20251001",
    )

    mock_conn = MagicMock()
    scheduler._open_conn = Mock(return_value=mock_conn)

    mock_jobs_repo = Mock()
    job = ScheduledJob(
        id=6,
        agent_name="news",
        skill_name="",
        skill_prompt="",
        frequency="monthly",
        run_hour=8,
        run_minute=0,
        enabled=True,
        last_run=None,
        created_at=None,  # Edge case: no reference time
    )
    mock_jobs_repo.get_enabled.return_value = [job]

    execute_job_calls = []
    async def mock_execute_job(job_id):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs()

    assert len(execute_job_calls) == 0
