import pytest
from unittest.mock import AsyncMock, MagicMock
from core.llm.base import Message, Role
from monitoring.langfuse_client import MonitoredLLMProvider, wrap_with_monitoring


def make_generation_cm(generation: MagicMock) -> MagicMock:
    """Create a context manager mock that returns the generation mock."""
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=generation)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def make_langfuse_client():
    generation = MagicMock()
    generation.update = MagicMock()

    client = MagicMock()
    client.start_as_current_generation = MagicMock(
        return_value=make_generation_cm(generation)
    )
    client.flush = MagicMock()
    return client, generation


def make_provider(response: str = "result") -> MagicMock:
    provider = MagicMock()
    provider.model = "test-model"
    provider.chat = AsyncMock(return_value=response)
    return provider


@pytest.mark.asyncio
async def test_returns_provider_response():
    client, _ = make_langfuse_client()
    wrapped = MonitoredLLMProvider(make_provider("Hello"), client)
    result = await wrapped.chat([Message(role=Role.USER, content="Hi")])
    assert result == "Hello"


@pytest.mark.asyncio
async def test_generation_started_with_trace_name():
    client, _ = make_langfuse_client()
    wrapped = MonitoredLLMProvider(make_provider(), client)
    await wrapped.chat(
        [Message(role=Role.USER, content="Hi")],
        trace_name="portfolio_agent",
    )
    call_kwargs = client.start_as_current_generation.call_args.kwargs
    assert call_kwargs["name"] == "portfolio_agent"


@pytest.mark.asyncio
async def test_default_trace_name_uses_model():
    client, _ = make_langfuse_client()
    wrapped = MonitoredLLMProvider(make_provider(), client)
    await wrapped.chat([Message(role=Role.USER, content="Hi")])
    call_kwargs = client.start_as_current_generation.call_args.kwargs
    assert call_kwargs["name"] == "llm/test-model"


@pytest.mark.asyncio
async def test_generation_updated_on_success():
    client, generation = make_langfuse_client()
    wrapped = MonitoredLLMProvider(make_provider("ok"), client)
    await wrapped.chat([Message(role=Role.USER, content="Hi")])
    generation.update.assert_called_once_with(output="ok", status_message="success")


@pytest.mark.asyncio
async def test_generation_updated_with_error_on_failure():
    client, generation = make_langfuse_client()
    provider = make_provider()
    provider.chat = AsyncMock(side_effect=RuntimeError("LLM failed"))
    wrapped = MonitoredLLMProvider(provider, client)

    with pytest.raises(RuntimeError):
        await wrapped.chat([Message(role=Role.USER, content="Hi")])

    generation.update.assert_called_once()
    assert generation.update.call_args.kwargs.get("level") == "ERROR"


@pytest.mark.asyncio
async def test_flush_always_called():
    client, _ = make_langfuse_client()
    provider = make_provider()
    provider.chat = AsyncMock(side_effect=RuntimeError("fail"))
    wrapped = MonitoredLLMProvider(provider, client)

    with pytest.raises(RuntimeError):
        await wrapped.chat([Message(role=Role.USER, content="Hi")])

    client.flush.assert_called_once()


def test_model_property_delegates():
    client, _ = make_langfuse_client()
    wrapped = MonitoredLLMProvider(make_provider(), client)
    assert wrapped.model == "test-model"


def test_wrap_with_monitoring_returns_monitored_provider():
    client, _ = make_langfuse_client()
    result = wrap_with_monitoring(make_provider(), client)
    assert isinstance(result, MonitoredLLMProvider)
