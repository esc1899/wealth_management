"""
LLM provider factories and helpers.
"""

from config import config
from core.llm.base import LLMProvider
from core.llm.claude import ClaudeProvider
from core.llm.local import OllamaProvider
from state_repos import get_usage_repo, get_app_config_repo


def _make_claude_provider(model: str, agent_name: str, enable_thinking: bool = False) -> ClaudeProvider:
    """Create and wire up a Claude provider with usage tracking."""
    provider = ClaudeProvider(
        api_key=config.LLM_API_KEY,
        model=model,
        base_url=config.LLM_BASE_URL,
        enable_thinking=enable_thinking,
    )
    provider.on_usage = lambda i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None, web_search=None: get_usage_repo().record(agent_name, model, i, o, skill=skill, duration_ms=dur, position_count=pos, cache_read_tokens=cache_read, cache_write_tokens=cache_write, web_search_requests=web_search)
    return provider


def _make_openai_provider(model: str, agent_name: str) -> "OpenAICompatibleProvider":
    """Create and wire up an OpenAI-compatible provider with usage tracking."""
    from core.llm.openai_compatible import OpenAICompatibleProvider
    provider = OpenAICompatibleProvider(
        api_key=config.OPENAI_API_KEY,
        model=model,
        base_url=config.OPENAI_BASE_URL,
    )
    provider.on_usage = lambda i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None, web_search=None: get_usage_repo().record(agent_name, model, i, o, skill=skill, duration_ms=dur, position_count=pos, cache_read_tokens=cache_read, cache_write_tokens=cache_write, web_search_requests=web_search)
    return provider


def _make_public_provider(model: str, agent_name: str, enable_thinking: bool = False) -> LLMProvider:
    """Return either OpenAI-compatible or Claude provider based on active config."""
    if config.OPENAI_BASE_URL:
        return _make_openai_provider(model, agent_name)
    return _make_claude_provider(model, agent_name, enable_thinking=enable_thinking)


def _get_public_agent_model(agent_key: str, default: str) -> str:
    """Get model for a public (cloud) agent. Uses model_openai or model_claude keys depending on active provider."""
    model_type = "openai" if config.OPENAI_BASE_URL else "claude"
    return _get_agent_model(agent_key, model_type, default)


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
    else:
        env_default = config.LLM_DEFAULT_MODEL
    return (
        repo.get(f"model_{model_type}_{agent_key}")
        or repo.get(f"model_{model_type}")
        or env_default
        or default
    )
