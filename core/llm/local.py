"""
Ollama LLM provider — runs entirely on the local Mac Mini.
Requires Ollama to be installed and running (https://ollama.com).
"""

import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from core.llm.base import LLMProvider, Message, Role


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class OllamaResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class OllamaProvider(LLMProvider):
    """
    Communicates with Ollama's REST API.
    No data leaves the machine.
    """

    def __init__(self, host: str, model: str, timeout: float = 120.0, think: bool = False):
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._think = think  # qwen3 thinking mode — disable for faster tool calling

    async def chat(
        self,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        result = await self.chat_with_tools(messages, tools=[], max_tokens=max_tokens, temperature=temperature)
        return result.content

    async def chat_with_tools(
        self,
        messages: list[Message],
        tools: list[dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> OllamaResponse:
        """Send messages with optional tool definitions, returns content and tool calls."""
        payload = {
            "model": self._model,
            "messages": [
                {"role": msg.role.value, "content": msg.content}
                for msg in messages
            ],
            "stream": False,
            "think": self._think,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        if tools:
            payload["tools"] = tools

        _t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._host}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        _duration_ms = int((time.monotonic() - _t0) * 1000)

        message = data["message"]
        tool_calls = [
            ToolCall(
                name=tc["function"]["name"],
                arguments=tc["function"]["arguments"],
            )
            for tc in message.get("tool_calls", [])
        ]
        if self.on_usage:
            self.on_usage(
                data.get("prompt_eval_count", 0),
                data.get("eval_count", 0),
                self.skill_context,
                _duration_ms,
            )
        return OllamaResponse(
            content=message.get("content", ""),
            tool_calls=tool_calls,
        )

    @property
    def model(self) -> str:
        return self._model
