"""
Unit tests for ConsensusGapAgent — Tool-call based verdict extraction.

The agent now uses Claude's tool-calling mechanism to extract verdicts,
rather than parsing free-form text. This is deterministic and robust.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock
import pytest

from agents.consensus_gap_agent import ConsensusGapAgent
from core.llm.claude import ClaudeResponse, ClaudeToolCall
from core.storage.models import Position


def make_agent():
    """Create agent with mocked LLM."""
    llm = MagicMock()
    return ConsensusGapAgent(llm=llm)


def make_test_position(pos_id: int, name: str, story: str = "Test thesis") -> Position:
    """Create a test position with a story."""
    return Position(
        id=pos_id,
        name=name,
        ticker="TEST",
        asset_class="Equity",
        investment_type="stock",
        story=story,
        quantity=10,
        unit="Shares",
        purchase_price=100,
        purchase_date=None,
        added_date=date.today(),
        in_portfolio=False,
        in_watchlist=False,
        rebalance_excluded=False,
    )


@pytest.mark.asyncio
async def test_single_verdict_extraction():
    """Agent extracts a single position verdict from tool call."""
    agent = make_agent()

    tool_call = ClaudeToolCall(
        id="call_1",
        name="submit_consensus_verdict",
        input={
            "position_id": 42,
            "verdict": "wächst",
            "summary": "Market still wrong.",
            "analysis": "Target lags fundamentals.",
        },
    )

    agent._llm.chat_with_tools = AsyncMock(
        return_value=ClaudeResponse(
            content="",
            tool_calls=[tool_call],
            stop_reason="tool_use",
        )
    )

    analyses_repo = MagicMock()

    positions = [make_test_position(42, "Apple")]
    results = await agent.analyze_portfolio(
        positions=positions,
        skill_name="test_skill",
        skill_prompt="Test prompt",
        analyses_repo=analyses_repo,
    )

    assert len(results) == 1
    pos_id, verdict, summary = results[0]
    assert pos_id == 42
    assert verdict == "wächst"
    assert summary == "Market still wrong."

    # Verify verdict was persisted
    analyses_repo.save.assert_called_once()
    call_kwargs = analyses_repo.save.call_args[1]
    assert call_kwargs["position_id"] == 42
    assert call_kwargs["verdict"] == "wächst"


@pytest.mark.asyncio
async def test_multiple_verdicts_in_batch():
    """Agent extracts multiple verdicts from a single batch."""
    agent = make_agent()

    tool_calls = [
        ClaudeToolCall(
            id="call_1",
            name="submit_consensus_verdict",
            input={
                "position_id": 1,
                "verdict": "wächst",
                "summary": "Gap growing.",
                "analysis": "Market wrong.",
            },
        ),
        ClaudeToolCall(
            id="call_2",
            name="submit_consensus_verdict",
            input={
                "position_id": 2,
                "verdict": "eingeholt",
                "summary": "Gap closed.",
                "analysis": "Consensus caught up.",
            },
        ),
    ]

    agent._llm.chat_with_tools = AsyncMock(
        return_value=ClaudeResponse(
            content="",
            tool_calls=tool_calls,
            stop_reason="tool_use",
        )
    )

    analyses_repo = MagicMock()
    positions = [
        make_test_position(1, "Apple"),
        make_test_position(2, "Microsoft"),
    ]

    results = await agent.analyze_portfolio(
        positions=positions,
        skill_name="test",
        skill_prompt="prompt",
        analyses_repo=analyses_repo,
    )

    assert len(results) == 2
    assert {r[1] for r in results} == {"wächst", "eingeholt"}
    assert analyses_repo.save.call_count == 2


@pytest.mark.asyncio
async def test_no_verdicts_logged():
    """When no tool calls are returned, warning is logged."""
    agent = make_agent()

    agent._llm.chat_with_tools = AsyncMock(
        return_value=ClaudeResponse(
            content="Some text without tool calls.",
            tool_calls=[],
            stop_reason="end_turn",
        )
    )

    analyses_repo = MagicMock()
    positions = [make_test_position(1, "Apple")]

    results = await agent.analyze_portfolio(
        positions=positions,
        skill_name="test",
        skill_prompt="prompt",
        analyses_repo=analyses_repo,
    )

    assert len(results) == 0
    analyses_repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_verdict_filtered():
    """Tool calls with invalid verdicts are filtered out."""
    agent = make_agent()

    tool_call = ClaudeToolCall(
        id="call_1",
        name="submit_consensus_verdict",
        input={
            "position_id": 1,
            "verdict": "bullish",  # Invalid!
            "summary": "Not a valid verdict.",
            "analysis": "N/A",
        },
    )

    agent._llm.chat_with_tools = AsyncMock(
        return_value=ClaudeResponse(
            content="",
            tool_calls=[tool_call],
            stop_reason="tool_use",
        )
    )

    analyses_repo = MagicMock()
    positions = [make_test_position(1, "Apple")]

    results = await agent.analyze_portfolio(
        positions=positions,
        skill_name="test",
        skill_prompt="prompt",
        analyses_repo=analyses_repo,
    )

    assert len(results) == 0
    analyses_repo.save.assert_not_called()


@pytest.mark.asyncio
async def test_mixed_valid_and_invalid():
    """Valid and invalid verdicts are separated."""
    agent = make_agent()

    tool_calls = [
        ClaudeToolCall(
            id="call_1",
            name="submit_consensus_verdict",
            input={
                "position_id": 1,
                "verdict": "wächst",
                "summary": "Valid.",
                "analysis": "OK.",
            },
        ),
        ClaudeToolCall(
            id="call_2",
            name="submit_consensus_verdict",
            input={
                "position_id": 2,
                "verdict": "invalid",  # Invalid!
                "summary": "Invalid verdict.",
                "analysis": "Dropped.",
            },
        ),
    ]

    agent._llm.chat_with_tools = AsyncMock(
        return_value=ClaudeResponse(
            content="",
            tool_calls=tool_calls,
            stop_reason="tool_use",
        )
    )

    analyses_repo = MagicMock()
    positions = [
        make_test_position(1, "A"),
        make_test_position(2, "B"),
    ]

    results = await agent.analyze_portfolio(
        positions=positions,
        skill_name="test",
        skill_prompt="prompt",
        analyses_repo=analyses_repo,
    )

    assert len(results) == 1
    pos_ids = {r[0] for r in results}
    assert pos_ids == {1}
    assert analyses_repo.save.call_count == 1


@pytest.mark.asyncio
async def test_all_valid_verdicts_accepted():
    """All four valid verdicts are accepted."""
    agent = make_agent()

    verdicts = ["wächst", "stabil", "schließt", "eingeholt"]
    for i, verdict in enumerate(verdicts, 1):
        tool_call = ClaudeToolCall(
            id=f"call_{i}",
            name="submit_consensus_verdict",
            input={
                "position_id": i,
                "verdict": verdict,
                "summary": f"Summary for {verdict}.",
                "analysis": "Analysis.",
            },
        )

        agent._llm.chat_with_tools = AsyncMock(
            return_value=ClaudeResponse(
                content="",
                tool_calls=[tool_call],
                stop_reason="tool_use",
            )
        )

        analyses_repo = MagicMock()
        positions = [make_test_position(i, f"Stock{i}")]

        results = await agent.analyze_portfolio(
            positions=positions,
            skill_name="test",
            skill_prompt="prompt",
            analyses_repo=analyses_repo,
        )

        assert len(results) == 1
        assert results[0][1] == verdict, f"Failed for verdict: {verdict}"


@pytest.mark.asyncio
async def test_positions_without_story_skipped():
    """Positions without a story are not analyzed."""
    agent = make_agent()

    analyses_repo = MagicMock()

    # Position without story
    pos_no_story = Position(
        id=1,
        name="NoStory",
        ticker="TEST",
        asset_class="Equity",
        investment_type="stock",
        story=None,  # No story
        quantity=10,
        unit="Shares",
        purchase_price=100,
        purchase_date=None,
        added_date=date.today(),
        in_portfolio=False,
        in_watchlist=False,
        rebalance_excluded=False,
    )

    results = await agent.analyze_portfolio(
        positions=[pos_no_story],
        skill_name="test",
        skill_prompt="prompt",
        analyses_repo=analyses_repo,
    )

    assert len(results) == 0
    agent._llm.chat_with_tools.assert_not_called()


@pytest.mark.asyncio
async def test_non_tool_calls_ignored():
    """Tool calls for other tools are ignored (e.g., web_search)."""
    agent = make_agent()

    # Only the submit_consensus_verdict call matters
    tool_calls = [
        ClaudeToolCall(
            id="web_1",
            name="web_search",  # Not our verdict tool
            input={"query": "Something"},
        ),
        ClaudeToolCall(
            id="verdict_1",
            name="submit_consensus_verdict",
            input={
                "position_id": 1,
                "verdict": "wächst",
                "summary": "Valid.",
                "analysis": "OK.",
            },
        ),
    ]

    agent._llm.chat_with_tools = AsyncMock(
        return_value=ClaudeResponse(
            content="",
            tool_calls=tool_calls,
            stop_reason="tool_use",
        )
    )

    analyses_repo = MagicMock()
    positions = [make_test_position(1, "Apple")]

    results = await agent.analyze_portfolio(
        positions=positions,
        skill_name="test",
        skill_prompt="prompt",
        analyses_repo=analyses_repo,
    )

    # Only the verdict tool call is processed
    assert len(results) == 1
    assert results[0][0] == 1
    assert analyses_repo.save.call_count == 1
