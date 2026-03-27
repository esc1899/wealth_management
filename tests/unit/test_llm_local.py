import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from core.llm.local import OllamaProvider
from core.llm.base import Message, Role


@pytest.fixture
def provider():
    return OllamaProvider(host="http://localhost:11434", model="llama3.2")


def ollama_response(content: str) -> dict:
    return {"message": {"role": "assistant", "content": content}}


@pytest.mark.asyncio
async def test_chat_returns_content(provider):
    mock_response = MagicMock()
    mock_response.json.return_value = ollama_response("Hello from Ollama")
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
        result = await provider.chat([Message(role=Role.USER, content="Hi")])
    assert result == "Hello from Ollama"


@pytest.mark.asyncio
async def test_complete_wraps_chat(provider):
    mock_response = MagicMock()
    mock_response.json.return_value = ollama_response("Market is bullish")
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)):
        result = await provider.complete("What is the market doing?")
    assert result == "Market is bullish"


@pytest.mark.asyncio
async def test_complete_includes_system_message(provider):
    captured = {}

    async def capture_post(*args, json=None, **kwargs):
        captured["payload"] = json
        mock = MagicMock()
        mock.json.return_value = ollama_response("ok")
        mock.raise_for_status = MagicMock()
        return mock

    with patch("httpx.AsyncClient.post", new=capture_post):
        await provider.complete("User prompt", system="You are a finance expert")

    messages = captured["payload"]["messages"]
    roles = [m["role"] for m in messages]
    assert "system" in roles
    assert "user" in roles


@pytest.mark.asyncio
async def test_http_error_propagates(provider):
    with patch(
        "httpx.AsyncClient.post",
        new=AsyncMock(side_effect=httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            await provider.chat([Message(role=Role.USER, content="hi")])


def test_model_property(provider):
    assert provider.model == "llama3.2"
