"""
Unit tests for ResearchAgent.
LLM and repositories are mocked — no external calls.
"""

import sqlite3
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.research_agent import CLIENT_TOOL_NAMES, MAX_TOOL_ITERATIONS, ResearchAgent
from core.llm.claude import ClaudeResponse, ClaudeToolCall
from core.storage.models import ResearchMessage, ResearchSession
from core.strategy_config import CUSTOM_STRATEGY_NAME, StrategyConfig, StrategyRegistry


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def mock_positions_repo():
    repo = MagicMock()
    repo.add.return_value = MagicMock(id=42)
    return repo


@pytest.fixture
def mock_research_repo():
    repo = MagicMock()
    session = ResearchSession(
        id=1,
        ticker="AAPL",
        company_name="Apple Inc.",
        strategy_name="Value Investing",
        strategy_prompt="Focus on intrinsic value.",
        created_at=datetime.now(timezone.utc),
    )
    repo.get_session.return_value = session
    repo.create_session.return_value = session
    repo.get_messages.return_value = []
    repo.add_message.return_value = MagicMock()
    return repo


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.model = "claude-haiku-4-5-test"
    llm.chat_with_tools = AsyncMock(return_value=ClaudeResponse(
        content="Apple ist fundamental attraktiv bewertet.",
        tool_calls=[],
        stop_reason="end_turn",
    ))
    return llm


@pytest.fixture
def mock_strategy_registry():
    registry = MagicMock(spec=StrategyRegistry)
    registry.require.return_value = StrategyConfig(
        name="Value Investing",
        description="Graham style",
        system_prompt="Focus on intrinsic value.",
    )
    return registry


@pytest.fixture
def agent(mock_positions_repo, mock_research_repo, mock_llm, mock_strategy_registry):
    return ResearchAgent(
        positions_repo=mock_positions_repo,
        research_repo=mock_research_repo,
        llm=mock_llm,
        strategy_registry=mock_strategy_registry,
    )


# ------------------------------------------------------------------
# start_session
# ------------------------------------------------------------------

class TestStartSession:
    def test_creates_session_with_strategy_prompt(self, agent, mock_research_repo, mock_strategy_registry):
        agent.start_session("AAPL", "Value Investing")
        mock_research_repo.create_session.assert_called_once()
        call_kwargs = mock_research_repo.create_session.call_args[1]
        assert call_kwargs["ticker"] == "AAPL"
        assert call_kwargs["strategy_name"] == "Value Investing"
        assert "intrinsic value" in call_kwargs["strategy_prompt"]

    def test_uses_custom_prompt_when_provided(self, agent, mock_research_repo):
        agent.start_session("AAPL", CUSTOM_STRATEGY_NAME, custom_prompt="My custom focus.")
        call_kwargs = mock_research_repo.create_session.call_args[1]
        assert call_kwargs["strategy_prompt"] == "My custom focus."

    def test_custom_prompt_skips_registry_lookup(self, agent, mock_strategy_registry):
        agent.start_session("AAPL", CUSTOM_STRATEGY_NAME, custom_prompt="Custom.")
        mock_strategy_registry.require.assert_not_called()

    def test_named_strategy_looks_up_registry(self, agent, mock_strategy_registry):
        agent.start_session("AAPL", "Value Investing")
        mock_strategy_registry.require.assert_called_once_with("Value Investing")

    def test_company_name_passed_through(self, agent, mock_research_repo):
        agent.start_session("SAP.DE", "Value Investing", company_name="SAP SE")
        call_kwargs = mock_research_repo.create_session.call_args[1]
        assert call_kwargs["company_name"] == "SAP SE"

    def test_returns_session(self, agent):
        session = agent.start_session("AAPL", "Value Investing")
        assert session.ticker == "AAPL"


# ------------------------------------------------------------------
# chat
# ------------------------------------------------------------------

