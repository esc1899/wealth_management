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


@pytest.fixture
def eingeplant():
    """Wie ein eingeplanter Lauf: nur dort darf der Scheduler Batches schicken."""
    from core.scheduler import _BATCH_ERLAUBT
    token = _BATCH_ERLAUBT.set(True)
    yield
    _BATCH_ERLAUBT.reset(token)


@pytest.mark.usefixtures("eingeplant")
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


# ------------------------------------------------------------------
# 02.10.2026: Batch ist Standard fuer eingeplante Laeufe, nie fuer "Jetzt ausfuehren"
# ------------------------------------------------------------------


def test_jetzt_ausfuehren_laeuft_live(monkeypatch):
    monkeypatch.setattr("config.config.USE_BATCH_API", True)
    s = AgentSchedulerService(db_path=":memory:", encryption_key="k",
                              anthropic_api_key="sk-ant-real", default_claude_model="claude-haiku-4-5")
    assert s._can_use_batch_api("claude-sonnet-5-5") is False  # Kontext nicht gesetzt


@pytest.mark.asyncio
@pytest.mark.parametrize("source, erwartet", [("scheduled", True), ("manual", False)])
async def test_quelle_des_laufs_entscheidet(monkeypatch, source, erwartet):
    from core.scheduler import _BATCH_ERLAUBT
    monkeypatch.setattr("config.config.USE_BATCH_API", True)
    s = AgentSchedulerService(db_path=":memory:", encryption_key="k",
                              anthropic_api_key="sk-ant-real", default_claude_model="claude-haiku-4-5")
    gesehen = {}

    async def dispatch(job, conn, log_fn):
        gesehen["batch"] = s._can_use_batch_api("claude-sonnet-5-5")

    s._open_conn = Mock(return_value=MagicMock())
    s._dispatch_agent = dispatch
    with patch("core.scheduler.ScheduledJobsRepository") as jobs, \
         patch("core.scheduler.ScheduledJobRunsRepository"):
        jobs.return_value.get.return_value = MagicMock(enabled=True)
        await s._execute_job(1, source=source)
    assert gesehen["batch"] is erwartet
    assert _BATCH_ERLAUBT.get() is False  # setzt nichts ausserhalb des Laufs


def test_neuestes_wird_vor_der_batch_pruefung_aufgeloest():
    s = AgentSchedulerService(db_path=":memory:", encryption_key="k",
                              anthropic_api_key="sk-ant-real", default_claude_model="claude-haiku-4-5")
    with patch("core.house_models.resolve_newest", return_value="claude-sonnet-5-5"):
        assert s._resolve_model("storychecker", "neuestes:sonnet", MagicMock()) == "claude-sonnet-5-5"


@pytest.mark.asyncio
async def test_batch_anfragen_denken_wie_live():
    from core.llm.claude import ClaudeProvider
    llm = ClaudeProvider(api_key="k", model="claude-sonnet-5-5")
    llm._client = MagicMock()
    llm._client.messages.batches.create = AsyncMock(return_value=MagicMock(id="b1"))
    req = ClaudeProvider.build_batch_request("sc_1", "claude-sonnet-5-5", "sys",
                                             [{"role": "user", "content": "x"}], [], 4096)
    await llm.submit_batch([req])
    gesendet = llm._client.messages.batches.create.call_args.kwargs["requests"][0]["params"]
    for k, v in llm._reasoning_kwargs().items():
        assert gesendet[k] == v


