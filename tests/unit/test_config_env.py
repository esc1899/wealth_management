"""Config env-loading: the Anthropic-standard fallbacks must apply.

The corporate Anthropic proxy is typically configured via the SDK-standard
ANTHROPIC_BASE_URL. The app reads LLM_BASE_URL, so without an explicit fallback the
proxy is silently ignored and calls hit api.anthropic.com → 404.
"""

import importlib

import pytest


@pytest.fixture
def reloaded_config(monkeypatch):
    """Reimport config.py with a controlled environment.

    Reloading rebinds config.config to a new instance; other modules did
    `from config import config` and hold the original. So we restore that exact
    original instance on teardown to keep object identity (and their monkeypatches)
    intact for the rest of the suite.
    """
    import config as config_module
    original_instance = config_module.config

    def _load(env: dict) -> object:
        for var in ("LLM_BASE_URL", "ANTHROPIC_BASE_URL", "LLM_API_KEY", "ANTHROPIC_API_KEY", "ENV_PROFILE"):
            monkeypatch.delenv(var, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        importlib.reload(config_module)
        return config_module.config

    yield _load
    config_module.config = original_instance


class TestBaseUrlFallback:
    def test_anthropic_base_url_is_used_when_llm_base_url_absent(self, reloaded_config):
        cfg = reloaded_config({"ANTHROPIC_BASE_URL": "http://localhost:6655/ANTHROPIC"})
        assert cfg.LLM_BASE_URL == "http://localhost:6655/ANTHROPIC"

    def test_llm_base_url_wins_over_anthropic_base_url(self, reloaded_config):
        cfg = reloaded_config({
            "LLM_BASE_URL": "http://proxy/LLM",
            "ANTHROPIC_BASE_URL": "http://proxy/ANTHROPIC",
        })
        assert cfg.LLM_BASE_URL == "http://proxy/LLM"

    def test_empty_when_neither_set(self, reloaded_config):
        cfg = reloaded_config({})
        assert cfg.LLM_BASE_URL == ""