class TestChat:
    @pytest.mark.asyncio
    async def test_saves_user_message(self, agent, mock_research_repo):
        await agent.chat(1, "Analysiere Apple bitte.")
        mock_research_repo.add_message.assert_any_call(1, "user", "Analysiere Apple bitte.")

    @pytest.mark.asyncio
    async def test_saves_assistant_response(self, agent, mock_research_repo, mock_llm):
        mock_llm.chat_with_tools = AsyncMock(return_value=ClaudeResponse(
            content="Apple ist attraktiv.",
            tool_calls=[],
            stop_reason="end_turn",
        ))
        await agent.chat(1, "Analysiere.")
        mock_research_repo.add_message.assert_any_call(1, "assistant", "Apple ist attraktiv.")

    @pytest.mark.asyncio
    async def test_returns_assistant_text(self, agent, mock_llm):
        mock_llm.chat_with_tools = AsyncMock(return_value=ClaudeResponse(
            content="Starkes Buy-Signal.",
            tool_calls=[],
            stop_reason="end_turn",
        ))
        result = await agent.chat(1, "Bewerte Apple.")
        assert result == "Starkes Buy-Signal."

    @pytest.mark.asyncio
    async def test_raises_if_session_not_found(self, agent, mock_research_repo):
        mock_research_repo.get_session.return_value = None
        with pytest.raises(ValueError, match="Session 99 not found"):
            await agent.chat(99, "Test")

    @pytest.mark.asyncio
    async def test_calls_llm_with_tools(self, agent, mock_llm):
        await agent.chat(1, "Analysiere.")
        call_kwargs = mock_llm.chat_with_tools.call_args[1]
        tools = call_kwargs["tools"]
        tool_names = [t.get("name") or t.get("type", "") for t in tools]
        assert "add_to_watchlist" in tool_names
        assert any("web_search" in n for n in tool_names)

    @pytest.mark.asyncio
    async def test_system_prompt_contains_strategy(self, agent, mock_llm):
        await agent.chat(1, "Analysiere.")
        call_kwargs = mock_llm.chat_with_tools.call_args[1]
        assert "intrinsic value" in call_kwargs["system"]

    @pytest.mark.asyncio
    async def test_history_included_in_api_messages(self, agent, mock_research_repo, mock_llm):
        mock_research_repo.get_messages.return_value = [
            ResearchMessage(id=1, session_id=1, role="user", content="Erste Frage",
                            created_at=datetime.now(timezone.utc)),
            ResearchMessage(id=2, session_id=1, role="assistant", content="Erste Antwort",
                            created_at=datetime.now(timezone.utc)),
        ]
        await agent.chat(1, "Zweite Frage")
        call_kwargs = mock_llm.chat_with_tools.call_args[1]
        msgs = call_kwargs["messages"]
        # History + new user message
        assert any(m["content"] == "Erste Frage" for m in msgs)
        assert any(m["content"] == "Erste Antwort" for m in msgs)
        assert any(m["content"] == "Zweite Frage" for m in msgs)


# ------------------------------------------------------------------
# Tool execution — add_to_watchlist
# ------------------------------------------------------------------

class TestAddToWatchlistTool:
    @pytest.mark.asyncio
    async def test_executes_add_to_watchlist_tool(self, agent, mock_llm, mock_positions_repo):
        tool_call = ClaudeToolCall(
            id="tool_1",
            name="add_to_watchlist",
            input={"ticker": "AAPL", "name": "Apple Inc.", "asset_class": "Aktie", "notes": "Günstig bewertet"},
        )
        mock_llm.chat_with_tools = AsyncMock(side_effect=[
            ClaudeResponse(
                content="",
                tool_calls=[tool_call],
                stop_reason="tool_use",
                raw_blocks=[],
            ),
            ClaudeResponse(
                content="Apple wurde zur Watchlist hinzugefügt.",
                tool_calls=[],
                stop_reason="end_turn",
            ),
        ])
        result = await agent.chat(1, "Füge Apple zur Watchlist hinzu.")
        mock_positions_repo.add.assert_called_once()
        assert "Apple" in result or "Watchlist" in result

    @pytest.mark.asyncio
    async def test_watchlist_entry_has_correct_source(self, agent, mock_llm, mock_positions_repo):
        tool_call = ClaudeToolCall(
            id="tool_1",
            name="add_to_watchlist",
            input={"ticker": "AAPL", "name": "Apple", "asset_class": "Aktie"},
        )
        mock_llm.chat_with_tools = AsyncMock(side_effect=[
            ClaudeResponse(content="", tool_calls=[tool_call], stop_reason="tool_use", raw_blocks=[]),
            ClaudeResponse(content="Fertig.", tool_calls=[], stop_reason="end_turn"),
        ])
        await agent.chat(1, "Watchlist.")
        position = mock_positions_repo.add.call_args[0][0]
        assert position.recommendation_source == "research_agent"
        assert position.strategy == "Value Investing"
        assert position.in_portfolio is False

    @pytest.mark.asyncio
    async def test_llm_called_twice_for_tool_use(self, agent, mock_llm):
        tool_call = ClaudeToolCall(id="t1", name="add_to_watchlist",
                                   input={"ticker": "AAPL", "name": "Apple", "asset_class": "Aktie"})
        mock_llm.chat_with_tools = AsyncMock(side_effect=[
            ClaudeResponse(content="", tool_calls=[tool_call], stop_reason="tool_use", raw_blocks=[]),
            ClaudeResponse(content="Fertig.", tool_calls=[], stop_reason="end_turn"),
        ])
        await agent.chat(1, "Test.")
        assert mock_llm.chat_with_tools.call_count == 2


# ------------------------------------------------------------------
# Session management delegation
# ------------------------------------------------------------------

class TestSessionDelegation:
    def test_list_sessions_delegates(self, agent, mock_research_repo):
        agent.list_sessions(limit=10)
        mock_research_repo.list_sessions.assert_called_once_with(limit=10)

    def test_get_session_delegates(self, agent, mock_research_repo):
        agent.get_session(1)
        mock_research_repo.get_session.assert_called_once_with(1)

    def test_delete_session_delegates(self, agent, mock_research_repo):
        agent.delete_session(1)
        mock_research_repo.delete_session.assert_called_once_with(1)

    def test_get_messages_delegates(self, agent, mock_research_repo):
        agent.get_messages(1)
        mock_research_repo.get_messages.assert_called_once_with(1)
