"""
Ollama LLM provider — runs entirely on the local Mac Mini.
Requires Ollama to be installed and running (https://ollama.com).
"""

import httpx
from core.llm.base import LLMProvider, Message, Role


class OllamaProvider(LLMProvider):
    """
    Communicates with Ollama's REST API.
    No data leaves the machine.
    """

    def __init__(self, host: str, model: str, timeout: float = 120.0):
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def chat(
        self,
        messages: list[Message],
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": msg.role.value, "content": msg.content}
                for msg in messages
            ],
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._host}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]

    @property
    def model(self) -> str:
        return self._model
