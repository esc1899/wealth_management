"""
Unit tests for SearchAgent.
LLM and repositories are mocked — no external calls.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.search_agent import CLIENT_TOOL_NAMES, MAX_TOOL_ITERATIONS, SearchAgent
from core.llm.claude import ClaudeResponse, ClaudeToolCall
from core.storage.models import SearchMessage, SearchSession


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def mock_positions_repo():
    repo = MagicMock()
    repo.add.return_value = MagicMock(id=42)
    return repo


@pytest.fixture
def mock_search_repo():
    repo = MagicMock()
    session = SearchSession(
        id=1,
        query="European dividend stocks",
        skill_name="European Stock Screener",
        skill_prompt="Screen for European dividend stocks.",
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
    llm.chat_with_tools = AsyncMock(return_value=ClaudeResponse(
        content="## Top European Dividend Stocks\n1. Nestlé (NESN.SW) — yield 3.1%",
        tool_calls=[],
        stop_reason="end_turn",
    ))
    return llm


@pytest.fixture
def agent(mock_positions_repo, mock_search_repo, mock_llm):
    return SearchAgent(
        positions_repo=mock_positions_repo,
        search_repo=mock_search_repo,
        llm=mock_llm,
    )


# ------------------------------------------------------------------
# start_session
# ------------------------------------------------------------------

class TestStartSession:
    def test_creates_session(self, agent, mock_search_repo):
        agent.start_session("ETFs", "Fund Screener", "Focus on low TER.")
        mock_search_repo.create_session.assert_called_once_with(
            query="ETFs",
            skill_name="Fund Screener",
            skill_prompt="Focus on low TER.",
        )

    def test_returns_session(self, agent):
        session = agent.start_session("ETFs", "Fund Screener", "Low TER.")
        assert session.query == "European dividend stocks"  # from fixture


# ------------------------------------------------------------------
# chat
# ------------------------------------------------------------------

class TestChat:
    @pytest.mark.asyncio
    async def test_saves_user_message(self, agent, mock_search_repo):
        await agent.chat(1, "Find me some ETFs.")
        mock_search_repo.add_message.assert_any_call(1, "user", "Find me some ETFs.")

    @pytest.mark.asyncio
    async def test_saves_assistant_response(self, agent, mock_search_repo, mock_llm):
        mock_llm.chat_with_tools = AsyncMock(return_value=ClaudeResponse(
            content="Here are top ETFs.",
            tool_calls=[],
            stop_reason="end_turn",
        ))
        await agent.chat(1, "Find ETFs.")
        mock_search_repo.add_message.assert_any_call(1, "assistant", "Here are top ETFs.")

    @pytest.mark.asyncio
    async def test_returns_assistant_text_and_proposals(self, agent, mock_llm):
        mock_llm.chat_with_tools = AsyncMock(return_value=ClaudeResponse(
            content="Nestlé is a strong candidate.",
            tool_calls=[],
            stop_reason="end_turn",
        ))
        result, proposals = await agent.chat(1, "Best picks?")
        assert result == "Nestlé is a strong candidate."
        assert proposals == []

    @pytest.mark.asyncio
    async def test_raises_if_session_not_found(self, agent, mock_search_repo):
        mock_search_repo.get_session.return_value = None
        with pytest.raises(ValueError, match="Session 99 not found"):
            await agent.chat(99, "Test")

    @pytest.mark.asyncio
    async def test_calls_llm_with_tools(self, agent, mock_llm):
        await agent.chat(1, "Find stocks.")
        call_kwargs = mock_llm.chat_with_tools.call_args[1]
        tools = call_kwargs["tools"]
        tool_names = [t.get("name") or t.get("type", "") for t in tools]
        assert "propose_for_watchlist" in tool_names
        assert any("web_search" in n for n in tool_names)

    @pytest.mark.asyncio
    async def test_system_prompt_contains_strategy(self, agent, mock_llm):
        await agent.chat(1, "Find stocks.")
        call_kwargs = mock_llm.chat_with_tools.call_args[1]
        assert "Screen for European dividend stocks" in call_kwargs["system"]

    @pytest.mark.asyncio
    async def test_history_included_in_messages(self, agent, mock_search_repo, mock_llm):
        mock_search_repo.get_messages.return_value = [
            SearchMessage(id=1, session_id=1, role="user", content="First question",
                          created_at=datetime.now(timezone.utc)),
            SearchMessage(id=2, session_id=1, role="assistant", content="First answer",
                          created_at=datetime.now(timezone.utc)),
        ]
        await agent.chat(1, "Second question")
        call_kwargs = mock_llm.chat_with_tools.call_args[1]
        msgs = call_kwargs["messages"]
        assert any(m["content"] == "First question" for m in msgs)
        assert any(m["content"] == "First answer" for m in msgs)
        assert any(m["content"] == "Second question" for m in msgs)


# ------------------------------------------------------------------
# Tool execution — propose_for_watchlist
# ------------------------------------------------------------------

class TestProposeForWatchlistTool:
    @pytest.mark.asyncio
    async def test_collects_proposals_during_chat(self, agent, mock_llm):
        tool_call = ClaudeToolCall(
            id="tool_1",
            name="propose_for_watchlist",
            input={"ticker": "NESN.SW", "name": "Nestlé", "asset_class": "Aktie", "notes": "High yield"},
        )
        mock_llm.chat_with_tools = AsyncMock(side_effect=[
            ClaudeResponse(content="", tool_calls=[tool_call], stop_reason="tool_use", raw_blocks=[]),
            ClaudeResponse(content="Proposed Nestlé for review.", tool_calls=[], stop_reason="end_turn"),
        ])
        result, proposals = await agent.chat(1, "Find dividend stocks.")
        assert len(proposals) == 1
        assert proposals[0]["ticker"] == "NESN.SW"
        assert proposals[0]["name"] == "Nestlé"

    @pytest.mark.asyncio
    async def test_add_from_proposal_writes_to_watchlist(self, agent, mock_positions_repo):
        proposal = {
            "ticker": "NESN.SW",
            "name": "Nestlé",
            "asset_class": "Aktie",
            "notes": "High yield",
            "story": "Strong dividend history"
        }
        agent.add_from_proposal(1, proposal)
        mock_positions_repo.add.assert_called_once()
        position = mock_positions_repo.add.call_args[0][0]
        assert position.ticker == "NESN.SW"
        assert position.recommendation_source == "search_agent"
        assert position.in_watchlist is True


# ------------------------------------------------------------------
# Session management delegation
# ------------------------------------------------------------------

class TestSessionDelegation:
    def test_list_sessions_delegates(self, agent, mock_search_repo):
        agent.list_sessions(limit=10)
        mock_search_repo.list_sessions.assert_called_once_with(limit=10)

    def test_get_session_delegates(self, agent, mock_search_repo):
        agent.get_session(1)
        mock_search_repo.get_session.assert_called_once_with(1)

    def test_delete_session_delegates(self, agent, mock_search_repo):
        agent.delete_session(1)
        mock_search_repo.delete_session.assert_called_once_with(1)

    def test_get_messages_delegates(self, agent, mock_search_repo):
        agent.get_messages(1)
        mock_search_repo.get_messages.assert_called_once_with(1)
