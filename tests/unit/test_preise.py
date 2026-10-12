"""Preise der Sprachmodelle aus Quellen, nicht aus Eingaben (core/preise.py, 12.10.2026).

Claude aus dem Katalog des Hauses, OpenRouter aus der Liste, die der Job kosten holt,
lokal kostenlos -- und ein Modell ohne Preis ist "offen", nie 0.
"""

import sqlite3
from datetime import date
from unittest.mock import patch

import pytest

from core import preise
from core.storage.app_config import AppConfigRepository
from core.storage.usage import compute_cost

_CATALOG = '''
[claude]
aktuell = ["claude-opus-5-5", "claude-haiku-4-5-20251001"]

[claude.preise."claude-opus-5-5"]
eingabe = 4
ausgabe = 20
cache_lesen = 0.2
cache_schreiben = 5

[claude.preise."claude-haiku-4-5"]
eingabe = 1.5
ausgabe = 6

[claude.preise."claude-opus-4-1"]
eingabe = 15
ausgabe = 75
'''


@pytest.fixture
def app_cfg():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE app_config (key TEXT PRIMARY KEY, value TEXT)")
    return AppConfigRepository(c)


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    path = tmp_path / "katalog.toml"
    path.write_text(_CATALOG, encoding="utf-8")
    monkeypatch.setenv("OPS_CORE_KATALOG", str(path))
    return path


class TestAnbieter:
    @pytest.mark.parametrize("modell,erwartet", [
        ("claude-sonnet-5", "claude"),
        ("deepseek/deepseek-v4-pro", "openrouter"),
        ("mistralai/mistral-medium-3-5", "openrouter"),
        ("qwen3.5:9b", "ollama"),
        ("llama3.2", "ollama"),
        ("deepseek-chat", "deepseek"),     # alte Aufrufe an DeepSeek direkt
    ])
    def test_aus_der_id(self, modell, erwartet):
        assert preise.anbieter(modell) == erwartet


class TestPreis:
    def test_claude_aus_dem_katalog_auch_abgeloeste(self, app_cfg, catalog):
        liste = preise.preisliste(app_cfg)
        assert preise.preis("claude-opus-5-5", liste)["input"] == 4
        assert preise.preis("claude-opus-4-1", liste)["output"] == 75   # alte Aufrufe behalten ihn
        assert liste["claude-opus-5-5"]["quelle"] == "katalog"

    def test_datierte_id_und_alias_sind_ein_modell(self, app_cfg, catalog):
        liste = preise.preisliste(app_cfg)
        assert preise.preis("claude-haiku-4-5-20251001", liste)["input"] == 1.5

    def test_lokal_kostet_nichts(self, app_cfg, catalog):
        assert preise.preis("qwen3.5:9b", preise.preisliste(app_cfg)) == {"input": 0.0, "output": 0.0}

    def test_ohne_preis_offen_nie_null(self, app_cfg, catalog):
        liste = preise.preisliste(app_cfg)
        assert preise.preis("acme/neu", liste) is None
        assert preise.preis("claude-unbekannt-9", liste) is None
        assert preise.preis("deepseek-chat", liste) is None

    def test_ohne_katalog_ist_claude_offen(self, app_cfg, tmp_path, monkeypatch):
        monkeypatch.setenv("OPS_CORE_KATALOG", str(tmp_path / "fehlt.toml"))
        assert preise.preis("claude-opus-5-5", preise.preisliste(app_cfg)) is None

    def test_openrouter_aus_der_abgelegten_liste(self, app_cfg, catalog):
        preise.openrouter_ablegen(app_cfg, {"acme/neu": {"input": 0.5, "output": 1.0}})
        liste = preise.preisliste(app_cfg)
        assert preise.preis("acme/neu", liste)["output"] == 1.0
        assert liste["acme/neu"]["quelle"] == "openrouter"

    def test_cache_preise_aus_dem_katalog(self, app_cfg, catalog):
        p = preise.preis("claude-opus-5-5", preise.preisliste(app_cfg))
        cost = compute_cost(0, 0, "claude-opus-5-5", {"claude-opus-5-5": p},
                            cache_read_tokens=1_000_000, cache_write_tokens=1_000_000)
        assert cost == pytest.approx(0.2 + 5.0)

    def test_unlesbarer_katalog_heisst_keiner(self, tmp_path):
        from core import house_models

        bad = tmp_path / "k.toml"
        bad.write_text("[broken", encoding="utf-8")
        assert house_models.load_catalog(path=bad) == {}


class TestOpenrouterAbruf:
    def test_einmal_am_tag(self, app_cfg):
        heute = date(2026, 10, 12)
        assert preise.openrouter_faellig(app_cfg, heute)
        preise.openrouter_ablegen(app_cfg, {}, heute)
        assert not preise.openrouter_faellig(app_cfg, heute)
        assert preise.openrouter_faellig(app_cfg, date(2026, 10, 13))

    def test_ein_alter_preis_bleibt_ein_neuer_ersetzt_ihn(self, app_cfg):
        preise.openrouter_ablegen(app_cfg, {"a/x": {"input": 1, "output": 2},
                                            "a/y": {"input": 3, "output": 4}})
        preise.openrouter_ablegen(app_cfg, {"a/x": {"input": 9, "output": 9}})
        gespeichert = app_cfg.get_json(preise.OPENROUTER_SCHLUESSEL)
        assert gespeichert["a/x"]["input"] == 9 and gespeichert["a/y"]["input"] == 3

    def test_preise_je_token_werden_je_million(self):
        from core.llm.openrouter_costs import fetch_model_prices

        antwort = {"data": [
            {"id": "a/x", "pricing": {"prompt": "0.0000005", "completion": "0.0000015"}},
            {"id": "a/ungefragt", "pricing": {"prompt": "1", "completion": "1"}},
            {"id": "a/kaputt", "pricing": {}},
        ]}
        with patch("core.llm.openrouter_costs.requests.get") as get:
            get.return_value.json.return_value = antwort
            get.return_value.raise_for_status.return_value = None
            prices = fetch_model_prices("https://openrouter.test/api/v1", ["a/x", "a/kaputt"])
        assert prices == {"a/x": {"input": pytest.approx(0.5), "output": pytest.approx(1.5)}}

    def test_ein_fehler_gibt_nichts(self):
        from core.llm.openrouter_costs import fetch_model_prices

        with patch("core.llm.openrouter_costs.requests.get", side_effect=OSError("weg")):
            assert fetch_model_prices("https://openrouter.test/api/v1", ["a/x"]) == {}
