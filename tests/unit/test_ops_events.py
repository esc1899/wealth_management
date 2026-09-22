"""Die Hausbuchhaltung: Jeder LLM-Aufruf landet im Run-Log von ops-core.

Vier Projekte auf diesem Rechner teilen sich drei Anbieter; seit dem
2026-09-22 buchen sie in denselben Kanal, und der Home-Ops-Agent summiert
daraus den laufenden Monat je Anbieter. Hier wird geprüft, was dieses
Projekt dazu beiträgt -- und vor allem, dass es einen Aufruf nie kaputt
macht.
"""

import json
import os
import sqlite3
from pathlib import Path

import pytest

from core import ops_events
from core.storage.app_config import AppConfigRepository
from core.storage.usage import UsageRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE llm_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent TEXT, model TEXT, skill TEXT, source TEXT,
            input_tokens INTEGER, output_tokens INTEGER, duration_ms INTEGER,
            position_count INTEGER, cache_read_tokens INTEGER,
            cache_write_tokens INTEGER, web_search_requests INTEGER,
            generation_id TEXT, actual_cost_usd REAL, created_at TEXT
        );
        CREATE TABLE app_config (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    return c


@pytest.fixture
def runs(tmp_path, monkeypatch):
    """Ein eigenes ops-core-Zuhause je Test."""
    home = tmp_path / "ops-core"
    home.mkdir()
    monkeypatch.setenv("OPS_CORE_HOME", str(home))
    monkeypatch.delenv("OPS_RUN_ID", raising=False)
    monkeypatch.delenv("OPS_JOB", raising=False)
    return home / "runs"


def _lines(runs: Path) -> list[dict]:
    out = []
    for f in sorted(runs.glob("*.ndjson")):
        out += [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line]
    return out


class TestBooking:
    def test_a_claude_call_is_booked_with_its_list_price(self, conn, runs):
        """Mit dem datumslosen Alias -- die Registry führt Haiku datiert, und
        beides ist dasselbe Modell (wie in core.llm.router)."""
        UsageRepository(conn).record(
            "news_digest", "claude-haiku-4-5", 1000, 200, skill="News",
            source="scheduled", duration_ms=4200)
        (event,) = _lines(runs)
        assert event["project"] == "wealth_management" and event["kind"] == "metric"
        assert event["job"] == "scheduler" and len(event["run_id"]) == 26
        p = event["payload"]
        assert p["metric"] == "llm_call" and p["provider"] == "claude"
        assert p["purpose"] == "news_digest" and p["cost_source"] == "liste"
        assert p["tokens_in"] == 1000 and p["tokens_out"] == 200
        # 1000 * 1.00/1e6 + 200 * 5.00/1e6
        assert p["cost_usd"] == pytest.approx(0.002)
        assert p["duration_ms"] == 4200

    def test_a_local_call_costs_nothing_and_says_so(self, conn, runs):
        UsageRepository(conn).record("portfolio_chat", "qwen3.5:9b", 900, 120)
        (event,) = _lines(runs)
        assert event["payload"]["provider"] == "ollama"
        assert event["payload"]["cost_usd"] == 0
        assert event["job"] == "interaktiv"

    def test_an_openrouter_call_carries_its_generation_id(self, conn, runs):
        UsageRepository(conn).record(
            "research", "deepseek/deepseek-chat", 10_000, 2_000,
            generation_id="gen-42")
        (event,) = _lines(runs)
        assert event["payload"]["provider"] == "openrouter"
        assert event["payload"]["generation_id"] == "gen-42"
        assert event["payload"]["cost_usd"] > 0

    def test_inside_an_ops_run_the_call_joins_that_run(self, conn, runs, monkeypatch):
        monkeypatch.setenv("OPS_RUN_ID", "01ABCDEFGHJKMNPQRSTVWXYZ00")
        monkeypatch.setenv("OPS_JOB", "digest")
        UsageRepository(conn).record("news_digest", "claude-haiku-4-5", 10, 10)
        (event,) = _lines(runs)
        assert event["run_id"] == "01ABCDEFGHJKMNPQRSTVWXYZ00" and event["job"] == "digest"

    def test_without_ops_core_nothing_is_booked_and_nothing_created(
            self, conn, tmp_path, monkeypatch):
        """Ein frischer Checkout, CI, der Dev-Container: kein ops-core, kein Log."""
        monkeypatch.setenv("OPS_CORE_HOME", str(tmp_path / "gibt-es-nicht"))
        UsageRepository(conn).record("news_digest", "claude-haiku-4-5", 10, 10)
        assert not (tmp_path / "gibt-es-nicht").exists()
        assert conn.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0] == 1

    def test_a_broken_log_never_breaks_the_call(self, conn, tmp_path, monkeypatch, capsys):
        """Die harte Regel von ops-core: Das Log darf nie ein Projekt umbringen."""
        home = tmp_path / "ops-core"
        home.mkdir()
        (home / "runs").write_text("das ist eine Datei, kein Verzeichnis")
        monkeypatch.setenv("OPS_CORE_HOME", str(home))
        UsageRepository(conn).record("news_digest", "claude-haiku-4-5", 10, 10)
        assert conn.execute("SELECT COUNT(*) FROM llm_usage").fetchone()[0] == 1
        assert "not booked" in capsys.readouterr().err

    def test_the_dated_id_prices_the_same_as_its_alias(self, conn, runs):
        repo = UsageRepository(conn)
        repo.record("news_digest", "claude-haiku-4-5-20251001", 1000, 200)
        repo.record("news_digest", "claude-haiku-4-5", 1000, 200)
        datiert, alias = [e["payload"]["cost_usd"] for e in _lines(runs)]
        assert datiert == alias == pytest.approx(0.002)

    def test_an_unknown_model_is_booked_at_zero_like_the_statistics_show_it(
            self, conn, runs):
        UsageRepository(conn).record("research", "brandneues-modell", 10, 10)
        (event,) = _lines(runs)
        assert event["payload"]["cost_usd"] == 0
        assert event["payload"]["provider"] == "openrouter"   # aus der Modell-ID


