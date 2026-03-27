"""
Langfuse monitoring client (v3 API).
Wraps LLM calls with tracing so all agent runs are visible in the Langfuse UI.
"""

from __future__ import annotations

from typing import Optional
from langfuse import Langfuse

from core.llm.base import LLMProvider, Message


class MonitoredLLMProvider(LLMProvider):
    """
    Wraps any LLMProvider and records every call as a Langfuse generation.
    Drop-in replacement: same interface as the underlying provider.
    """

    def __init__(self, provider: LLMProvider, client: Langfuse):
        self._provider = provider
        self._client = client

    async def chat(
        self,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        trace_name: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        name = trace_name or f"llm/{self._provider.model}"
        input_payload = [
            {"role": m.role.value, "content": m.content} for m in messages
        ]

        with self._client.start_as_current_generation(
            name=name,
            model=self._provider.model,
            input=input_payload,
            model_parameters={"max_tokens": max_tokens, "temperature": temperature},
            metadata=metadata or {},
        ) as generation:
            try:
                result = await self._provider.chat(
                    messages, max_tokens=max_tokens, temperature=temperature
                )
                generation.update(output=result, status_message="success")
                return result
            except Exception as exc:
                generation.update(level="ERROR", status_message=str(exc))
                raise
            finally:
                self._client.flush()

    @property
    def model(self) -> str:
        return self._provider.model


def create_langfuse_client(
    public_key: str,
    secret_key: str,
    host: str = "http://localhost:3000",
) -> Langfuse:
    return Langfuse(
        public_key=public_key,
        secret_key=secret_key,
        host=host,
    )


def wrap_with_monitoring(provider: LLMProvider, client: Langfuse) -> MonitoredLLMProvider:
    """Wrap a provider with Langfuse monitoring."""
    return MonitoredLLMProvider(provider, client)
