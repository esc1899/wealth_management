"""
UI smoke tests for the Settings page — FEAT-57 model registry.

Verifies the page renders without exception and that the registry editor
(provider column + save button) is wired up. Model discovery (Claude/Ollama)
falls back gracefully on network errors, so no mocking is required.
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

    def test_registry_save_button_present(self):
        at = AppTest.from_file(PAGES / "settings.py")
        at.run()
        keys = [b.key for b in at.button]
        assert "_save_prices_btn" in keys, keys

    def test_provider_selectboxes_rendered(self):
        # One provider selectbox per registry row → at least the default models
        at = AppTest.from_file(PAGES / "settings.py")
        at.run()
        prov_keys = [s.key for s in at.selectbox if s.key and s.key.startswith("_price_prov_")]
        assert prov_keys, "expected per-model provider selectboxes"

    def test_delete_checkboxes_and_add_dropdown_present(self):
        at = AppTest.from_file(PAGES / "settings.py")
        at.run()
        del_keys = [c.key for c in at.checkbox if c.key and c.key.startswith("_price_del_")]
        assert del_keys, "expected per-model delete checkboxes"
        pick_keys = [s.key for s in at.selectbox if s.key == "_new_price_pick"]
        assert pick_keys, "expected add-model picker dropdown"

    def test_deleted_model_disappears_from_registry(self):
        repo = get_app_config_repo()
        original_prices = repo.get_model_prices()
        original_deleted = repo.get_deleted_models()
        try:
            repo.set_deleted_models(["deepseek/deepseek-r1"])
            reg = repo.get_model_registry()
            assert "deepseek/deepseek-r1" not in reg
        finally:
            repo.set_deleted_models(original_deleted)
            repo.set_model_prices(original_prices)

    def test_registered_openrouter_model_becomes_selectable(self):
        """A model added to the registry must appear in the agent model dropdowns."""
        repo = get_app_config_repo()
        original = repo.get_model_prices()
        try:
            merged = dict(original)
            merged["acme/new-router-model"] = {
                "input": 1.0, "output": 2.0, "provider": "openrouter",
            }
            repo.set_model_prices(merged)

            # settings.py blendet die OpenRouter-Modelle aus, solange
            # _HAS_OPENROUTER falsch ist (pages/settings.py:105). Die Vorbedingung
            # gehört in den Test: früher kam sie unausgesprochen aus der echten
            # .env des Entwicklers, was den Test von einer Datei abhängig machte,
            # die weder im Repo noch in CI existiert.
            with (
                patch.object(config, "OPENAI_BASE_URL", "https://openrouter.test/api/v1"),
                patch.object(config, "OPENAI_API_KEY", "test-openrouter-key"),
            ):
                at = AppTest.from_file(PAGES / "settings.py")
                at.run()
            assert not at.exception, f"Page threw exception: {at.exception}"
            all_options = [opt for s in at.selectbox for opt in (s.options or [])]
            assert "acme/new-router-model" in all_options
        finally:
            repo.set_model_prices(original)
