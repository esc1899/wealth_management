"""Tests for AgentSchedulerService catchup logic and batch API guard."""

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


# ------------------------------------------------------------------
# _can_use_batch_api
# ------------------------------------------------------------------


class TestCanUseBatchApi:
    def _make_scheduler(self, anthropic_key="sk-ant-real", llm_base_url="", openai_base_url=""):
        return AgentSchedulerService(
            db_path=":memory:",
            encryption_key="key",
            anthropic_api_key=anthropic_key,
            default_claude_model="claude-haiku-4-5-20251001",
            llm_base_url=llm_base_url,
            openai_api_key="or-key" if openai_base_url else "",
            openai_base_url=openai_base_url,
        )

    def test_direct_anthropic_claude_model(self, monkeypatch):
        monkeypatch.setattr("config.config.USE_BATCH_API", True)
        s = self._make_scheduler()
        assert s._can_use_batch_api("claude-haiku-4-5-20251001") is True

    def test_openrouter_claude_model_format_rejected(self, monkeypatch):
        """OpenRouter model names like 'anthropic/claude-*' must be rejected."""
        monkeypatch.setattr("config.config.USE_BATCH_API", True)
        s = self._make_scheduler()
        assert s._can_use_batch_api("anthropic/claude-sonnet-4-6") is False

    def test_deepseek_model_rejected(self, monkeypatch):
        monkeypatch.setattr("config.config.USE_BATCH_API", True)
        s = self._make_scheduler()
        assert s._can_use_batch_api("deepseek/deepseek-chat") is False

    def test_custom_llm_base_url_rejected(self, monkeypatch):
        """Custom LLM_BASE_URL (e.g. OpenRouter via Claude path) must disable batch."""
        monkeypatch.setattr("config.config.USE_BATCH_API", True)
        s = self._make_scheduler(llm_base_url="https://openrouter.ai/api/v1")
        assert s._can_use_batch_api("claude-haiku-4-5-20251001") is False

    def test_flag_disabled(self, monkeypatch):
        monkeypatch.setattr("config.config.USE_BATCH_API", False)
        s = self._make_scheduler()
        assert s._can_use_batch_api("claude-haiku-4-5-20251001") is False

    def test_no_anthropic_key(self, monkeypatch):
        monkeypatch.setattr("config.config.USE_BATCH_API", True)
        s = self._make_scheduler(anthropic_key="")
        assert s._can_use_batch_api("claude-haiku-4-5-20251001") is False

    def test_openai_base_url_set_but_direct_claude_still_allowed(self, monkeypatch):
        """OPENAI_BASE_URL for OpenRouter is independent of the Anthropic-direct path.
        A resolved claude-* model with empty LLM_BASE_URL CAN use batch."""
        monkeypatch.setattr("config.config.USE_BATCH_API", True)
        s = self._make_scheduler(openai_base_url="https://openrouter.ai/api/v1")
        assert s._can_use_batch_api("claude-haiku-4-5-20251001") is True


# ------------------------------------------------------------------
# Manual frequency: catchup + reload_jobs
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_catchup_skips_manual_jobs():
    """Manual jobs must never be caught up automatically."""
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
        id=10,
        agent_name="sector_rotation",
        skill_name="",
        skill_prompt="",
        frequency="manual",
        run_hour=0,
        run_minute=0,
        enabled=True,
        last_run=None,
        created_at=datetime.now() - timedelta(days=30),
    )
    mock_jobs_repo.get_enabled.return_value = [job]

    execute_job_calls = []

    async def mock_execute_job(job_id, source="scheduled"):
        execute_job_calls.append(job_id)

    scheduler._execute_job = mock_execute_job

    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        await scheduler._catchup_missed_jobs()

    assert len(execute_job_calls) == 0, "manual jobs must never be auto-caught-up"


def test_reload_jobs_skips_manual_frequency():
    """Manual-frequency jobs must not be registered with APScheduler."""
    scheduler = AgentSchedulerService(
        db_path=":memory:",
        encryption_key="test-key",
        anthropic_api_key="test-api",
        default_claude_model="claude-haiku-4-5-20251001",
    )

    mock_conn = MagicMock()
    scheduler._open_conn = Mock(return_value=mock_conn)

    manual_job = ScheduledJob(
        id=11,
        agent_name="search_agent",
        skill_name="",
        skill_prompt="",
        frequency="manual",
        run_hour=0,
        run_minute=0,
        enabled=True,
    )
    daily_job = ScheduledJob(
        id=12,
        agent_name="news",
        skill_name="",
        skill_prompt="",
        frequency="daily",
        run_hour=8,
        run_minute=0,
        enabled=True,
    )

    mock_jobs_repo = Mock()
    mock_jobs_repo.get_enabled.return_value = [manual_job, daily_job]

    added_jobs = []
    scheduler._scheduler = MagicMock()
    scheduler._scheduler.get_jobs.return_value = []
    scheduler._scheduler.add_job.side_effect = lambda *a, **kw: added_jobs.append(kw.get("id", ""))

    with patch("core.scheduler.ScheduledJobsRepository", return_value=mock_jobs_repo):
        scheduler._reload_jobs()

    # Only the daily job should have been added
    assert len(added_jobs) == 1
    assert "agent_job_12" in added_jobs[0]
    # The manual job (id=11) must not appear
    assert not any("agent_job_11" in j for j in added_jobs)


# ------------------------------------------------------------------
# _process_batch_results: new agent routing
# ------------------------------------------------------------------


