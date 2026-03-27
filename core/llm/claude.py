"""
Claude (Anthropic) LLM provider — used for agents that need advanced reasoning.
Requires ANTHROPIC_API_KEY.
"""

import anthropic
from core.llm.base import LLMProvider, Message, Role

# Claude model to use — update when a newer version is preferred
DEFAULT_MODEL = "claude-sonnet-4-6"


class ClaudeProvider(LLMProvider):
    """
    Wraps the Anthropic SDK.
    Only used for agents explicitly configured to use Claude.
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
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

        response = await self._client.messages.create(**kwargs)
        return response.content[0].text

    @property
    def model(self) -> str:
        return self._model
