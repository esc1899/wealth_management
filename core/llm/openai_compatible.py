"""
OpenAI-compatible LLM provider — supports Perplexity Sonar, Groq, Together, etc.
Requires OPENAI_API_KEY and OPENAI_BASE_URL.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, List, Optional

from openai import AsyncOpenAI

from core.llm.base import LLMProvider, Message, Role

_logger = logging.getLogger(__name__)

_WEB_SEARCH_TYPES = {"web_search_20250305"}
_MAX_SEARCH_ITERATIONS = 8


def _to_openai_tools(tools: list[dict], tavily_key: str = "") -> list[dict]:
    """Convert Anthropic tool format to OpenAI function calling format.

    Handles three formats:
    - Format A (already OpenAI): type=function → pass through
    - Format B (Anthropic custom): name + input_schema → convert to function
    - Format C (Anthropic built-in): web_search_20250305 → replace with Tavily if key set, else drop
    """
    from core.search import tavily as _tavily
    result = []
    tavily_added = False
    for t in tools:
        if t.get("type") in _WEB_SEARCH_TYPES:
            if tavily_key and not tavily_added:
                td = _tavily.TAVILY_TOOL_DEFINITION
                result.append({
                    "type": "function",
                    "function": {
                        "name": td["name"],
                        "description": td["description"],
                        "parameters": td["input_schema"],
                    },
                })
                tavily_added = True
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

    def __init__(self, api_key: str = "", model: str = "", base_url: str = "", tavily_news_mode: bool = False, provider_order: Optional[List[str]] = None, tavily_search_depth: str = "basic"):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model
        self._tavily_news_mode = tavily_news_mode
        self._tavily_search_depth = tavily_search_depth
        self._provider_extra = {"provider": {"order": provider_order, "allow_fallbacks": True}} if provider_order else {}
        self.last_generation_id: Optional[str] = None

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
            extra_body=self._provider_extra or None,
        )
        self.last_generation_id = getattr(response, "id", None)

        if self.on_usage and response.usage:
            self.on_usage(
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
                self.skill_context,
                None,
                self.position_count,
                None,
                None,
            )
        return response.choices[0].message.content or ""

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
        max_tokens: int = 2048,
        enable_thinking: bool = False,  # accepted for API compatibility, ignored
    ) -> _OAIResponse:
        """
        Call OpenAI-compatible API with tool definitions.
        Converts Anthropic tool format to OpenAI function calling format.

        web_search calls are executed internally via Tavily (if TAVILY_API_KEY is set)
        and looped until the model produces a final text response or calls a non-search tool.
        Other tool calls (e.g. propose_for_watchlist) are returned to the caller.
        """
        import time
        from core.search import tavily as _tavily

        tavily_key = os.getenv("TAVILY_API_KEY", "")

        # Extract max_uses before _to_openai_tools drops it (server-side field, not in OAI format)
        _web_search_max_uses: Optional[int] = next(
            (t.get("max_uses") for t in tools if t.get("type") in _WEB_SEARCH_TYPES),
            None,
        )
        _tavily_call_count = 0

        # Normalize Anthropic multi-turn format → OpenAI format
        messages = self._normalize_messages(messages)

        oai_tools = _to_openai_tools(tools, tavily_key)
        oai_messages = [{"role": "system", "content": system}] if system else []
        oai_messages.extend(messages)

        kwargs: dict = {
            "model": self._model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
        if self._provider_extra:
            kwargs["extra_body"] = self._provider_extra

        _t0 = time.monotonic()
        total_input = total_output = 0
        total_web_search = 0

        for _ in range(_MAX_SEARCH_ITERATIONS):
            response = await self._client.chat.completions.create(**kwargs)
            self.last_generation_id = getattr(response, "id", None)
            msg = response.choices[0].message

            if response.usage:
                total_input += response.usage.prompt_tokens
                total_output += response.usage.completion_tokens

            # Separate web_search calls (handled here) from other tool calls (returned to caller)
            search_calls = []
            other_calls: list[_OAIToolCall] = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        input_dict = json.loads(tc.function.arguments)
                    except (json.JSONDecodeError, AttributeError) as e:
                        _logger.warning("Failed to parse tool arguments: %s", e)
                        input_dict = {}
                    if tc.function.name == "web_search" and tavily_key:
                        search_calls.append((tc.id, input_dict.get("query", "")))
                    else:
                        other_calls.append(_OAIToolCall(id=tc.id, name=tc.function.name, input=input_dict))

            if search_calls:
                # Execute Tavily searches and feed results back
                oai_assistant_msg: dict = {
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [
                        {"id": tc_id, "type": "function", "function": {"name": "web_search", "arguments": json.dumps({"query": q})}}
                        for tc_id, q in search_calls
                    ],
                }
                oai_messages.append(oai_assistant_msg)
                _tavily_kwargs = {"days": 14, "topic": "news"} if self._tavily_news_mode else {}
                _limit_hit = False
                for tc_id, query in search_calls:
                    if _web_search_max_uses is not None and _tavily_call_count >= _web_search_max_uses:
                        result = f"[Search limit reached. Call the verdict/result tool now — do not search again.]"
                        _limit_hit = True
                    else:
                        _tavily_call_count += 1
                        total_web_search += 1
                        try:
                            result = _tavily.search(query, tavily_key, search_depth=self._tavily_search_depth, **_tavily_kwargs)
                        except Exception as e:
                            _logger.warning("Tavily search failed for query %r: %s", query, e)
                            result = f"Search unavailable: {e}"
                    oai_messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})
                kwargs["messages"] = oai_messages
                # When limit is hit, force the model to call a non-search tool instead of searching again
                if _limit_hit:
                    non_search = [t for t in oai_tools if t["function"]["name"] != "web_search"]
                    if non_search:
                        kwargs["tool_choice"] = {"type": "function", "function": {"name": non_search[0]["function"]["name"]}}
                else:
                    kwargs.pop("tool_choice", None)
                continue

            # No (more) web_search calls — done
            _duration_ms = int((time.monotonic() - _t0) * 1000)
            if self.on_usage:
                self.on_usage(total_input, total_output, self.skill_context, _duration_ms, self.position_count, None, None, total_web_search or None)

            oai_assistant_msg = {"role": "assistant", "content": msg.content or None}
            if other_calls:
                oai_assistant_msg["tool_calls"] = [
                    {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.input)}}
                    for tc in other_calls
                ]

            stop_reason = "tool_use" if other_calls else "end_turn"
            return _OAIResponse(
                content=msg.content or "",
                tool_calls=other_calls,
                stop_reason=stop_reason,
                raw_blocks=[oai_assistant_msg],
            )

        _duration_ms = int((time.monotonic() - _t0) * 1000)
        if self.on_usage:
            self.on_usage(total_input, total_output, self.skill_context, _duration_ms, self.position_count, None, None, total_web_search or None)
        return _OAIResponse(content="", tool_calls=[], stop_reason="end_turn", raw_blocks=[])