def _make_mock_batch_result(custom_id: str, text: str, tool_calls=None):
    """Build a mock batch result object with optional tool_use blocks."""
    block = MagicMock()
    block.type = "text"
    block.text = text

    content_blocks = [block]
    if tool_calls:
        for tc in tool_calls:
            tb = MagicMock()
            tb.type = "tool_use"
            tb.name = tc["name"]
            tb.input = tc["input"]
            content_blocks.append(tb)

    message = MagicMock()
    message.content = content_blocks

    result_inner = MagicMock()
    result_inner.type = "succeeded"
    result_inner.message = message

    result = MagicMock()
    result.custom_id = custom_id
    result.result = result_inner
    return result


def test_process_sr_result_saves_run_and_verdicts():
    """_process_sr_result must save a SectorRotationRun and verdicts."""
    scheduler = AgentSchedulerService(
        db_path=":memory:",
        encryption_key="key",
        anthropic_api_key="sk-ant",
        default_claude_model="claude-haiku-4-5-20251001",
    )

    mock_conn = MagicMock()
    result = _make_mock_batch_result(
        custom_id="sr_scan",
        text="## Sektor Rotation Bericht\nTech hat Zuflüsse...",
        tool_calls=[{
            "name": "submit_sector_verdict",
            "input": {"sector": "Technology", "verdict": "aligned", "momentum": "inflow", "summary": "Tech flows strong"},
        }],
    )

    mock_run = MagicMock()
    mock_run.id = 99
    mock_sr_repo = MagicMock()
    mock_sr_repo.save_run.return_value = mock_run

    with patch("core.storage.sector_rotation.SectorRotationRepository", return_value=mock_sr_repo):
        ok = scheduler._process_sr_result(result, "TestSkill", mock_conn)

    assert ok is True
    mock_sr_repo.save_run.assert_called_once_with(skill_name="TestSkill", result="## Sektor Rotation Bericht\nTech hat Zuflüsse...")
    mock_sr_repo.add_message.assert_called_once()
    mock_sr_repo.save_verdict.assert_called_once()
    call_kwargs = mock_sr_repo.save_verdict.call_args
    assert call_kwargs.kwargs["sector"] == "Technology"
    assert call_kwargs.kwargs["verdict"] == "aligned"
    assert call_kwargs.kwargs["momentum"] == "inflow"


def test_process_sr_result_wrong_custom_id():
    scheduler = AgentSchedulerService(
        db_path=":memory:", encryption_key="key",
        anthropic_api_key="sk", default_claude_model="claude-haiku-4-5-20251001",
    )
    result = _make_mock_batch_result("cg_123", "some text")
    ok = scheduler._process_sr_result(result, "", MagicMock())
    assert ok is False


def test_process_structural_scan_result_saves_run():
    """_process_structural_scan_result must save a run with the report text."""
    scheduler = AgentSchedulerService(
        db_path=":memory:", encryption_key="key",
        anthropic_api_key="sk", default_claude_model="claude-haiku-4-5-20251001",
    )
    result = _make_mock_batch_result("struct_scan", "Structural scan report...")
    mock_run = MagicMock()
    mock_run.id = 42
    mock_scans_repo = MagicMock()
    mock_scans_repo.save_run.return_value = mock_run

    with patch("core.storage.structural_scans.StructuralScansRepository", return_value=mock_scans_repo):
        ok = scheduler._process_structural_scan_result(result, "MyScan", MagicMock())

    assert ok is True
    mock_scans_repo.save_run.assert_called_once_with(skill_name="MyScan", result="Structural scan report...")
    mock_scans_repo.add_message.assert_called_once()


def test_process_search_result_saves_session():
    """_process_search_result must create a search session with the report."""
    scheduler = AgentSchedulerService(
        db_path=":memory:", encryption_key="key",
        anthropic_api_key="sk", default_claude_model="claude-haiku-4-5-20251001",
    )
    result = _make_mock_batch_result("search_run", "Investment screening results...")
    mock_session = MagicMock()
    mock_session.id = 7
    mock_search_repo = MagicMock()
    mock_search_repo.create_session.return_value = mock_session

    with patch("core.storage.search.SearchRepository", return_value=mock_search_repo):
        ok = scheduler._process_search_result(result, "MySearch", MagicMock())

    assert ok is True
    mock_search_repo.create_session.assert_called_once()
    call_kwargs = mock_search_repo.create_session.call_args.kwargs
    assert call_kwargs["skill_name"] == "MySearch"
    mock_search_repo.add_message.assert_called_once()


def test_process_batch_results_routes_new_agents():
    """_process_batch_results dispatches to correct _process_* for new agents."""
    scheduler = AgentSchedulerService(
        db_path=":memory:", encryption_key="key",
        anthropic_api_key="sk", default_claude_model="claude-haiku-4-5-20251001",
    )

    sr_result = _make_mock_batch_result("sr_scan", "SR report")
    struct_result = _make_mock_batch_result("struct_scan", "Struct report")
    search_result = _make_mock_batch_result("search_run", "Search report")

    scheduler._process_sr_result = Mock(return_value=True)
    scheduler._process_structural_scan_result = Mock(return_value=True)
    scheduler._process_search_result = Mock(return_value=True)

    conn = MagicMock()

    s, e = scheduler._process_batch_results("sector_rotation", "sk", [sr_result], conn)
    assert s == 1 and e == 0
    scheduler._process_sr_result.assert_called_once()

    s, e = scheduler._process_batch_results("structural_scan", "sk", [struct_result], conn)
    assert s == 1 and e == 0
    scheduler._process_structural_scan_result.assert_called_once()

    s, e = scheduler._process_batch_results("search_agent", "sk", [search_result], conn)
    assert s == 1 and e == 0
    scheduler._process_search_result.assert_called_once()
