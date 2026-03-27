import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.llm.claude import ClaudeProvider
from core.llm.base import Message, Role


@pytest.fixture
def provider():
    return ClaudeProvider(api_key="test_key", model="claude-sonnet-4-6")


def make_claude_response(text: str) -> MagicMock:
    mock = MagicMock()
    mock.content = [MagicMock(text=text)]
    return mock


@pytest.mark.asyncio
async def test_chat_returns_content(provider):
    provider._client.messages.create = AsyncMock(
        return_value=make_claude_response("Analysis complete")
    )
    result = await provider.chat([Message(role=Role.USER, content="Analyse AAPL")])
    assert result == "Analysis complete"


@pytest.mark.asyncio
async def test_system_message_extracted(provider):
    captured = {}

    async def mock_create(**kwargs):
        captured.update(kwargs)
        return make_claude_response("ok")

    provider._client.messages.create = mock_create

    messages = [
        Message(role=Role.SYSTEM, content="You are a finance expert"),
        Message(role=Role.USER, content="What should I buy?"),
    ]
    await provider.chat(messages)

    assert captured.get("system") == "You are a finance expert"
    assert len(captured["messages"]) == 1
    assert captured["messages"][0]["role"] == "user"


@pytest.mark.asyncio
async def test_no_system_message_omits_system_key(provider):
    captured = {}

    async def mock_create(**kwargs):
        captured.update(kwargs)
        return make_claude_response("ok")

    provider._client.messages.create = mock_create
    await provider.chat([Message(role=Role.USER, content="Hello")])
    assert "system" not in captured


@pytest.mark.asyncio
async def test_complete_convenience(provider):
    provider._client.messages.create = AsyncMock(
        return_value=make_claude_response("Portfolio looks good")
    )
    result = await provider.complete("Review my portfolio")
    assert result == "Portfolio looks good"


@pytest.mark.asyncio
async def test_api_error_propagates(provider):
    import anthropic
    provider._client.messages.create = AsyncMock(
        side_effect=anthropic.APIError("rate limit", request=MagicMock(), body=None)
    )
    with pytest.raises(anthropic.APIError):
        await provider.chat([Message(role=Role.USER, content="hi")])


def test_model_property(provider):
    assert provider.model == "claude-sonnet-4-6"
