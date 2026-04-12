"""
Claude (Anthropic) LLM provider — used for agents that need advanced reasoning.
Requires ANTHROPIC_API_KEY.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional

import anthropic
from core.constants import CLAUDE_SONNET
from core.llm.base import LLMProvider, Message, Role

_logger = logging.getLogger(__name__)

# Patterns to detect signs of successful prompt injection in LLM output
_OUTPUT_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|prior)\s+instructions?",
    r"disregard\s+(your|the)\s+(system\s+)?instructions?",
    r"new\s+instructions?",
    r"execute\s+(this|the\s+following)",
]
_OUTPUT_COMPILED_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in _OUTPUT_INJECTION_PATTERNS
]

# Claude model to use — update when a newer version is preferred
DEFAULT_MODEL = CLAUDE_SONNET


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


def validate_llm_response(text: str) -> str:
    """
    Scan Claude's response for signs of successful prompt injection.
    Logs a warning if suspicious patterns are detected.
    Returns the response unchanged (non-blocking validation).

    Args:
        text: The LLM response text to validate

    Returns:
        The response unchanged (non-blocking)
    """
    for pattern in _OUTPUT_COMPILED_PATTERNS:
        if pattern.search(text):
            _logger.warning(
                "Suspicious pattern detected in LLM output: %s", pattern.pattern
            )
    return text


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
            self.on_usage(response.usage.input_tokens, response.usage.output_tokens, self.skill_context, _duration_ms, self.position_count)
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

        Server-side web_search (Anthropic built-in) is handled transparently.
        When TAVILY_API_KEY is set, web_search_20250305 is replaced with a
        client-side Tavily tool — the search loop runs internally so callers
        see no difference.
        """
        import os
        from core.search import tavily as _tavily

        tavily_key = os.getenv("TAVILY_API_KEY", "")
        _WEB_SEARCH_SERVER = "web_search_20250305"

        # Replace server-side web_search with Tavily client-side tool if configured
        if tavily_key:
            resolved_tools = [
                _tavily.TAVILY_TOOL_DEFINITION
                if t.get("type") == _WEB_SEARCH_SERVER or t.get("name") == "web_search"
                else t
                for t in tools
            ]
        else:
            resolved_tools = tools

        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": list(messages),  # copy — we may extend it in the Tavily loop
            "tools": resolved_tools,
        }
        if system:
            kwargs["system"] = system

        _t0 = time.monotonic()
        total_input = 0
        total_output = 0

        # Loop to handle Tavily tool calls (max 10 iterations as safety net)
        for _ in range(10):
            # Retry up to 3 times on rate limit errors
            for attempt in range(3):
                try:
                    response = await self._client.messages.create(**kwargs)
                    break
                except anthropic.RateLimitError:
                    if attempt < 2:
                        await asyncio.sleep(60)
                    else:
                        raise

            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens

            # Collect web_search tool calls if Tavily is active
            if tavily_key and response.stop_reason == "tool_use":
                web_calls = [
                    b for b in response.content
                    if getattr(b, "type", None) == "tool_use"
                    and getattr(b, "name", None) == "web_search"
                ]
                other_calls = [
                    b for b in response.content
                    if getattr(b, "type", None) == "tool_use"
                    and getattr(b, "name", None) != "web_search"
                ]

                if web_calls:
                    # Execute searches and inject results
                    kwargs["messages"].append(
                        {"role": "assistant", "content": list(response.content)}
                    )
                    tool_results = []
                    for call in web_calls:
                        query = call.input.get("query", "")
                        try:
                            result = _tavily.search(query, tavily_key)
                        except Exception as e:
                            result = f"Search failed: {e}"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "content": result,
                        })
                    kwargs["messages"].append(
                        {"role": "user", "content": tool_results}
                    )
                    # If there are also non-web client tools, break out to caller
                    if other_calls:
                        break
                    continue  # fetch next Claude response with search results injected

            # No more Tavily calls — exit loop
            break

        content_text = ""
        tool_calls: List[ClaudeToolCall] = []

        for block in response.content:
            if hasattr(block, "text"):
                content_text += block.text
            elif getattr(block, "type", None) == "tool_use":
                if not tavily_key or block.name != "web_search":
                    tool_calls.append(ClaudeToolCall(
                        id=block.id,
                        name=block.name,
                        input=block.input,
                    ))

        # Validate response for signs of prompt injection
        content_text = validate_llm_response(content_text)

        _duration_ms = int((time.monotonic() - _t0) * 1000)
        if self.on_usage:
            self.on_usage(total_input, total_output, self.skill_context, _duration_ms, self.position_count)
        return ClaudeResponse(
            content=content_text,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            raw_blocks=list(response.content),
        )

    @property
    def model(self) -> str:
        return self._model
