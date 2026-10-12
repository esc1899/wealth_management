"""
UI smoke tests for the Settings page: three tabs by meaning (12.10.2026) --
Pruefung, System, Preise. Prices are read-only (core/preise.py). Model discovery
(Claude/Ollama) falls back gracefully on network errors, so no mocking is required.
"""

from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from config import config
from state import get_app_config_repo

PAGES = Path(__file__).resolve().parents[2] / "pages"


class TestSettingsPage:
    def test_page_loads(self):
        at = AppTest.from_file(PAGES / "settings.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_one_save_button_for_all_models(self):
        at = AppTest.from_file(PAGES / "settings.py")
        at.run()
        keys = [b.key for b in at.button]
        assert "_save_models_btn" in keys, keys
        assert not any(k and k.startswith(("_price_", "_save_prices")) for k in keys)

    def test_configured_openrouter_model_is_selectable(self):
        with (
            patch.object(config, "OPENAI_BASE_URL", "https://openrouter.test/api/v1"),
            patch.object(config, "OPENAI_API_KEY", "test-openrouter-key"),
            patch.object(config, "OPENAI_MODELS", ["acme/new-router-model"]),
        ):
            at = AppTest.from_file(PAGES / "settings.py")
            at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"
        all_options = [opt for s in at.selectbox for opt in (s.options or [])]
        assert "acme/new-router-model" in all_options

    def test_prices_are_read_only_and_say_open(self):
        """Ein OpenRouter-Modell ohne abgelegten Preis steht als "offen" da, nie mit 0."""
        repo = get_app_config_repo()
        saved = repo.get_json("preise_openrouter")
        try:
            repo.delete("preise_openrouter")
            with (
                patch.object(config, "OPENAI_BASE_URL", "https://openrouter.test/api/v1"),
                patch.object(config, "OPENAI_API_KEY", "test-openrouter-key"),
                patch.object(config, "OPENAI_MODELS", ["acme/ohne-preis"]),
            ):
                at = AppTest.from_file(PAGES / "settings.py")
                at.run()
            assert not at.exception, at.exception
            preise_tab = at.tabs[2]
            assert not preise_tab.button and not preise_tab.number_input
            df = preise_tab.dataframe[0].value
            zeile = df[df.iloc[:, 0] == "acme/ohne-preis"].iloc[0]
            assert zeile.iloc[-1] in ("offen", "open")
        finally:
            if saved is not None:
                repo.set_json("preise_openrouter", saved)


class TestHouseholdCatalog:
    """2026-09-27: the per-agent picker follows the household model catalog."""

    def test_picker_offers_current_claude_models_and_marks_a_saved_old_one(
            self, tmp_path, monkeypatch):
        katalog = tmp_path / "katalog.toml"
        katalog.write_text(
            '[claude]\naktuell = ["claude-opus-5-5", "claude-sonnet-5"]\n\n'
            '[claude.preise."claude-opus-5-5"]\neingabe = 4\nausgabe = 20\n',
            encoding="utf-8")
        monkeypatch.setenv("OPS_CORE_KATALOG", str(katalog))
        repo = get_app_config_repo()
        saved = repo.get("model_public_devils_advocate")
        try:
            repo.set("model_public_devils_advocate", "claude-opus-5")
            with (
                patch.object(config, "LLM_API_KEY", "test-key"),
                # the Models API: the account sees both, old and new
                patch("core.llm.claude.fetch_available_models",
                      return_value=["claude-opus-5-5", "claude-opus-5", "claude-sonnet-5"]),
            ):
                at = AppTest.from_file(PAGES / "settings.py")
                at.run()
            assert not at.exception, f"Page threw exception: {at.exception}"
            boxes = [s for s in at.selectbox if s.key and s.key.startswith("_model_public_")]
            assert boxes
            # AppTest reports options as rendered labels (format_func applied).
            fremd = [s for s in boxes if s.key != "_model_public_bereich_watchlist"]
            assert "claude-opus-5-5" in fremd[0].options
            assert not any(o.startswith("claude-opus-5 ") or o == "claude-opus-5"
                           for o in fremd[0].options)                 # retired: not offered
            # Seit 11.10.2026 ein Feld je Bereich; die Watchlist faellt auf den Eintrag des DA zurueck.
            da = next(s for s in boxes if s.key == "_model_public_bereich_watchlist")
            assert "claude-opus-5 — nicht mehr aktuell" in da.options \
                or "claude-opus-5 — no longer current" in da.options  # saved: visible, marked
        finally:
            if saved is None:
                repo.delete("model_public_devils_advocate")
            else:
                repo.set("model_public_devils_advocate", saved)


def test_drei_bereiche_nach_bedeutung():
    """Gliederung seit 12.10.2026: Pruefung (Checks und Modelle), System (Sprache zuerst), Preise."""
    at = AppTest.from_file(PAGES / "settings.py", default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    assert [tab.label for tab in at.tabs] == ["Prüfung", "System", "Preise"]
    pruefung, system = at.tabs[0], at.tabs[1]
    assert any(b.key == "_save_models_btn" for b in pruefung.button)
    assert system.radio, "Sprache steht unter System"
    assert system.subheader[0].value == system.radio[0].label