class TestCostCorrection:
    def _record(self, conn, runs, cost_in_registry=True):
        repo = UsageRepository(conn)
        repo.record("research", "deepseek/deepseek-chat", 1_000_000, 0,
                    generation_id="gen-7")
        booked = _lines(runs)[0]["payload"]["cost_usd"]
        row_id = conn.execute("SELECT id FROM llm_usage").fetchone()[0]
        return repo, row_id, booked

    def test_only_the_difference_is_booked(self, conn, runs):
        repo, row_id, booked = self._record(conn, runs)
        repo.update_actual_cost(row_id, booked - 0.05)
        events = _lines(runs)
        assert [e["payload"]["metric"] for e in events] == ["llm_call", "llm_call_cost"]
        korrektur = events[1]["payload"]
        assert korrektur["cost_usd"] == pytest.approx(-0.05)
        assert korrektur["cost_source"] == "gemessen"
        assert korrektur["generation_id"] == "gen-7"
        assert korrektur["provider"] == "openrouter" and korrektur["purpose"] == "research"
        # Zusammen ergibt es den abgerechneten Betrag -- der Aufruf selbst
        # wurde nur einmal gezählt.
        assert sum(e["payload"]["cost_usd"] for e in events) == pytest.approx(booked - 0.05)

    def test_a_second_sync_of_the_same_row_books_nothing(self, conn, runs):
        repo, row_id, booked = self._record(conn, runs)
        repo.update_actual_cost(row_id, booked - 0.05)
        repo.update_actual_cost(row_id, booked - 0.05)
        assert len(_lines(runs)) == 2
        assert conn.execute("SELECT actual_cost_usd FROM llm_usage").fetchone()[0] \
            == pytest.approx(booked - 0.05)

    def test_a_matching_amount_needs_no_correction(self, conn, runs):
        repo, row_id, booked = self._record(conn, runs)
        repo.update_actual_cost(row_id, booked)
        assert len(_lines(runs)) == 1

    def test_the_stored_cost_is_written_even_when_the_log_is_gone(
            self, conn, tmp_path, monkeypatch):
        repo = UsageRepository(conn)
        repo.record("research", "deepseek/deepseek-chat", 10, 10, generation_id="g")
        row_id = conn.execute("SELECT id FROM llm_usage").fetchone()[0]
        monkeypatch.setenv("OPS_CORE_HOME", str(tmp_path / "weg"))
        repo.update_actual_cost(row_id, 1.23)
        assert conn.execute("SELECT actual_cost_usd FROM llm_usage").fetchone()[0] == 1.23


