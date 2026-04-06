"""
Claude (Anthropic) LLM provider — used for agents that need advanced reasoning.
Requires ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional

import anthropic
from core.llm.base import LLMProvider, Message, Role

# Claude model to use — update when a newer version is preferred
DEFAULT_MODEL = "claude-sonnet-4-6"


@dataclass
class ClaudeToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ClaudeResponse:
    content: str                            # text portion of the response
    tool_calls: List[ClaudeToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    raw_blocks: List[Any] = field(default_factory=list)  # raw SDK content blocks

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class ClaudeProvider(LLMProvider):
    """
    Wraps the Anthropic SDK.
    Only used for agents explicitly configured to use Claude.
    """

    def __init__(self, api_key: str = "", model: str = DEFAULT_MODEL):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def chat(
        self,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        system_content = ""
        api_messages = []

        for msg in messages:
            if msg.role == Role.SYSTEM:
                system_content = msg.content
            else:
                api_messages.append(
                    {"role": msg.role.value, "content": msg.content}
                )

        kwargs = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }
        if system_content:
            kwargs["system"] = system_content

        _t0 = time.monotonic()
        response = await self._client.messages.create(**kwargs)
        _duration_ms = int((time.monotonic() - _t0) * 1000)
        if self.on_usage:
            self.on_usage(response.usage.input_tokens, response.usage.output_tokens, self.skill_context, _duration_ms)
        return response.content[0].text

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
        max_tokens: int = 2048,
    ) -> ClaudeResponse:
        """
        Single API call with tool definitions.
        Returns text content and any client-side tool calls.
        Server-side tools (web_search) are handled automatically by Anthropic.
        """
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": tools,
        }
        if system:
            kwargs["system"] = system

        # Retry up to 3 times on rate limit errors (60s between attempts)
        _t0 = time.monotonic()
        for attempt in range(3):
            try:
                response = await self._client.messages.create(**kwargs)
                break
            except anthropic.RateLimitError:
                if attempt < 2:
                    await asyncio.sleep(60)
                else:
                    raise

        content_text = ""
        tool_calls: List[ClaudeToolCall] = []

        for block in response.content:
            if hasattr(block, "text"):
                content_text += block.text
            elif getattr(block, "type", None) == "tool_use":
                tool_calls.append(ClaudeToolCall(
                    id=block.id,
                    name=block.name,
                    input=block.input,
                ))

        _duration_ms = int((time.monotonic() - _t0) * 1000)
        if self.on_usage:
            self.on_usage(response.usage.input_tokens, response.usage.output_tokens, self.skill_context, _duration_ms)
        return ClaudeResponse(
            content=content_text,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            raw_blocks=list(response.content),
        )

    @property
    def model(self) -> str:
        return self._model
