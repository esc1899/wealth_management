import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from core.llm.openai_compatible import (
    OpenAICompatibleProvider,
    _to_openai_tools,
    _OAIResponse,
    _OAIToolCall,
)
from core.llm.base import Message, Role


@pytest.fixture
def provider():
    """OpenAICompatibleProvider with test credentials."""
    return OpenAICompatibleProvider(
        api_key="test_key",
        model="sonar",
        base_url="https://api.test.example.com",
    )


def make_oai_response(text: str, tool_calls=None) -> MagicMock:
    """Create a mock OpenAI API response."""
    msg = MagicMock()
    msg.content = text
    msg.tool_calls = tool_calls or []

    resp = MagicMock()
    resp.choices = [MagicMock(message=msg)]
    resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    return resp


def make_tool_call(tool_id: str, name: str, args: dict) -> MagicMock:
    """Create a mock tool call from OpenAI API."""
    tc = MagicMock()
    tc.id = tool_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


# ------------------------------------------------------------------
# _to_openai_tools() — format conversion
# ------------------------------------------------------------------


class TestToOpenAITools:
    """Test the tool format conversion function."""

    def test_empty_list(self):
        """Empty tool list returns empty list."""
        result = _to_openai_tools([])
        assert result == []

    def test_openai_format_passthrough(self):
        """Tools already in OpenAI format pass through unchanged."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search the web",
                    "parameters": {"type": "object"},
                }
            }
        ]
        result = _to_openai_tools(tools)
        assert len(result) == 1
        assert result[0] == tools[0]

    def test_anthropic_custom_format_converted(self):
        """Anthropic custom tool format (name + input_schema) is converted to OpenAI."""
        tools = [
            {
                "name": "analyze",
                "description": "Analyze a stock",
                "input_schema": {
                    "type": "object",
                    "properties": {"ticker": {"type": "string"}},
                }
            }
        ]
        result = _to_openai_tools(tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "analyze"
        assert result[0]["function"]["description"] == "Analyze a stock"
        assert result[0]["function"]["parameters"]["type"] == "object"

    def test_anthropic_builtin_web_search_dropped(self):
        """Anthropic built-in web_search_20250305 tool is filtered out."""
        tools = [
            {"type": "web_search_20250305"},
            {
                "name": "get_price",
                "description": "Get stock price",
                "input_schema": {"type": "object"},
            }
        ]
        result = _to_openai_tools(tools)
        # Only the custom tool should remain
        assert len(result) == 1
        assert result[0]["function"]["name"] == "get_price"

    def test_mixed_formats(self):
        """All three formats mixed together are handled correctly."""
        tools = [
            # Format A: OpenAI-style
            {
                "type": "function",
                "function": {"name": "openai_tool", "description": "OAI", "parameters": {}},
            },
            # Format B: Anthropic custom
            {
                "name": "anthropic_tool",
                "description": "Anthropic",
                "input_schema": {"type": "object"},
            },
            # Format C: Anthropic built-in
            {"type": "web_search_20250305"},
        ]
        result = _to_openai_tools(tools)
        # Should have 2 tools: A passthrough + B converted, C dropped
        assert len(result) == 2
        assert result[0]["function"]["name"] == "openai_tool"
        assert result[1]["function"]["name"] == "anthropic_tool"

    def test_anthropic_custom_without_description(self):
        """Anthropic custom tool without description gets empty string."""
        tools = [
            {
                "name": "tool_no_desc",
                "input_schema": {"type": "object"},
            }
        ]
        result = _to_openai_tools(tools)
        assert result[0]["function"]["description"] == ""


# ------------------------------------------------------------------
# chat() — basic text completion
# ------------------------------------------------------------------


class TestChat:
    """Test the chat() method for simple completions."""

    @pytest.mark.asyncio
    async def test_returns_content(self, provider):
        """chat() returns the message content."""
        provider._client.chat.completions.create = AsyncMock(
            return_value=make_oai_response("Analysis complete")
        )
        result = await provider.chat([Message(role=Role.USER, content="Analyse AAPL")])
        assert result == "Analysis complete"

    @pytest.mark.asyncio
    async def test_on_usage_callback_fires(self, provider):
        """chat() calls on_usage callback with token counts."""
        captured_usage = {}

        def capture_usage(in_tokens, out_tokens, skill=None, duration=None, pos=None):
            captured_usage.update({
                "in": in_tokens,
                "out": out_tokens,
                "skill": skill,
                "duration": duration,
                "pos": pos,
            })

        provider.on_usage = capture_usage
        provider.skill_context = "test_skill"
        provider.position_count = 5

        provider._client.chat.completions.create = AsyncMock(
            return_value=make_oai_response("ok")
        )
        await provider.chat([Message(role=Role.USER, content="test")])

        assert captured_usage["in"] == 10
        assert captured_usage["out"] == 5
        assert captured_usage["skill"] == "test_skill"
        assert captured_usage["duration"] is None  # chat() always passes None
        assert captured_usage["pos"] == 5

    @pytest.mark.asyncio
    async def test_on_usage_none_does_not_crash(self, provider):
        """chat() works fine when on_usage is None."""
        provider.on_usage = None
        provider._client.chat.completions.create = AsyncMock(
            return_value=make_oai_response("ok")
        )
        result = await provider.chat([Message(role=Role.USER, content="test")])
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_string(self, provider):
        """chat() handles None response.content gracefully."""
        resp = make_oai_response("dummy")
        resp.choices[0].message.content = None
        provider._client.chat.completions.create = AsyncMock(return_value=resp)
        result = await provider.chat([Message(role=Role.USER, content="test")])
        assert result == ""

    def test_model_property(self, provider):
        """provider.model returns the configured model."""
        assert provider.model == "sonar"


# ------------------------------------------------------------------
# chat_with_tools() — tool calling
# ------------------------------------------------------------------


class TestChatWithTools:
    """Test the chat_with_tools() method for function calling."""

    @pytest.mark.asyncio
    async def test_no_tool_calls_returns_end_turn(self, provider):
        """When no tool calls, stop_reason is 'end_turn'."""
        provider._client.chat.completions.create = AsyncMock(
            return_value=make_oai_response("Final answer")
        )
        result = await provider.chat_with_tools(
            messages=[],
            tools=[],
        )
        assert result.stop_reason == "end_turn"
        assert result.content == "Final answer"
        assert len(result.tool_calls) == 0

    @pytest.mark.asyncio
    async def test_tool_call_returns_tool_use(self, provider):
        """When tool calls present, stop_reason is 'tool_use'."""
        tc = make_tool_call("call_123", "search", {"query": "AAPL"})
        resp = make_oai_response("calling search")
        resp.choices[0].message.tool_calls = [tc]

        provider._client.chat.completions.create = AsyncMock(return_value=resp)
        result = await provider.chat_with_tools(
            messages=[],
            tools=[],
        )

        assert result.stop_reason == "tool_use"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_123"
        assert result.tool_calls[0].name == "search"
        assert result.tool_calls[0].input == {"query": "AAPL"}

    @pytest.mark.asyncio
    async def test_system_message_prepended(self, provider):
        """System message is prepended to the message list."""
        captured = {}

        async def mock_create(**kwargs):
            captured.update(kwargs)
            return make_oai_response("ok")

        provider._client.chat.completions.create = mock_create

        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        system = "You are helpful"

        await provider.chat_with_tools(messages=messages, tools=[], system=system)

        # First message should be system
        assert captured["messages"][0]["role"] == "system"
        assert captured["messages"][0]["content"] == "You are helpful"
        # Then user and assistant
        assert captured["messages"][1]["role"] == "user"
        assert captured["messages"][2]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_no_system_omits_system_entry(self, provider):
        """Without system message, no system entry is added."""
        captured = {}

        async def mock_create(**kwargs):
            captured.update(kwargs)
            return make_oai_response("ok")

        provider._client.chat.completions.create = mock_create

        messages = [{"role": "user", "content": "Hello"}]
        await provider.chat_with_tools(messages=messages, tools=[], system="")

        # No system message should be in the list
        assert captured["messages"][0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_empty_tools_omits_tools_key(self, provider):
        """When tools are empty after conversion, 'tools' key is omitted."""
        captured = {}

        async def mock_create(**kwargs):
            captured.update(kwargs)
            return make_oai_response("ok")

        provider._client.chat.completions.create = mock_create

        # Tools that will be filtered to empty list
        tools = [{"type": "web_search_20250305"}]
        await provider.chat_with_tools(messages=[], tools=tools)

        assert "tools" not in captured

    @pytest.mark.asyncio
    async def test_nonempty_tools_includes_tools_key(self, provider):
        """When tools remain after conversion, 'tools' key is included."""
        captured = {}

        async def mock_create(**kwargs):
            captured.update(kwargs)
            return make_oai_response("ok")

        provider._client.chat.completions.create = mock_create

        tools = [
            {
                "name": "search",
                "description": "Search",
                "input_schema": {"type": "object"},
            }
        ]
        await provider.chat_with_tools(messages=[], tools=tools)

        assert "tools" in captured
        assert len(captured["tools"]) == 1

    @pytest.mark.asyncio
    async def test_json_decode_error_returns_empty_input(self, provider):
        """Malformed JSON in tool arguments results in empty input dict."""
        tc = make_tool_call("call_1", "search", {"query": "test"})
        # Corrupt the JSON
        tc.function.arguments = "{ invalid json }"

        resp = make_oai_response("calling")
        resp.choices[0].message.tool_calls = [tc]

        provider._client.chat.completions.create = AsyncMock(return_value=resp)
        result = await provider.chat_with_tools(messages=[], tools=[])

        assert result.tool_calls[0].input == {}
        assert result.tool_calls[0].name == "search"

    @pytest.mark.asyncio
    async def test_on_usage_callback_with_duration(self, provider):
        """chat_with_tools() includes duration_ms in on_usage callback."""
        captured_usage = {}

        def capture_usage(in_tokens, out_tokens, skill=None, duration=None, pos=None):
            captured_usage.update({
                "duration": duration,
            })

        provider.on_usage = capture_usage

        provider._client.chat.completions.create = AsyncMock(
            return_value=make_oai_response("ok")
        )
        await provider.chat_with_tools(messages=[], tools=[])

        # duration should be a number >= 0
        assert captured_usage["duration"] is not None
        assert isinstance(captured_usage["duration"], int)
        assert captured_usage["duration"] >= 0

    @pytest.mark.asyncio
    async def test_web_search_tool_dropped_tools_key_omitted(self, provider):
        """When only web_search_20250305 tool, tools key is omitted."""
        captured = {}

        async def mock_create(**kwargs):
            captured.update(kwargs)
            return make_oai_response("Sonar handles search internally")

        provider._client.chat.completions.create = mock_create

        # Only web search tool
        tools = [{"type": "web_search_20250305"}]
        result = await provider.chat_with_tools(messages=[], tools=tools)

        assert "tools" not in captured
        assert result.content == "Sonar handles search internally"

    @pytest.mark.asyncio
    async def test_response_object_structure(self, provider):
        """Returned _OAIResponse has correct structure."""
        tc = make_tool_call("call_1", "search", {"q": "test"})
        resp = make_oai_response("searching")
        resp.choices[0].message.tool_calls = [tc]

        provider._client.chat.completions.create = AsyncMock(return_value=resp)
        result = await provider.chat_with_tools(messages=[], tools=[])

        assert isinstance(result, _OAIResponse)
        assert result.content == "searching"
        assert result.stop_reason == "tool_use"
        assert result.has_tool_calls is True
        assert len(result.raw_blocks) == 0

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, provider):
        """Multiple tool calls are all captured."""
        tc1 = make_tool_call("call_1", "search", {"query": "AAPL"})
        tc2 = make_tool_call("call_2", "price", {"ticker": "MSFT"})

        resp = make_oai_response("calling tools")
        resp.choices[0].message.tool_calls = [tc1, tc2]

        provider._client.chat.completions.create = AsyncMock(return_value=resp)
        result = await provider.chat_with_tools(messages=[], tools=[])

        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].name == "search"
        assert result.tool_calls[1].name == "price"
