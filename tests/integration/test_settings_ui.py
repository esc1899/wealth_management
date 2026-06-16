"""
UI smoke tests for the Settings page — FEAT-57 model registry.

Verifies the page renders without exception and that the registry editor
(provider column + save button) is wired up. Model discovery (Claude/Ollama)
falls back gracefully on network errors, so no mocking is required.
"""

from streamlit.testing.v1 import AppTest

from state import get_app_config_repo


class TestSettingsPage:
    def test_page_loads(self):
        at = AppTest.from_file("pages/settings.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_registry_save_button_present(self):
        at = AppTest.from_file("pages/settings.py")
        at.run()
        keys = [b.key for b in at.button]
        assert "_save_prices_btn" in keys, keys

    def test_provider_selectboxes_rendered(self):
        # One provider selectbox per registry row → at least the default models
        at = AppTest.from_file("pages/settings.py")
        at.run()
        prov_keys = [s.key for s in at.selectbox if s.key and s.key.startswith("_price_prov_")]
        assert prov_keys, "expected per-model provider selectboxes"

    def test_delete_checkboxes_and_add_dropdown_present(self):
        at = AppTest.from_file("pages/settings.py")
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

            at = AppTest.from_file("pages/settings.py")
            at.run()
            assert not at.exception, f"Page threw exception: {at.exception}"
            all_options = [opt for s in at.selectbox for opt in (s.options or [])]
            assert "acme/new-router-model" in all_options
        finally:
            repo.set_model_prices(original)
