"""
OpenAI-compatible LLM provider — supports Perplexity Sonar, Groq, Together, etc.
Requires OPENAI_API_KEY and OPENAI_BASE_URL.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, List, Optional

from openai import AsyncOpenAI

from core.llm.base import LLMProvider, Message, Role

_logger = logging.getLogger(__name__)

_WEB_SEARCH_TYPES = {"web_search_20250305"}


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool format to OpenAI function calling format.

    Handles three formats:
    - Format A (already OpenAI): type=function → pass through
    - Format B (Anthropic custom): name + input_schema → convert to function
    - Format C (Anthropic built-in): web_search_20250305 → drop (provider handles)
    """
    result = []
    for t in tools:
        # Skip Anthropic built-in tools (Sonar handles search internally)
        if t.get("type") in _WEB_SEARCH_TYPES:
            continue
        # Already in OpenAI format
        if t.get("type") == "function":
            result.append(t)
            continue
        # Anthropic custom tool format
        if "name" in t and "input_schema" in t:
            result.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t["input_schema"],
                }
            })
    return result


@dataclass
class _OAIToolCall:
    """Represents a tool call from OpenAI API."""
    id: str
    name: str
    input: dict


@dataclass
class _OAIResponse:
    """Response from OpenAI-compatible provider (duck-type compatible with ClaudeResponse)."""
    content: str
    tool_calls: List[_OAIToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    raw_blocks: List[Any] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class OpenAICompatibleProvider(LLMProvider):
    """
    Wraps OpenAI-compatible APIs (Perplexity Sonar, Groq, Together, etc.).
    Uses the openai SDK with base_url override to support any compatible endpoint.
    """

    def __init__(self, api_key: str = "", model: str = "", base_url: str = ""):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model

    async def chat(
        self,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        oai_messages = [{"role": m.role.value, "content": m.content} for m in messages]
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=oai_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        _t0_import = __import__("time").monotonic() if self.on_usage else None
        if self.on_usage and response.usage:
            self.on_usage(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                self.skill_context,
                None,
                self.position_count,
            )
        return response.choices[0].message.content or ""

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
        max_tokens: int = 2048,
    ) -> _OAIResponse:
        """
        Call OpenAI-compatible API with tool definitions.
        Converts Anthropic tool format to OpenAI function calling format.

        For Perplexity Sonar: built-in web search is automatic.
        For other providers: full function calling support.
        """
        import time

        oai_tools = _to_openai_tools(tools)
        oai_messages = [{"role": "system", "content": system}] if system else []
        oai_messages.extend(messages)

        kwargs = {
            "model": self._model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools

        _t0 = time.monotonic()
        response = await self._client.chat.completions.create(**kwargs)
        _duration_ms = int((time.monotonic() - _t0) * 1000)

        msg = response.choices[0].message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    input_dict = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, AttributeError) as e:
                    _logger.warning("Failed to parse tool arguments: %s", e)
                    input_dict = {}
                tool_calls.append(_OAIToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    input=input_dict,
                ))

        if self.on_usage and response.usage:
            self.on_usage(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                self.skill_context,
                _duration_ms,
                self.position_count,
            )

        stop_reason = "tool_use" if tool_calls else "end_turn"
        return _OAIResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            stop_reason=stop_reason,
        )
