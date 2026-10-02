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
from core.constants import (
    CLAUDE_SONNET, WEB_SEARCH_TYPE_BASIC, WEB_SEARCH_TYPES, supports_dynamic_search, supports_effort,
)
from core.house_models import house_effort
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

# Wie oft eine vom Server unterbrochene Runde (``pause_turn``) live fortgesetzt wird.
# Die Suche mit dynamischer Filterung läuft über Code-Ausführung und kann länger
# dauern als eine Runde; im Batch gibt es kein Fortsetzen.
MAX_PAUSE_CONTINUATIONS = 4


def tools_for_model(tools: list[dict], model: str) -> list[dict]:
    """Die Werkzeuge so, wie dieses Modell sie annimmt.

    Die Agenten nennen die Websuche mit dynamischer Filterung (``WEB_SEARCH_TYPE``);
    Haiku 4.5 kann sie nicht und bekäme einen 400 -- dort die Grundfassung.
    """
    if supports_dynamic_search(model):
        return tools
    return [
        {**t, "type": WEB_SEARCH_TYPE_BASIC} if t.get("type") in WEB_SEARCH_TYPES else t
        for t in tools
    ]


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
        self._base_url = base_url
        self._enable_thinking = enable_thinking
        self._tavily_search_depth = tavily_search_depth

    def _reasoning_kwargs(
        self, enable_thinking: Optional[bool] = None, *, forced_tool: bool = False
    ) -> dict:
        """effort/thinking-Parameter für das konfigurierte Modell (leer außer Sonnet/Opus).

        Ab Sonnet 5 / Opus 5 denkt das Modell auch dann, wenn gar kein ``thinking``
        mitgeschickt wird — auf 4.6/4.8 hieß Weglassen noch "nicht denken". Denk-Tokens
        zählen gegen ``max_tokens``. Explizites Abschalten wäre bei freier Tool-Wahl
        riskant: Opus 5 schreibt Tool-Aufrufe dann gelegentlich als Fließtext statt als
        ``tool_use``-Block — der Aufruf passiert stillschweigend nicht. Der UI-Toggle
        steuert deshalb die Denktiefe über ``effort``, nicht das Denken selbst.

        Bei erzwungenem ``tool_choice`` gibt es keine Prosa-Antwort; Denken wäre reine
        Kosten und frisst das knappe Token-Budget → dort abgeschaltet (``output_config``
        verträgt sich nicht mit erzwungenem tool_choice).
        """
        if not supports_effort(self._model):
            return {}
        if forced_tool:
            return {"thinking": {"type": "disabled"}}
        _thinking = self._enable_thinking if enable_thinking is None else enable_thinking
        # "Denken an" bleibt high; sonst die Denktiefe des Hauses aus dem
        # Maschinenraum (2026-10-02) -- ohne sie medium wie bisher.
        effort = "high" if _thinking else (house_effort() or "medium")
        kwargs: dict = {"output_config": {"effort": effort}}
        if _thinking:
            kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
        return kwargs

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
        kwargs.update(self._reasoning_kwargs())

        _t0 = time.monotonic()
        response = await self._client.messages.create(**kwargs)
        _duration_ms = int((time.monotonic() - _t0) * 1000)
        if self.on_usage:
            cache_read = getattr(response.usage, 'cache_read_input_tokens', 0) or 0
            cache_write = getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
            self.on_usage(response.usage.input_tokens, response.usage.output_tokens, self.skill_context, _duration_ms, self.position_count, cache_read, cache_write)
        # Ab Sonnet/Opus 5 kann ein Denk-Block vorn stehen -- nur Textbloecke zaehlen.
        return "".join(b.text for b in response.content if getattr(b, "type", None) == "text")

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
        Tool-enabled call. Returns text content and any client-side tool calls.

        Web search: on a direct Anthropic endpoint, Anthropic's built-in server-side
        web_search runs within a single response (native passthrough). Behind a custom
        base_url (corporate proxy / OpenRouter) the upstream often rejects the
        server-side web_search tool (HTTP 400) — there we route search through Tavily
        client-side if TAVILY_API_KEY is set, looping internally so callers see no
        difference; without a key we drop the tool so the call still succeeds.
        ``strict`` an den Werkzeugen geht nur an Anthropic direkt; der Proxy bekommt
        sie ohne, wie bisher.

        Unterbricht der Server eine lange Runde (``pause_turn``), geht sie mit der
        Antwort bis dahin weiter -- bis zu ``MAX_PAUSE_CONTINUATIONS`` Mal.
        """
        import os
        from core.search import tavily as _tavily

        def _is_web_search(t: dict) -> bool:
            return t.get("type") in WEB_SEARCH_TYPES or t.get("name") == "web_search"

        from core.secrets import get_secret

        # Read per call, not once at import: the key may come from the keychain,
        # and a rotation should take effect without restarting the process.
        tavily_key = get_secret("TAVILY_API_KEY", "")
        _has_web_search = any(_is_web_search(t) for t in tools)
        _custom_endpoint = bool(self._base_url)
        # Native server-side web_search only works on a direct Anthropic endpoint.
        use_tavily = _has_web_search and _custom_endpoint and bool(tavily_key)

        # max_uses is a server-side-only field; capture it before we swap the tool out.
        _web_search_max_uses: Optional[int] = next(
            (t.get("max_uses") for t in tools if _is_web_search(t)), None
        )

        if use_tavily:
            resolved_tools = [_tavily.TAVILY_TOOL_DEFINITION if _is_web_search(t) else t for t in tools]
        elif _has_web_search and _custom_endpoint:
            # Proxy without native web_search and no Tavily key → drop the tool (no live search).
            resolved_tools = [t for t in tools if not _is_web_search(t)]
        else:
            resolved_tools = tools_for_model(tools, self._model)
        if _custom_endpoint:
            resolved_tools = [{k: v for k, v in t.items() if k != "strict"} for t in resolved_tools]

        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": list(messages),  # copy — extended in the Tavily loop
            "tools": resolved_tools,
        }
        if system:
            kwargs["system"] = [{"type": "text", "text": system}]
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        # Haiku kennt weder effort noch adaptives Denken — _reasoning_kwargs liefert
        # dafür ein leeres Dict.
        # Nur ein *erzwungenes* tool_choice (tool/any) schaltet das Denken ab; ``auto``
        # ist freie Wahl. Opus 5.5 kennt ohnehin keins von beiden (400), deshalb
        # erzwingt seit 2026-09-27 kein Aufrufer mehr.
        forced = bool(tool_choice) and tool_choice.get("type") in ("tool", "any")
        kwargs.update(self._reasoning_kwargs(enable_thinking, forced_tool=forced))

        _t0 = time.monotonic()
        total_input = total_output = total_cache_read = total_cache_write = total_web_search = 0
        _tavily_call_count = 0
        # Accumulate prose across ALL turns: the model often writes analysis text in the
        # same turn it calls web_search, then only e.g. the verdict tool in the final turn —
        # using the final message alone would drop it (the bug that motivated f94abfd).
        content_parts: list[str] = []

        _pauses = 0
        for _ in range(10):  # safety net; only Tavily and pause_turn iterate more than once
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
            total_cache_read += getattr(response.usage, 'cache_read_input_tokens', 0) or 0
            total_cache_write += getattr(response.usage, 'cache_creation_input_tokens', 0) or 0
            # Anthropic built-in web_search: count from the server_tool_use usage field.
            _stu = getattr(response.usage, 'server_tool_use', None)
            total_web_search += getattr(_stu, 'web_search_requests', 0) or 0

            for block in response.content:
                if hasattr(block, "text"):
                    content_parts.append(block.text)

            if use_tavily and response.stop_reason == "tool_use":
                web_calls = [b for b in response.content
                             if getattr(b, "type", None) == "tool_use" and getattr(b, "name", None) == "web_search"]
                other_calls = [b for b in response.content
                               if getattr(b, "type", None) == "tool_use" and getattr(b, "name", None) != "web_search"]
                if web_calls:
                    kwargs["messages"].append({"role": "assistant", "content": list(response.content)})
                    tool_results = []
                    for call in web_calls:
                        query = call.input.get("query", "")
                        if _web_search_max_uses is not None and _tavily_call_count >= _web_search_max_uses:
                            result = f"[Search limit of {_web_search_max_uses} reached. Base your answer on the results already gathered.]"
                        else:
                            _tavily_call_count += 1
                            total_web_search += 1
                            try:
                                result = _tavily.search(query, tavily_key, search_depth=self._tavily_search_depth)
                            except Exception as e:
                                result = f"Search failed: {e}"
                        tool_results.append({"type": "tool_result", "tool_use_id": call.id, "content": result})
                    kwargs["messages"].append({"role": "user", "content": tool_results})
                    if other_calls:
                        break  # hand non-search client tools back to the caller
                    continue  # fetch next response with search results injected
            if response.stop_reason == "pause_turn" and _pauses < MAX_PAUSE_CONTINUATIONS:
                # Fortsetzen heißt: die unterbrochene Antwort unverändert zurück, kein
                # "weiter" -- der Server erkennt es selbst.
                _pauses += 1
                kwargs["messages"].append({"role": "assistant", "content": list(response.content)})
                continue
            break

        tool_calls: List[ClaudeToolCall] = []
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                if not (use_tavily and block.name == "web_search"):
                    tool_calls.append(ClaudeToolCall(id=block.id, name=block.name, input=block.input))

        # Validate response for signs of prompt injection
        content_text = validate_llm_response("".join(content_parts))

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
        """Submit a message batch. Returns the batch_id.

        Dieselben effort/thinking-Parameter wie live (_reasoning_kwargs): Ohne sie
        denkt Sonnet/Opus 5.x auf "high" und verbraucht max_tokens, bevor es antwortet.
        """
        reasoning = self._reasoning_kwargs()
        for r in requests:
            for k, v in reasoning.items():
                r["params"].setdefault(k, v)
            if "tools" in r["params"]:
                r["params"]["tools"] = tools_for_model(r["params"]["tools"], r["params"]["model"])
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
