"""Tests for AgentSchedulerService: batch API guard and batch result routing.

When a job is due: tests/unit/test_scheduler_faellig.py."""

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
