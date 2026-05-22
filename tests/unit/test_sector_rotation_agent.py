"""Unit tests for SectorRotationAgent."""

from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.sector_rotation_agent import SectorRotationAgent, VALID_VERDICTS, VALID_MOMENTUM
from core.storage.base import init_db, migrate_db
from core.storage.models import PublicPosition
from core.storage.sector_rotation import SectorRotationRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    init_db(c)
    migrate_db(c)
    return c


@pytest.fixture
def sr_repo(conn):
    return SectorRotationRepository(conn)


def make_llm(tool_calls=None, content="## Sector Report"):
    """Create a mock LLM with given tool calls + final content."""
    end_response = MagicMock()
    end_response.stop_reason = "end_turn"
    end_response.tool_calls = []
    end_response.content = content
    end_response.raw_blocks = content

    if tool_calls:
        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.tool_calls = tool_calls
        tool_response.content = ""
        tool_response.raw_blocks = []
        llm = MagicMock()
        llm.model = "claude-sonnet-4-6"
        llm.chat_with_tools = AsyncMock(side_effect=[tool_response, end_response])
    else:
        llm = MagicMock()
        llm.model = "claude-sonnet-4-6"
        llm.chat_with_tools = AsyncMock(return_value=end_response)

    llm.skill_context = None
    llm.position_count = 0
    return llm


def make_verdict_tool_call(sector: str, verdict: str, momentum: str = "inflow", summary: str = "Test"):
    tc = MagicMock()
    tc.name = "submit_sector_verdict"
    tc.id = f"tc_{sector}"
    tc.input = {"sector": sector, "verdict": verdict, "momentum": momentum, "summary": summary}
    return tc


class TestConstants:
    def test_valid_verdicts(self):
        assert VALID_VERDICTS == {"aligned", "lagging", "overexposed", "rotation_risk"}

    def test_valid_momentum(self):
        assert VALID_MOMENTUM == {"inflow", "neutral", "outflow"}


class TestSectorRotationAgentVerdictCollection:
    @pytest.mark.asyncio
    async def test_verdicts_collected_from_tool_calls(self, sr_repo):
        tc = make_verdict_tool_call("Technology", "aligned", "inflow", "Tech is on fire")
        llm = make_llm(tool_calls=[tc])
        agent = SectorRotationAgent(llm=llm, sr_repo=sr_repo)

        positions = [PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie")]
        run, report, verdicts = await agent.start_scan(positions, "Standard", "prompt", "de")

        assert run.id is not None
        assert len(verdicts) == 1
        assert verdicts[0].sector == "Technology"
        assert verdicts[0].verdict == "aligned"
        assert verdicts[0].momentum == "inflow"
        assert verdicts[0].summary == "Tech is on fire"

    @pytest.mark.asyncio
    async def test_invalid_verdict_skipped(self, sr_repo):
        tc = make_verdict_tool_call("Technology", "invalid_verdict", "inflow", "Bad verdict")
        llm = make_llm(tool_calls=[tc])
        agent = SectorRotationAgent(llm=llm, sr_repo=sr_repo)

        positions = [PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie")]
        run, report, verdicts = await agent.start_scan(positions, "Standard", "prompt", "de")

        assert len(verdicts) == 0

    @pytest.mark.asyncio
    async def test_multiple_verdicts_all_saved(self, sr_repo):
        tc1 = make_verdict_tool_call("Technology", "aligned", "inflow", "Tech strong")
        tc2 = make_verdict_tool_call("Energy", "overexposed", "outflow", "Energy fading")

        end_response = MagicMock()
        end_response.stop_reason = "end_turn"
        end_response.tool_calls = []
        end_response.content = "## Report"
        end_response.raw_blocks = []

        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.tool_calls = [tc1, tc2]
        tool_response.content = ""
        tool_response.raw_blocks = []

        llm = MagicMock()
        llm.model = "claude-sonnet-4-6"
        llm.chat_with_tools = AsyncMock(side_effect=[tool_response, end_response])
        llm.skill_context = None
        llm.position_count = 0

        agent = SectorRotationAgent(llm=llm, sr_repo=sr_repo)
        positions = [PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie")]
        run, report, verdicts = await agent.start_scan(positions, "Standard", "prompt", "de")

        assert len(verdicts) == 2
        sectors = {v.sector for v in verdicts}
        assert sectors == {"Technology", "Energy"}


class TestSectorRotationAgentEdgeCases:
    @pytest.mark.asyncio
    async def test_no_positions_handled(self, sr_repo):
        llm = make_llm(content="No positions to analyze.")
        agent = SectorRotationAgent(llm=llm, sr_repo=sr_repo)

        run, report, verdicts = await agent.start_scan([], "Standard", "prompt", "de")

        assert run.id is not None
        assert report == "No positions to analyze."
        assert verdicts == []

    @pytest.mark.asyncio
    async def test_run_and_messages_persisted(self, sr_repo):
        llm = make_llm(content="## Sector Analysis Report")
        agent = SectorRotationAgent(llm=llm, sr_repo=sr_repo)

        positions = [PublicPosition(id=1, name="Apple", ticker="AAPL", asset_class="Aktie")]
        run, report, verdicts = await agent.start_scan(positions, "MySkill", "prompt", "de")

        # Run persisted
        fetched = sr_repo.get_run(run.id)
        assert fetched is not None
        assert fetched.skill_name == "MySkill"
        assert fetched.result == "## Sector Analysis Report"

        # Messages persisted (user + assistant)
        messages = sr_repo.get_messages(run.id)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    @pytest.mark.asyncio
    async def test_invalid_momentum_normalized(self, sr_repo):
        tc = make_verdict_tool_call("Healthcare", "lagging", "invalid_momentum", "Healthcare slow")
        llm = make_llm(tool_calls=[tc])
        agent = SectorRotationAgent(llm=llm, sr_repo=sr_repo)

        positions = [PublicPosition(id=1, name="JNJ", ticker="JNJ", asset_class="Aktie")]
        run, report, verdicts = await agent.start_scan(positions, "Standard", "prompt", "de")

        # Invalid momentum should be normalized to "neutral"
        assert len(verdicts) == 1
        assert verdicts[0].momentum == "neutral"

    def test_model_property(self, sr_repo):
        llm = MagicMock()
        llm.model = "claude-sonnet-4-6"
        agent = SectorRotationAgent(llm=llm, sr_repo=sr_repo)
        assert agent.model == "claude-sonnet-4-6"

    def test_positions_context_without_ticker(self, sr_repo):
        llm = MagicMock()
        agent = SectorRotationAgent(llm=llm, sr_repo=sr_repo)
        positions = [PublicPosition(id=1, name="No Ticker Fund", asset_class="Aktienfonds")]
        context = agent._build_positions_context(positions)
        assert "No Ticker Fund" in context
        assert "Aktienfonds" in context

    def test_empty_positions_context(self, sr_repo):
        llm = MagicMock()
        agent = SectorRotationAgent(llm=llm, sr_repo=sr_repo)
        context = agent._build_positions_context([])
        assert "No portfolio positions" in context
