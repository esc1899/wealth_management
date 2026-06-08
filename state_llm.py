"""
LLM provider factories and helpers.
"""

from config import config
from core.llm.base import LLMProvider
from core.llm.claude import ClaudeProvider
from core.llm.local import OllamaProvider
from state_repos import get_usage_repo, get_app_config_repo


_TAVILY_NEWS_AGENTS = {"news", "structural_scan"}
_TAVILY_ADVANCED_AGENTS = {"fundamental_analyzer"}


def _make_claude_provider(model: str, agent_name: str, enable_thinking: bool = False, tavily_search_depth: str = "basic") -> ClaudeProvider:
    """Create and wire up a Claude provider with usage tracking."""
    provider = ClaudeProvider(
        api_key=config.LLM_API_KEY,
        model=model,
        base_url=config.LLM_BASE_URL,
        enable_thinking=enable_thinking,
        tavily_search_depth=tavily_search_depth,
    )
    provider.on_usage = lambda i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None, web_search=None: get_usage_repo().record(agent_name, model, i, o, skill=skill, duration_ms=dur, position_count=pos, cache_read_tokens=cache_read, cache_write_tokens=cache_write, web_search_requests=web_search)
    return provider


def _make_openai_provider(model: str, agent_name: str, tavily_search_depth: str = "basic") -> "OpenAICompatibleProvider":
    """Create and wire up an OpenAI-compatible provider with usage tracking."""
    from core.llm.openai_compatible import OpenAICompatibleProvider
    provider = OpenAICompatibleProvider(
        api_key=config.OPENAI_API_KEY,
        model=model,
        base_url=config.OPENAI_BASE_URL,
        tavily_news_mode=agent_name in _TAVILY_NEWS_AGENTS,
        tavily_search_depth=tavily_search_depth,
        provider_order=config.OPENAI_PROVIDER or None,
    )

    def _on_usage(i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None, web_search=None):
        get_usage_repo().record(
            agent_name, model, i, o,
            skill=skill, duration_ms=dur, position_count=pos,
            cache_read_tokens=cache_read, cache_write_tokens=cache_write,
            web_search_requests=web_search,
            generation_id=provider.last_generation_id,
        )

    provider.on_usage = _on_usage
    return provider


def _make_deepseek_provider(model: str, agent_name: str) -> "OpenAICompatibleProvider":
    """Create a DeepSeek direct API provider (cheaper than OpenRouter middlemen)."""
    from core.llm.openai_compatible import OpenAICompatibleProvider
    provider = OpenAICompatibleProvider(
        api_key=config.DEEPSEEK_API_KEY,
        model=model,
        base_url=config.DEEPSEEK_BASE_URL,
    )

    def _on_usage(i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None, web_search=None):
        get_usage_repo().record(
            agent_name, model, i, o,
            skill=skill, duration_ms=dur, position_count=pos,
            cache_read_tokens=cache_read, cache_write_tokens=cache_write,
            web_search_requests=web_search,
            generation_id=provider.last_generation_id,
        )

    provider.on_usage = _on_usage
    return provider


def _make_public_provider(model: str, agent_name: str, enable_thinking: bool = False) -> LLMProvider:
    """Route to the right provider based on model name prefix."""
    search_depth = "advanced" if agent_name in _TAVILY_ADVANCED_AGENTS else "basic"
    if model.startswith("claude-") and config.LLM_API_KEY:
        return _make_claude_provider(model, agent_name, enable_thinking=enable_thinking, tavily_search_depth=search_depth)
    if model.startswith("deepseek-") and config.DEEPSEEK_API_KEY:
        return _make_deepseek_provider(model, agent_name)
    if config.OPENAI_BASE_URL:
        return _make_openai_provider(model, agent_name, tavily_search_depth=search_depth)
    return _make_claude_provider(model, agent_name, enable_thinking=enable_thinking, tavily_search_depth=search_depth)


def _get_public_agent_model(agent_key: str, default: str) -> str:
    """Get model for a public agent. Uses unified model_public_* key, falls back to legacy provider-specific keys."""
    repo = get_app_config_repo()
    saved = repo.get(f"model_public_{agent_key}")
    if saved:
        return saved
    for prefix in ("openai", "claude"):
        saved = repo.get(f"model_{prefix}_{agent_key}")
        if saved:
            return saved
    env_default = config.LLM_DEFAULT_MODEL
    if env_default:
        return env_default
    if config.OPENAI_MODELS:
        return config.OPENAI_MODELS[0]
    if config.CLAUDE_MODELS:
        return config.CLAUDE_MODELS[0]
    return default


def _make_ollama_provider(model: str, agent_name: str, timeout: float = 120.0) -> OllamaProvider:
    """Create and wire up an Ollama provider with usage tracking."""
    provider = OllamaProvider(host=config.OLLAMA_HOST, model=model, timeout=timeout, num_ctx=config.OLLAMA_NUM_CTX)
    provider.on_usage = lambda i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None, web_search=None: get_usage_repo().record(agent_name, model, i, o, skill=skill, duration_ms=dur, position_count=pos, cache_read_tokens=cache_read, cache_write_tokens=cache_write, web_search_requests=web_search)
    return provider


def _get_agent_model(agent_key: str, model_type: str, default: str) -> str:
    """Return model for a specific agent. Falls back to global setting then env default."""
    repo = get_app_config_repo()
    if model_type == "openai":
        env_default = config.LLM_DEFAULT_MODEL or (config.OPENAI_MODELS[0] if config.OPENAI_MODELS else "")
        valid = set(config.OPENAI_MODELS)
        def _ok(m) -> str:
            return (m or "") if (not valid or m in valid) else ""
    else:
        env_default = config.LLM_DEFAULT_MODEL
        _ok = lambda m: m or ""
    return (
        _ok(repo.get(f"model_{model_type}_{agent_key}"))
        or _ok(repo.get(f"model_{model_type}"))
        or env_default
        or default
    )
