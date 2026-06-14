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
from core.constants import CLAUDE_SONNET, CLAUDE_OPUS
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


def fetch_available_models(api_key: str, base_url: str = "") -> list[str]:
    """Fetch available Claude models from Anthropic API. Returns empty list on error."""
    try:
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = anthropic.Anthropic(**kwargs)
        return [m.id for m in client.models.list()]
    except Exception as e:
        _logger.debug("Anthropic model discovery failed: %s", e)
        return []


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
    web_search_requests: int = 0            # web search calls made (Tavily or server-side)

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

    def __init__(self, api_key: str = "", model: str = DEFAULT_MODEL, base_url: str = "", enable_thinking: bool = False, tavily_search_depth: str = "basic"):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = anthropic.AsyncAnthropic(**kwargs)
        self._model = model
        self._enable_thinking = enable_thinking
        self._tavily_search_depth = tavily_search_depth

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
            cache_read = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
            cache_write = getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
            self.on_usage(response.usage.input_tokens, response.usage.output_tokens, self.skill_context, _duration_ms, self.position_count, cache_read, cache_write)
        return response.content[0].text

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
        max_tokens: int = 2048,
        enable_thinking: Optional[bool] = None,
        tool_choice: Optional[dict] = None,
    ) -> ClaudeResponse:
        """
        Single API call with tool definitions.

        Anthropic's built-in server-side web_search is passed through natively: the
        model runs any searches server-side within a single response, so there is no
        client-side search loop. Returns the text content and any client tool calls.
        """
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": list(messages),
            "tools": tools,
        }
        if system:
            kwargs["system"] = [{"type": "text", "text": system}]
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        # effort: "high" reduces thinking token overhead; Haiku does not support effort
        # Skip output_config when tool_choice forces a specific tool — incompatible combination
        if self._model in {CLAUDE_SONNET, CLAUDE_OPUS} and not tool_choice:
            kwargs["output_config"] = {"effort": "high"}
            _thinking = self._enable_thinking if enable_thinking is None else enable_thinking
            if _thinking:
                kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}

        _t0 = time.monotonic()

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

        total_input = response.usage.input_tokens
        total_output = response.usage.output_tokens
        total_cache_read = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
        total_cache_write = getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
        # Anthropic built-in web_search: count from the server_tool_use usage field.
        _stu = getattr(response.usage, 'server_tool_use', None)
        total_web_search = getattr(_stu, 'web_search_requests', 0) or 0

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

        # Validate response for signs of prompt injection
        content_text = validate_llm_response(content_text)

        _duration_ms = int((time.monotonic() - _t0) * 1000)
        if self.on_usage:
            self.on_usage(total_input, total_output, self.skill_context, _duration_ms, self.position_count, total_cache_read, total_cache_write, total_web_search)
        return ClaudeResponse(
            content=content_text,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
            raw_blocks=list(response.content),
            web_search_requests=total_web_search,
        )

    # ------------------------------------------------------------------
    # Message Batches API — 50% cheaper, async processing (up to 24h)
    # ------------------------------------------------------------------

    @staticmethod
    def build_batch_request(
        custom_id: str,
        model: str,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
    ) -> dict:
        """Build one request dict for the Message Batches API."""
        params: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system:
            params["system"] = system
        if tools:
            params["tools"] = tools
        return {"custom_id": custom_id, "params": params}

    async def submit_batch(self, requests: list[dict]) -> str:
        """Submit a message batch. Returns the batch_id."""
        batch = await self._client.messages.batches.create(requests=requests)
        return batch.id

    async def fetch_batch_results(self, batch_id: str):
        """
        Return results list when the batch is complete, None if still processing.
        Each result has: .custom_id, .result.type ("succeeded"|"errored"), .result.message
        """
        batch = await self._client.messages.batches.retrieve(batch_id)
        if batch.processing_status != "ended":
            return None
        results = []
        async for result in self._client.messages.batches.results(batch_id):
            results.append(result)
        return results

    @property
    def model(self) -> str:
        return self._model
