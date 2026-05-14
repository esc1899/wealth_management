"""Tests for AgentSchedulerService catchup logic."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, AsyncMock, patch, call

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
    async def mock_execute_job(job_id, source="scheduled"):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs()

    assert len(execute_job_calls) == 1
    assert execute_job_calls[0] == 1


@pytest.mark.asyncio
async def test_catchup_runs_new_job_immediately():
    """Job with last_run=NULL (never run) must be caught up immediately.

    New jobs are always caught up regardless of age.
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
    async def mock_execute_job(job_id, source="scheduled"):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs()

    assert len(execute_job_calls) == 1
    assert execute_job_calls[0] == 2


@pytest.mark.asyncio
async def test_catchup_skips_fresh_existing_job():
    """Existing job run 2 hours ago (last_run != NULL) must NOT be caught up.

    Grace period is 7 days, so time_since=2h < 7d → should NOT run.
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
        last_run=datetime.now() - timedelta(hours=2),  # Ran 2 hours ago
        created_at=datetime.now() - timedelta(days=30),
    )
    mock_jobs_repo.get_enabled.return_value = [job]

    execute_job_calls = []
    async def mock_execute_job(job_id, source="scheduled"):
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
    async def mock_execute_job(job_id, source="scheduled"):
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
    async def mock_execute_job(job_id, source="scheduled"):
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
    async def mock_execute_job(job_id, source="scheduled"):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs()

    assert len(execute_job_calls) == 0


# ------------------------------------------------------------------
# Regression: monthly job re-run bug
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_catchup_skips_monthly_job_already_ran_this_month():
    """Monthly job that already ran on its scheduled day must NOT run again mid-month.

    Regression: FA ran May 1st at 07:05, app restarts May 13th — must not re-run.
    Root cause: old logic checked `time_since > 7 days` which is always true for any
    monthly job that ran more than a week ago.
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
        id=7,
        agent_name="fundamental",
        skill_name="",
        skill_prompt="",
        frequency="monthly",
        run_day=1,
        run_hour=7,
        run_minute=0,
        enabled=True,
        last_run=datetime(2026, 5, 1, 7, 5),   # ran on scheduled day
        created_at=datetime(2026, 1, 1),
    )
    mock_jobs_repo.get_enabled.return_value = [job]

    execute_job_calls = []

    async def mock_execute_job(job_id, source="scheduled"):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    fake_now = datetime(2026, 5, 13, 10, 0)
    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs(now=fake_now)

    assert len(execute_job_calls) == 0, "monthly job already ran this period — must not run again"


@pytest.mark.asyncio
async def test_catchup_runs_monthly_job_that_missed_scheduled_day():
    """Monthly job not yet run this month (scheduled day already passed) must be caught up.

    Scenario: app was down on May 1st, restarts May 3rd — job must run.
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
        id=8,
        agent_name="fundamental",
        skill_name="",
        skill_prompt="",
        frequency="monthly",
        run_day=1,
        run_hour=7,
        run_minute=0,
        enabled=True,
        last_run=datetime(2026, 4, 1, 7, 5),   # ran in PREVIOUS month
        created_at=datetime(2026, 1, 1),
    )
    mock_jobs_repo.get_enabled.return_value = [job]

    execute_job_calls = []

    async def mock_execute_job(job_id, source="scheduled"):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    fake_now = datetime(2026, 5, 3, 10, 0)   # 2 days after scheduled May 1st fire
    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs(now=fake_now)

    assert len(execute_job_calls) == 1, "job missed May 1st fire — must be caught up"
    assert execute_job_calls[0] == 8


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
    async def mock_execute_job(job_id, source="scheduled"):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs()

    assert len(execute_job_calls) == 0
