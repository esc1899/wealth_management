"""Unit tests for CapitalAllocatorAgent."""

from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.capital_allocator_agent import CapitalAllocatorAgent, VALID_VERDICTS
from core.storage.analyses import PositionAnalysesRepository
from core.storage.base import init_db, migrate_db
from core.storage.capital_allocator import CapitalAllocatorRepository
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
    return CapitalAllocatorRepository(conn), PositionAnalysesRepository(conn)


def make_llm(verdict="solide", summary="Solid capital allocation."):
    """Create a mock LLM that returns a single submit_ca_verdict tool call."""
    tool_call = MagicMock()
    tool_call.name = "submit_ca_verdict"
    tool_call.input = {
        "position_id": 1,
        "verdict": verdict,
        "summary": summary,
        "analysis": "Detailed analysis here.",
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
        assert VALID_VERDICTS == {"exzellent", "solide", "fragwürdig", "destruktiv"}


class TestCapitalAllocatorAgentEligibility:
    def test_positions_without_ticker_skipped(self, repos):
        ca_repo, analyses_repo = repos
        llm = make_llm()
        agent = CapitalAllocatorAgent(llm=llm, analyses_repo=analyses_repo, ca_repo=ca_repo)

        positions = [
            PublicPosition(id=1, name="No Ticker Fund", asset_class="Aktienfonds"),
        ]

        import asyncio
        results = asyncio.run(
            agent.analyze_portfolio(positions, "Standard", "", "de")
        )

        assert results == []
        llm.chat_with_tools.assert_not_called()

    def test_positions_without_id_skipped(self, repos):
        ca_repo, analyses_repo = repos
        llm = make_llm()
        agent = CapitalAllocatorAgent(llm=llm, analyses_repo=analyses_repo, ca_repo=ca_repo)

        positions = [
            PublicPosition(id=None, name="No ID", ticker="XYZ", asset_class="Aktie"),
        ]

        import asyncio
        results = asyncio.run(
            agent.analyze_portfolio(positions, "Standard", "", "de")
        )

        assert results == []
        llm.chat_with_tools.assert_not_called()

    def test_story_not_required(self, repos):
        """Unlike ConsensusGapAgent, story is NOT required for eligibility."""
        ca_repo, analyses_repo = repos
        llm = make_llm()
        agent = CapitalAllocatorAgent(llm=llm, analyses_repo=analyses_repo, ca_repo=ca_repo)

        positions = [
            PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie", story=None),
        ]

        import asyncio
        results = asyncio.run(
            agent.analyze_portfolio(positions, "Standard", "", "de")
        )

        assert len(results) == 1
        llm.chat_with_tools.assert_called_once()


class TestCapitalAllocatorAgentAnalysis:
    def test_analyze_stores_verdict(self, repos):
        ca_repo, analyses_repo = repos
        llm = make_llm(verdict="exzellent", summary="Excellent buybacks below fair value.")
        agent = CapitalAllocatorAgent(llm=llm, analyses_repo=analyses_repo, ca_repo=ca_repo)

        positions = [
            PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie"),
        ]

        import asyncio
        results = asyncio.run(
            agent.analyze_portfolio(positions, "Standard", "", "de")
        )

        assert len(results) == 1
        pos_id, verdict, summary = results[0]
        assert pos_id == 1
        assert verdict == "exzellent"
        assert "buybacks" in summary.lower()

        # Verdict persisted in position_analyses
        stored = analyses_repo.get_latest_bulk([1], "capital_allocator")
        assert 1 in stored
        assert stored[1].verdict == "exzellent"

    def test_analyze_creates_session(self, repos):
        ca_repo, analyses_repo = repos
        llm = make_llm()
        agent = CapitalAllocatorAgent(llm=llm, analyses_repo=analyses_repo, ca_repo=ca_repo)

        positions = [PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie")]

        import asyncio
        asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))

        sessions = ca_repo.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].ticker == "AAPL"

    def test_invalid_verdict_ignored(self, repos):
        ca_repo, analyses_repo = repos

        tool_call = MagicMock()
        tool_call.name = "submit_ca_verdict"
        tool_call.input = {"position_id": 1, "verdict": "unknown_verdict", "summary": "Test"}

        response = MagicMock()
        response.tool_calls = [tool_call]
        response.content = ""

        llm = MagicMock()
        llm.model = "test"
        llm.chat_with_tools = AsyncMock(return_value=response)

        agent = CapitalAllocatorAgent(llm=llm, analyses_repo=analyses_repo, ca_repo=ca_repo)
        positions = [PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie")]

        import asyncio
        results = asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))

        assert results == []

    def test_llm_error_returns_empty(self, repos):
        ca_repo, analyses_repo = repos

        llm = MagicMock()
        llm.model = "test"
        llm.chat_with_tools = AsyncMock(side_effect=Exception("API error"))

        agent = CapitalAllocatorAgent(llm=llm, analyses_repo=analyses_repo, ca_repo=ca_repo)
        positions = [PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie")]

        import asyncio
        results = asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))

        assert results == []

    def test_all_valid_verdicts_accepted(self, repos):
        for v in ["exzellent", "solide", "fragwürdig", "destruktiv"]:
            ca_repo, analyses_repo = repos
            llm = make_llm(verdict=v, summary=f"Test {v}")
            agent = CapitalAllocatorAgent(llm=llm, analyses_repo=analyses_repo, ca_repo=ca_repo)
            positions = [PublicPosition(id=1, name="Test", ticker="TST", asset_class="Aktie")]

            import asyncio
            results = asyncio.run(agent.analyze_portfolio(positions, "Standard", "", "de"))
            assert len(results) == 1
            assert results[0][1] == v
