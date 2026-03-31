"""
Unit tests for NewsAgent.
LLM is mocked — no external calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.news_agent import NewsAgent
from core.llm.claude import ClaudeResponse


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.chat_with_tools = AsyncMock(return_value=ClaudeResponse(
        content="## AAPL — Apple Inc.\n- Reported strong Q4 earnings\n**Assessment:** 🟢 No action needed",
        tool_calls=[],
        stop_reason="end_turn",
    ))
    return llm


@pytest.fixture
def agent(mock_llm):
    return NewsAgent(llm=mock_llm)


# ------------------------------------------------------------------
# _run_digest (core digest logic, no DB)
# ------------------------------------------------------------------

class TestRunDigest:
    @pytest.mark.asyncio
    async def test_returns_content(self, agent, mock_llm):
        result = await agent._run_digest(
            tickers=["AAPL"], ticker_names={"AAPL": "Apple Inc."},
            skill_name="", skill_prompt="",
        )
        assert "AAPL" in result

    @pytest.mark.asyncio
    async def test_empty_tickers_returns_message(self, agent):
        result = await agent._run_digest(
            tickers=[], ticker_names={}, skill_name="", skill_prompt="",
        )
        assert "empty" in result.lower() or "no positions" in result.lower()

    @pytest.mark.asyncio
    async def test_calls_llm_with_web_search_tool(self, agent, mock_llm):
        await agent._run_digest(
            tickers=["AAPL"], ticker_names={}, skill_name="", skill_prompt="",
        )
        call_kwargs = mock_llm.chat_with_tools.call_args[1]
        tool_types = [t.get("type", "") for t in call_kwargs["tools"]]
        assert any("web_search" in t for t in tool_types)

    @pytest.mark.asyncio
    async def test_skill_prompt_included_in_system(self, agent, mock_llm):
        await agent._run_digest(
            tickers=["AAPL"],
            ticker_names={},
            skill_name="Long-term Investor",
            skill_prompt="Ignore noise, focus on fundamentals.",
        )
        call_kwargs = mock_llm.chat_with_tools.call_args[1]
        assert "Ignore noise" in call_kwargs["system"]

    @pytest.mark.asyncio
    async def test_ticker_names_included_in_user_message(self, agent, mock_llm):
        await agent._run_digest(
            tickers=["SAP.DE"],
            ticker_names={"SAP.DE": "SAP SE"},
            skill_name="", skill_prompt="",
        )
        call_kwargs = mock_llm.chat_with_tools.call_args[1]
        msgs = call_kwargs["messages"]
        user_content = next(m["content"] for m in msgs if m["role"] == "user")
        assert "SAP SE" in user_content

    @pytest.mark.asyncio
    async def test_fallback_when_no_content(self, agent, mock_llm):
        mock_llm.chat_with_tools = AsyncMock(return_value=ClaudeResponse(
            content="", tool_calls=[], stop_reason="end_turn"
        ))
        result = await agent._run_digest(
            tickers=["AAPL"], ticker_names={}, skill_name="", skill_prompt="",
        )
        assert result  # should not be empty string
