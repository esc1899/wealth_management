"""
Abstract base class for all LLM providers.
Both local (Ollama) and cloud (Claude) providers implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    role: Role
    content: str


class LLMProvider(ABC):
    """Common interface for all LLM backends."""

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
