"""Unit tests for the single-source-of-truth provider routing."""

from core.llm.router import (
    available_public_models,
    current_claude_models,
    resolve_provider_kind,
    tavily_news_mode,
    tavily_search_depth,
)


class TestResolveProviderKind:
    def test_claude_model_with_key(self):
        assert resolve_provider_kind(
            "claude-sonnet-4-6", has_anthropic=True, has_openai_base=True
        ) == "claude"

    def test_claude_model_without_key_falls_to_openai(self):
        assert resolve_provider_kind(
            "claude-sonnet-4-6", has_anthropic=False, has_openai_base=True
        ) == "openai"

    def test_deepseek_goes_through_openrouter(self):
        # DeepSeek direkt gibt es seit 12.10.2026 nicht mehr -- beide Schreibweisen gehen
        # ueber OpenRouter.
        for model in ("deepseek/deepseek-v4-pro", "deepseek-chat"):
            assert resolve_provider_kind(
                model, has_anthropic=True, has_openai_base=True) == "openai"

    def test_no_credentials_falls_back_to_claude(self):
        assert resolve_provider_kind(
            "anything", has_anthropic=False, has_openai_base=False
        ) == "claude"


class TestAvailablePublicModels:
    OPENROUTER = ["anthropic/claude-sonnet-4-6", "deepseek/deepseek-v4"]
    CLAUDE = ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"]

    def _call(self, **flags):
        return available_public_models(
            claude_models=self.CLAUDE, openrouter_models=self.OPENROUTER, **flags)

    def test_anthropic_proxy_only_hides_openrouter(self):
        # The work-machine case: only the Anthropic proxy is configured.
        assert self._call(has_anthropic=True, has_openrouter=False) == self.CLAUDE

    def test_openrouter_only(self):
        assert self._call(has_anthropic=False, has_openrouter=True) == self.OPENROUTER

    def test_both_keep_order_and_dedup(self):
        result = self._call(has_anthropic=True, has_openrouter=True)
        assert result == self.OPENROUTER + self.CLAUDE
        assert len(result) == len(set(result))

    def test_no_providers_yields_empty(self):
        assert self._call(has_anthropic=False, has_openrouter=False) == []


class TestTavilyFlags:
    def test_search_depth(self):
        assert tavily_search_depth("fundamental_analyzer") == "advanced"
        assert tavily_search_depth("news") == "basic"

    def test_news_mode(self):
        for a in ("news", "structural_scan", "sector_rotation", "search_agent"):
            assert tavily_news_mode(a) is True
        assert tavily_news_mode("consensus_gap") is False


class TestCurrentClaudeModels:
    """Die Models-API liefert die komplette Claude-Historie — als Auswahl brauchen wir
    nur die konfigurierten aktuellen Modelle, gefiltert auf tatsächlich Verfügbares."""

    CONFIGURED = ["claude-haiku-4-5-20251001", "claude-sonnet-5", "claude-opus-5"]

    def test_filters_history_down_to_configured(self):
        available = [
            "claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8", "claude-opus-5",
            "claude-sonnet-4-5", "claude-sonnet-4-6", "claude-sonnet-5",
            "claude-haiku-4-5-20251001", "claude-fable-5",
        ]
        assert current_claude_models(self.CONFIGURED, available) == self.CONFIGURED

    def test_dateless_alias_counts_as_available(self):
        # API meldet den Alias, konfiguriert ist die datierte ID (oder umgekehrt)
        available = ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"]
        assert current_claude_models(self.CONFIGURED, available) == self.CONFIGURED

    def test_unavailable_model_drops_out(self):
        # Firmenproxy gibt Opus nicht frei
        available = ["claude-haiku-4-5-20251001", "claude-sonnet-5"]
        assert current_claude_models(self.CONFIGURED, available) == [
            "claude-haiku-4-5-20251001", "claude-sonnet-5",
        ]

    def test_empty_api_answer_keeps_configured_list(self):
        assert current_claude_models(self.CONFIGURED, []) == self.CONFIGURED

    def test_no_overlap_keeps_configured_list(self):
        # Lieber ungefiltert als leer — sonst steht der User ohne Auswahl da
        assert current_claude_models(self.CONFIGURED, ["gpt-5", "mistral-large"]) == self.CONFIGURED
