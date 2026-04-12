"""
LLM provider factory.
Returns the correct provider based on the requested backend.
"""

from enum import Enum
from core.constants import CLAUDE_SONNET
from core.llm.base import LLMProvider


class LLMBackend(str, Enum):
    LOCAL = "local"   # Ollama — private, on-device
    CLAUDE = "claude"  # Anthropic Claude API


def create_llm(backend: LLMBackend, **kwargs) -> LLMProvider:
    """
    Create and return an LLM provider.

    For LOCAL:   pass host= and model=
    For CLAUDE:  pass api_key= (and optionally model=)
    """
    if backend == LLMBackend.LOCAL:
        from core.llm.local import OllamaProvider
        return OllamaProvider(
            host=kwargs["host"],
            model=kwargs["model"],
        )
    if backend == LLMBackend.CLAUDE:
        from core.llm.claude import ClaudeProvider
        return ClaudeProvider(
            api_key=kwargs["api_key"],
            model=kwargs.get("model", CLAUDE_SONNET),
        )
    raise ValueError(f"Unknown LLM backend: {backend}")
