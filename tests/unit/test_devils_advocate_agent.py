"""Unit tests for DevilsAdvocateAgent."""

from __future__ import annotations

import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.devils_advocate_agent import DevilsAdvocateAgent, VALID_VERDICTS
from core.storage.analyses import PositionAnalysesRepository
from core.storage.base import init_db, migrate_db
from core.storage.devils_advocate import DevilsAdvocateRepository
from core.storage.models import PublicPosition


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    init_db(c)
    migrate_db(c)
    return c


@pytest.fixture
def repos(conn):
    return DevilsAdvocateRepository(conn), PositionAnalysesRepository(conn)


def make_llm(verdict="angreifbar", summary="Notable risks identified."):
    """Create a mock LLM that returns a single submit_da_verdict tool call."""
    tool_call = MagicMock()
    tool_call.name = "submit_da_verdict"
    tool_call.input = {
        "position_id": 1,
        "verdict": verdict,
        "summary": summary,
        "analysis": "Detailed bear case analysis here.",
    }

    response = MagicMock()
    response.tool_calls = [tool_call]
    response.content = ""

    llm = MagicMock()
    llm.model = "claude-sonnet-4-6"
    llm.chat_with_tools = AsyncMock(return_value=response)
    return llm


class TestValidVerdicts:
    def test_valid_verdict_set(self):
        assert VALID_VERDICTS == {"robust", "angreifbar", "fragil", "kritisch"}


class TestDevilsAdvocateAgentEligibility:
    def test_positions_without_ticker_skipped(self, repos):
        da_repo, analyses_repo = repos
        llm = make_llm()
        agent = DevilsAdvocateAgent(llm=llm, analyses_repo=analyses_repo, da_repo=da_repo)

        positions = [
            PublicPosition(id=1, name="No Ticker Fund", asset_class="Aktienfonds"),
        ]

        results = asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))

        assert results == []
        llm.chat_with_tools.assert_not_called()

    def test_positions_without_id_skipped(self, repos):
        da_repo, analyses_repo = repos
        llm = make_llm()
        agent = DevilsAdvocateAgent(llm=llm, analyses_repo=analyses_repo, da_repo=da_repo)

        positions = [
            PublicPosition(id=None, name="No ID", ticker="XYZ", asset_class="Aktie"),
        ]

        results = asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))

        assert results == []
        llm.chat_with_tools.assert_not_called()

    def test_story_not_required(self, repos):
        """Story is NOT required for eligibility — agent runs without it."""
        da_repo, analyses_repo = repos
        llm = make_llm()
        agent = DevilsAdvocateAgent(llm=llm, analyses_repo=analyses_repo, da_repo=da_repo)

        positions = [
            PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie", story=None),
        ]

        results = asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))

        assert len(results) == 1
        llm.chat_with_tools.assert_called_once()

    def test_story_included_in_prompt_when_present(self, repos):
        """When a story is present it should be included in the user message."""
        da_repo, analyses_repo = repos
        llm = make_llm()
        agent = DevilsAdvocateAgent(llm=llm, analyses_repo=analyses_repo, da_repo=da_repo)

        positions = [
            PublicPosition(
                id=1,
                name="Apple",
                ticker="AAPL",
                asset_class="Aktie",
                story="Langfristig starke Marke mit hohem Free Cashflow.",
            ),
        ]

        asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))

        call_args = llm.chat_with_tools.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_content = messages[0]["content"]
        assert "Investment-These" in user_content
        assert "Langfristig starke Marke" in user_content


class TestDevilsAdvocateAgentAnalysis:
    def test_analyze_stores_verdict(self, repos):
        da_repo, analyses_repo = repos
        llm = make_llm(verdict="fragil", summary="Multiple structural risks found.")
        agent = DevilsAdvocateAgent(llm=llm, analyses_repo=analyses_repo, da_repo=da_repo)

        positions = [
            PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie"),
        ]

        results = asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))

        assert len(results) == 1
        pos_id, verdict, summary = results[0]
        assert pos_id == 1
        assert verdict == "fragil"
        assert "structural" in summary.lower()

        # Verdict persisted in position_analyses
        stored = analyses_repo.get_latest_bulk([1], "devils_advocate")
        assert 1 in stored
        assert stored[1].verdict == "fragil"

    def test_analyze_creates_session(self, repos):
        da_repo, analyses_repo = repos
        llm = make_llm()
        agent = DevilsAdvocateAgent(llm=llm, analyses_repo=analyses_repo, da_repo=da_repo)

        positions = [PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie")]

        asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))

        sessions = da_repo.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].ticker == "AAPL"

    def test_invalid_verdict_ignored(self, repos):
        da_repo, analyses_repo = repos

        tool_call = MagicMock()
        tool_call.name = "submit_da_verdict"
        tool_call.input = {"position_id": 1, "verdict": "unknown_verdict", "summary": "Test"}

        response = MagicMock()
        response.tool_calls = [tool_call]
        response.content = ""

        llm = MagicMock()
        llm.model = "test"
        llm.chat_with_tools = AsyncMock(return_value=response)

        agent = DevilsAdvocateAgent(llm=llm, analyses_repo=analyses_repo, da_repo=da_repo)
        positions = [PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie")]

        results = asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))

        assert results == []

    def test_llm_error_returns_empty(self, repos):
        da_repo, analyses_repo = repos

        llm = MagicMock()
        llm.model = "test"
        llm.chat_with_tools = AsyncMock(side_effect=Exception("API error"))

        agent = DevilsAdvocateAgent(llm=llm, analyses_repo=analyses_repo, da_repo=da_repo)
        positions = [PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie")]

        results = asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))

        assert results == []

    def test_all_valid_verdicts_accepted(self, repos):
        for v in ["robust", "angreifbar", "fragil", "kritisch"]:
            da_repo, analyses_repo = repos
            llm = make_llm(verdict=v, summary=f"Test {v}")
            agent = DevilsAdvocateAgent(llm=llm, analyses_repo=analyses_repo, da_repo=da_repo)
            positions = [PublicPosition(id=1, name="Test", ticker="TST", asset_class="Aktie")]

            results = asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))
            assert len(results) == 1
            assert results[0][1] == v

    def test_no_tool_call_returns_empty(self, repos):
        """If LLM doesn't call submit_da_verdict, returns empty."""
        da_repo, analyses_repo = repos

        response = MagicMock()
        response.tool_calls = []
        response.content = "I found some risks but couldn't format the verdict."

        llm = MagicMock()
        llm.model = "test"
        llm.chat_with_tools = AsyncMock(return_value=response)

        agent = DevilsAdvocateAgent(llm=llm, analyses_repo=analyses_repo, da_repo=da_repo)
        positions = [PublicPosition(id=1, name="Test", ticker="TST", asset_class="Aktie")]

        results = asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))
        assert results == []
