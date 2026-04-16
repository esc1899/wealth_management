"""
LLM provider factories and helpers.
"""

from config import config
from core.llm.claude import ClaudeProvider
from core.llm.local import OllamaProvider
from state_repos import get_usage_repo, get_app_config_repo


def _make_claude_provider(model: str, agent_name: str) -> ClaudeProvider:
    """Create and wire up a Claude provider with usage tracking."""
    provider = ClaudeProvider(
        api_key=config.ANTHROPIC_API_KEY,
        model=model,
    )
    provider.on_usage = lambda i, o, skill=None, dur=None, pos=None: get_usage_repo().record(agent_name, model, i, o, skill=skill, duration_ms=dur, position_count=pos)
    return provider


def _make_ollama_provider(model: str, agent_name: str, timeout: float = 120.0) -> OllamaProvider:
    """Create and wire up an Ollama provider with usage tracking."""
    provider = OllamaProvider(host=config.OLLAMA_HOST, model=model, timeout=timeout)
    provider.on_usage = lambda i, o, skill=None, dur=None, pos=None: get_usage_repo().record(agent_name, model, i, o, skill=skill, duration_ms=dur, position_count=pos)
    return provider


def _get_agent_model(agent_key: str, model_type: str, default: str) -> str:
    """Return model for a specific agent. Falls back to global setting then env default."""
    repo = get_app_config_repo()
    return (
        repo.get(f"model_{model_type}_{agent_key}")
        or repo.get(f"model_{model_type}")
        or default
    )
