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

    def _normalize_messages(self, messages: list[dict]) -> list[dict]:
        """
        Normalize messages for OpenAI API, converting Anthropic multi-turn format.

        Handles:
        - Unwrap OAI assistant message from raw_blocks list
        - Convert Anthropic tool_result → OpenAI role=tool messages
        """
        result = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            # Unwrap OAI assistant message stored in raw_blocks list
            if role == "assistant" and isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict) and first.get("role") == "assistant":
                    result.append(first)
                    continue

            # Convert Anthropic tool_result → OpenAI role=tool messages
            if role == "user" and isinstance(content, list) and content:
                first = content[0]
                if isinstance(first, dict) and first.get("type") == "tool_result":
                    for item in content:
                        result.append({
                            "role": "tool",
                            "tool_call_id": item["tool_use_id"],
                            "content": str(item["content"]),
                        })
                    continue

            result.append(msg)
        return result

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

        # Normalize Anthropic multi-turn format → OpenAI format
        messages = self._normalize_messages(messages)

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

        # Build OAI-format assistant message for multi-turn compatibility
        oai_assistant_msg: dict = {"role": "assistant", "content": msg.content or None}
        if tool_calls:
            oai_assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.input)},
                }
                for tc in tool_calls
            ]

        stop_reason = "tool_use" if tool_calls else "end_turn"
        return _OAIResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            raw_blocks=[oai_assistant_msg],
        )
