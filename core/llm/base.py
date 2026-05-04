"""
Abstract base class for all LLM providers.
Both local (Ollama) and cloud (Claude) providers implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    role: Role
    content: str


UsageCallback = Callable[[int, int, Optional[str], Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]], None]  # (input_tokens, output_tokens, skill, duration_ms, position_count, cache_read_tokens, cache_write_tokens, web_search_requests)


class LLMProvider(ABC):
    """Common interface for all LLM backends."""

    # Set by state.py after construction to record token usage.
    on_usage: Optional[UsageCallback] = None

    # Set by agents before each call so usage is attributed to the correct skill.
    skill_context: Optional[str] = None

    # Set by agents before batch calls to track how many positions were processed.
    position_count: Optional[int] = None

    @property
    def model(self) -> str:
        return self._model  # type: ignore[attr-defined]

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Send a list of messages and return the assistant reply."""
        ...

    async def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Convenience wrapper: single user prompt with optional system message."""
        messages: list[Message] = []
        if system:
            messages.append(Message(role=Role.SYSTEM, content=system))
        messages.append(Message(role=Role.USER, content=prompt))
        return await self.chat(messages, max_tokens=max_tokens, temperature=temperature)
