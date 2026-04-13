"""Tests for WatchlistCheckerAgent — parsing and data flow."""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from agents.watchlist_checker_agent import (
    WatchlistFit,
    WatchlistCheckResult,
    WatchlistCheckerAgent,
    _parse_watchlist_results,
)
from core.storage.models import Position


def make_position(**kwargs):
    """Helper to create Position with all required fields."""
    defaults = {
        "id": 1,
        "asset_class": "Aktie",
        "investment_type": "Stock",
        "name": "Test",
        "ticker": "TST",
        "unit": "EUR",
        "added_date": date.today(),
        "in_portfolio": False,
        "in_watchlist": True,
    }
    defaults.update(kwargs)
    return Position(**defaults)


class TestParseWatchlistResults:
    """Test parsing of LLM responses into structured verdicts."""

    def test_parse_single_position(self):
        """Parse single position with verdict."""
        positions = [
            make_position(
                id=1,
                name="Apple",
                ticker="AAPL",
            )
        ]

        response = """## Apple (AAPL)
**Fit:** 🟢 Sehr passend

> Füllt Lücke im Tech-Portfolio

Gute Fundamentals und passt zur Story."""

        fits = _parse_watchlist_results(positions, response)

        assert len(fits) == 1
        assert fits[0].position_id == 1
        assert fits[0].verdict == "sehr_passend"
        assert "Lücke" in fits[0].summary

    def test_parse_multiple_positions(self):
        """Parse multiple positions."""
        positions = [
            make_position(id=1, name="Apple", ticker="AAPL"),
            make_position(id=2, asset_class="Anleihe", name="German Bund", ticker="BU100"),
        ]

        response = """## Apple (AAPL)
**Fit:** 🟢 Sehr passend

> Tech exposure needed

Details here.

---

## German Bund (BU100)
**Fit:** 🟡 Passend

> Stabilisierung des Portfolios

Aber nicht dringend."""

        fits = _parse_watchlist_results(positions, response)

        assert len(fits) == 2
        assert fits[0].position_id == 1
        assert fits[0].verdict == "sehr_passend"
        assert fits[1].position_id == 2
        assert fits[1].verdict == "passend"

    def test_parse_all_verdicts(self):
        """Parse all four verdict types."""
        positions = [
            make_position(id=i, name=f"Stock{i}", ticker=f"STK{i}")
            for i in range(1, 5)
        ]

        response = """## Stock1 (STK1)
**Fit:** 🟢 Sehr passend
> Very good

## Stock2 (STK2)
**Fit:** 🟡 Passend
> OK

## Stock3 (STK3)
**Fit:** ⚪ Neutral
> Neither good nor bad

## Stock4 (STK4)
**Fit:** 🔴 Nicht passend
> Doesn't fit"""

        fits = _parse_watchlist_results(positions, response)

        assert len(fits) == 4
        verdicts = [f.verdict for f in fits]
        assert "sehr_passend" in verdicts
        assert "passend" in verdicts
        assert "neutral" in verdicts
        assert "nicht_passend" in verdicts

    def test_parse_empty_response(self):
        """Parse empty response returns empty list."""
        positions = [make_position()]

        fits = _parse_watchlist_results(positions, "")
        assert fits == []

    def test_parse_no_matching_positions(self):
        """Parse response with no matching position headers."""
        positions = [make_position(name="Apple", ticker="AAPL")]

        response = """## Unknown Stock (UNK)
**Fit:** 🟢 Sehr passend
> Some text"""

        fits = _parse_watchlist_results(positions, response)
        # Position not in lookup, so no match
        assert len(fits) == 0


