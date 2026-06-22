"""Unit tests for the single-source-of-truth provider routing."""

from core.llm.router import (
    available_public_models,
    resolve_provider_kind,
    tavily_news_mode,
    tavily_search_depth,
)


class TestResolveProviderKind:
    def test_claude_model_with_key(self):
        assert resolve_provider_kind(
            "claude-sonnet-4-6", has_anthropic=True, has_deepseek=True, has_openai_base=True
        ) == "claude"

    def test_claude_model_without_key_falls_to_openai(self):
        assert resolve_provider_kind(
            "claude-sonnet-4-6", has_anthropic=False, has_deepseek=False, has_openai_base=True
        ) == "openai"

    def test_openrouter_deepseek_model_routes_to_openai(self):
        # "deepseek/..." is OpenRouter format — does NOT match the "deepseek-" direct prefix.
        assert resolve_provider_kind(
            "deepseek/deepseek-v4-pro", has_anthropic=True, has_deepseek=True, has_openai_base=True
        ) == "openai"

    def test_deepseek_direct_prefix(self):
        assert resolve_provider_kind(
            "deepseek-chat", has_anthropic=True, has_deepseek=True, has_openai_base=True
        ) == "deepseek"

    def test_deepseek_direct_without_creds_falls_to_openai(self):
        # The scheduler has no DeepSeek-direct keys → deepseek-* falls through.
        assert resolve_provider_kind(
            "deepseek-chat", has_anthropic=True, has_deepseek=False, has_openai_base=True
        ) == "openai"

    def test_no_credentials_falls_back_to_claude(self):
        assert resolve_provider_kind(
            "anything", has_anthropic=False, has_deepseek=False, has_openai_base=False
        ) == "claude"


class TestAvailablePublicModels:
    DEEPSEEK = ["deepseek-chat", "deepseek-reasoner"]  # config default — non-empty!
    OPENROUTER = ["anthropic/claude-sonnet-4-6", "deepseek/deepseek-v4"]
    CLAUDE = ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]

    def _call(self, **flags):
        return available_public_models(
            claude_models=self.CLAUDE,
            openrouter_models=self.OPENROUTER,
            deepseek_models=self.DEEPSEEK,
            registry={},
            **flags,
        )

    def test_anthropic_proxy_only_hides_deepseek_and_openrouter(self):
        # The work-machine case: only the Anthropic proxy is configured.
        result = self._call(has_anthropic=True, has_openrouter=False, has_deepseek=False)
        assert result == self.CLAUDE
        assert "deepseek-chat" not in result  # the 404 trap is gone

    def test_openrouter_only(self):
        result = self._call(has_anthropic=False, has_openrouter=True, has_deepseek=False)
        assert result == self.OPENROUTER

    def test_all_providers_keep_order_and_dedup(self):
        result = self._call(has_anthropic=True, has_openrouter=True, has_deepseek=True)
        assert result == self.DEEPSEEK + self.OPENROUTER + self.CLAUDE
        assert len(result) == len(set(result))

    def test_no_providers_yields_empty(self):
        assert self._call(has_anthropic=False, has_openrouter=False, has_deepseek=False) == []

    def test_registry_model_gated_by_its_provider(self):
        registry = {"some/model": "deepseek", "other/model": "openrouter"}
        result = available_public_models(
            claude_models=self.CLAUDE, openrouter_models=[], deepseek_models=[],
            registry=registry, has_anthropic=True, has_openrouter=True, has_deepseek=False,
        )
        assert "other/model" in result      # openrouter is active
        assert "some/model" not in result   # deepseek is not


class TestTavilyFlags:
    def test_search_depth(self):
        assert tavily_search_depth("fundamental_analyzer") == "advanced"
        assert tavily_search_depth("news") == "basic"

    def test_news_mode(self):
        for a in ("news", "structural_scan", "sector_rotation", "search_agent"):
            assert tavily_news_mode(a) is True
        assert tavily_news_mode("consensus_gap") is False
