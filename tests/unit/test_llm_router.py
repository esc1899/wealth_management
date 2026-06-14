"""Unit tests for the single-source-of-truth provider routing."""

from core.llm.router import (
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


class TestTavilyFlags:
    def test_search_depth(self):
        assert tavily_search_depth("fundamental_analyzer") == "advanced"
        assert tavily_search_depth("news") == "basic"

    def test_news_mode(self):
        for a in ("news", "structural_scan", "sector_rotation", "search_agent"):
            assert tavily_news_mode(a) is True
        assert tavily_news_mode("consensus_gap") is False