class TestWatchlistCheckerAgent:
    """Test WatchlistCheckerAgent behavior and integration."""

    @pytest.mark.asyncio
    async def test_empty_watchlist(self):
        """Agent handles empty watchlist gracefully."""
        mock_llm = AsyncMock()
        mock_analyses_repo = MagicMock()

        agent = WatchlistCheckerAgent(
            positions_repo=MagicMock(),
            analyses_repo=mock_analyses_repo,
            llm=mock_llm,
        )

        result = await agent.check_watchlist(
            portfolio_snapshot="Test portfolio",
            watchlist_positions=[],
        )

        # Should return empty result without calling LLM
        assert result.position_fits == []
        assert "Keine Watchlist-Positionen" in result.full_text
        mock_llm.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_agent_calls_llm_with_context(self):
        """Agent builds context and calls LLM."""
        positions = [
            make_position(id=1, name="Tesla", ticker="TSLA"),
            make_position(id=2, name="Microsoft", ticker="MSFT"),
        ]

        mock_llm = AsyncMock()
        mock_llm.model = "test-model"
        mock_llm.chat = AsyncMock(return_value="""## Tesla (TSLA)
**Fit:** 🟢 Sehr passend
> Good fit

## Microsoft (MSFT)
**Fit:** 🟡 Passend
> Okay fit""")

        mock_analyses_repo = MagicMock()
        mock_analyses_repo.get_latest_bulk.return_value = {}

        agent = WatchlistCheckerAgent(
            positions_repo=MagicMock(),
            analyses_repo=mock_analyses_repo,
            llm=mock_llm,
        )

        await agent.check_watchlist(
            portfolio_snapshot="Portfolio with 5 positions",
            watchlist_positions=positions,
        )

        # Verify LLM was called
        mock_llm.chat.assert_called_once()
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        content = messages[0].content

        # Context should include portfolio snapshot
        assert "Portfolio with 5 positions" in content
        # And watchlist positions
        assert "Tesla" in content
        assert "TSLA" in content

    @pytest.mark.asyncio
    async def test_agent_persists_results(self):
        """Agent saves parsing results to repository."""
        positions = [
            make_position(id=1, name="Apple", ticker="AAPL"),
        ]

        mock_llm = AsyncMock()
        mock_llm.model = "test-model"
        mock_llm.chat = AsyncMock(return_value="""## Apple (AAPL)
**Fit:** 🟢 Sehr passend
> Good fit""")

        mock_analyses_repo = MagicMock()
        mock_analyses_repo.get_latest_bulk.return_value = {}

        agent = WatchlistCheckerAgent(
            positions_repo=MagicMock(),
            analyses_repo=mock_analyses_repo,
            llm=mock_llm,
        )

        result = await agent.check_watchlist(
            portfolio_snapshot="Test portfolio",
            watchlist_positions=positions,
        )

        # Verify results were saved
        assert len(result.position_fits) == 1
        mock_analyses_repo.save.assert_called_once()
        save_call = mock_analyses_repo.save.call_args
        assert save_call[1]["position_id"] == 1
        assert save_call[1]["agent"] == "watchlist_checker"
        assert save_call[1]["verdict"] == "sehr_passend"

    @pytest.mark.asyncio
    async def test_agent_with_existing_verdicts(self):
        """Agent includes existing verdicts in context."""
        positions = [
            make_position(id=1, name="Apple", ticker="AAPL"),
        ]

        mock_llm = AsyncMock()
        mock_llm.model = "test-model"
        mock_llm.chat = AsyncMock(return_value="""## Apple (AAPL)
**Fit:** 🟢 Sehr passend
> Good fit""")

        mock_analyses_repo = MagicMock()
        # Simulate existing storychecker verdict
        mock_analyses_repo.get_latest_bulk.return_value = {
            1: MagicMock(agent="storychecker", verdict="intact", summary="Good")
        }

        agent = WatchlistCheckerAgent(
            positions_repo=MagicMock(),
            analyses_repo=mock_analyses_repo,
            llm=mock_llm,
        )

        await agent.check_watchlist(
            portfolio_snapshot="Test portfolio",
            watchlist_positions=positions,
        )

        # Verify context included existing verdicts
        call_args = mock_llm.chat.call_args
        content = call_args[0][0][0].content
        # Should mention storychecker results
        assert "Storychecker" in content or "storychecker" in content.lower()

    @pytest.mark.asyncio
    async def test_model_property(self):
        """Agent exposes model name via property."""
        mock_llm = AsyncMock()
        mock_llm.model = "test-model-123"

        agent = WatchlistCheckerAgent(
            positions_repo=MagicMock(),
            analyses_repo=MagicMock(),
            llm=mock_llm,
        )

        assert agent.model == "test-model-123"