# ---------------------------------------------------------------------------
# Haus-Standard: ein Modell namens "home" folgt ~/.ops-core/modelle.toml
# ---------------------------------------------------------------------------

from core import house_models
from core.llm.router import resolve_house_model

HOUSE_TOML = '''
[claude]
modell = "claude-sonnet-5"
budget_usd = 20

[ollama]
modell = "qwen3.5:9b"

[openrouter]
modell = "deepseek/deepseek-chat"
'''


@pytest.fixture
def house(tmp_path, monkeypatch):
    """Die Datei im selben ops-core-Zuhause wie `runs` -- beide Fixtures
    zusammen ergeben einen Rechner mit Log und Haus-Standard."""
    home = tmp_path / "ops-core"
    home.mkdir(exist_ok=True)
    (home / "modelle.toml").write_text(HOUSE_TOML, encoding="utf-8")
    monkeypatch.setenv("OPS_CORE_HOME", str(home))
    return home / "modelle.toml"


class TestHouseModels:
    def test_home_resolves_per_provider(self, house):
        assert resolve_house_model("home", local=True) == "qwen3.5:9b"
        assert resolve_house_model("home") == "claude-sonnet-5"
        # Kein Anthropic-Schlüssel, aber ein OpenAI-kompatibler Endpunkt:
        # dann ist der Haus-Standard der von OpenRouter.
        assert resolve_house_model("home", has_anthropic=False,
                                   has_openai_base=True) == "deepseek/deepseek-chat"

    def test_anything_else_stays_as_it_is(self, house):
        assert resolve_house_model("claude-opus-5") == "claude-opus-5"
        assert resolve_house_model("") == ""

    def test_it_is_read_per_call_so_a_change_needs_no_restart(self, house):
        assert resolve_house_model("home", local=True) == "qwen3.5:9b"
        house.write_text(HOUSE_TOML.replace("qwen3.5:9b", "gemma3:4b"), encoding="utf-8")
        assert resolve_house_model("home", local=True) == "gemma3:4b"

    def test_without_the_file_the_fallback_stands(self, tmp_path, monkeypatch):
        """Eine fehlende Datei darf die App nie anhalten."""
        monkeypatch.setenv("OPS_CORE_HOME", str(tmp_path / "leer"))
        assert resolve_house_model("home", local=True, fallback="llama3.2") == "llama3.2"
        assert house_models.load() == {}

    def test_a_broken_file_is_a_warning_not_a_crash(self, tmp_path, monkeypatch, caplog):
        home = tmp_path / "ops-core"
        home.mkdir()
        (home / "modelle.toml").write_text("[claude\nmodell = ", encoding="utf-8")
        monkeypatch.setenv("OPS_CORE_HOME", str(home))
        assert house_models.load() == {}
        assert resolve_house_model("home", fallback="claude-haiku-4-5") == "claude-haiku-4-5"

    def test_an_entry_without_a_model_is_ignored(self, tmp_path, monkeypatch):
        home = tmp_path / "ops-core"
        home.mkdir()
        (home / "modelle.toml").write_text(
            '[claude]\nbudget_usd = 5\n[ollama]\nmodell = "qwen3.5:9b"\n', encoding="utf-8")
        monkeypatch.setenv("OPS_CORE_HOME", str(home))
        geladen = house_models.load()
        assert "claude" not in geladen and geladen["ollama"]["modell"] == "qwen3.5:9b"

    def test_the_resolved_model_is_what_gets_booked(self, conn, runs, house, monkeypatch):
        """Gebucht wird das echte Modell, nie "home" -- sonst stünde in der
        Hausbuchhaltung ein Wort statt eines Modells."""
        import state_llm

        monkeypatch.setattr(state_llm, "get_usage_repo", lambda: UsageRepository(conn))
        provider = state_llm._make_ollama_provider("home", "portfolio_chat")
        assert provider.model == "qwen3.5:9b"
        provider.on_usage(900, 120)
        (event,) = _lines(runs)
        assert event["payload"]["model"] == "qwen3.5:9b"
        assert event["payload"]["provider"] == "ollama"