def test_schalter_im_maschinenraum_schaltet(monkeypatch, tmp_path):
    """Der Hebel ist modelle.toml ([claude] batch), nicht die .env."""
    from core import house_models
    from core.scheduler import _BATCH_ERLAUBT

    monkeypatch.setattr("config.config.USE_BATCH_API", False)
    monkeypatch.setenv("OPS_CORE_HOME", str(tmp_path))
    s = AgentSchedulerService(db_path=":memory:", encryption_key="k",
                              anthropic_api_key="sk-ant-real", default_claude_model="claude-haiku-4-5")
    token = _BATCH_ERLAUBT.set(True)
    try:
        assert s._can_use_batch_api("claude-sonnet-5-5") is False          # keine Datei: aus
        (tmp_path / "modelle.toml").write_text('[claude]\nmodell = "claude-sonnet-5-5"\nbatch = true\n')
        assert house_models.scheduled_batch() is True
        assert s._can_use_batch_api("claude-sonnet-5-5") is True
        (tmp_path / "modelle.toml").write_text('[claude]\nmodell = "claude-sonnet-5-5"\nbatch = false\n')
        assert s._can_use_batch_api("claude-sonnet-5-5") is False
    finally:
        _BATCH_ERLAUBT.reset(token)


# ------------------------------------------------------------------
# 02.10.2026: News-Digest und Devil's Advocate im Batch, Stand fuer die Kachel
# ------------------------------------------------------------------


def _scheduler_mit_db(tmp_path):
    from core.storage.base import get_connection, init_db, migrate_db
    pfad = str(tmp_path / "wm.db")
    conn = get_connection(pfad); init_db(conn); migrate_db(conn); conn.close()
    s = AgentSchedulerService(db_path=pfad, encryption_key="k" * 32,
                              anthropic_api_key="sk-ant-real", default_claude_model="claude-haiku-4-5")
    return s


def _ergebnis(custom_id, blocks):
    msg = MagicMock(content=blocks, model="claude-sonnet-5-5")
    msg.usage = MagicMock(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                          cache_creation_input_tokens=0, server_tool_use=None)
    return MagicMock(custom_id=custom_id, result=MagicMock(type="succeeded", message=msg))


def test_wartet_nennt_die_offenen_batches(tmp_path):
    from core.storage.batch_queue import BatchQueueRepository
    s = _scheduler_mit_db(tmp_path)
    assert s.wartet() == {"anzahl": 0, "seit": None, "was": []}
    conn = s._open_conn()
    BatchQueueRepository(conn).create("b1", "storychecker", None, "de", 3)
    BatchQueueRepository(conn).create("b2", "news_digest", "Standard", "de", 1, kontext='{"tickers": ["SAP"]}')
    BatchQueueRepository(conn).mark_done("b0-nie", 0, 0)
    conn.close()
    w = s.wartet()
    assert w["anzahl"] == 2 and w["was"] == ["Storychecker", "News-Digest"]
    assert w["seit"][19:] in ("+01:00", "+02:00", "+00:00") or "+" in w["seit"]


def test_news_digest_aus_dem_batch_mit_den_tickern_des_laufs(tmp_path):
    from core.storage.news import NewsRepository
    s = _scheduler_mit_db(tmp_path)
    conn = s._open_conn()
    text = MagicMock(type="text", text="## Digest")
    ok, fehler = s._process_batch_results("news_digest", "Standard", [_ergebnis("news_digest", [text])],
                                          conn, '{"tickers": ["SAP", "KOG.OL"]}')
    assert (ok, fehler) == (1, 0)
    [run] = NewsRepository(conn).list_runs()
    assert run.result == "## Digest" and run.tickers == "SAP, KOG.OL"


def test_devils_advocate_aus_dem_batch_braucht_ein_urteil(tmp_path):
    from core.storage.analyses import PositionAnalysesRepository
    s = _scheduler_mit_db(tmp_path)
    s._lookup_position = lambda pid, conn: None
    conn = s._open_conn()
    urteil = MagicMock(type="tool_use", input={"verdict": "fragil", "summary": "kurz", "analysis": "lang"})
    urteil.name = "submit_da_verdict"
    nur_text = MagicMock(type="text", text="Analyse ohne Urteil")
    ok, fehler = s._process_batch_results("devils_advocate", "Standard",
                                          [_ergebnis("da_7", [urteil]), _ergebnis("da_8", [nur_text])], conn)
    assert (ok, fehler) == (1, 1)
    assert PositionAnalysesRepository(conn).get_latest_bulk([7], "devils_advocate")[7].verdict == "fragil"
