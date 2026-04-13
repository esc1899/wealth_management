"""Unit tests for InvestmentCompassAgent — context building and lineage tracking."""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from agents.investment_compass_agent import InvestmentCompassAgent, _build_portfolio_snapshot, _build_watchlist_summary
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
        "in_portfolio": True,
        "in_watchlist": False,
    }
    defaults.update(kwargs)
    return Position(**defaults)


class TestPortfolioSnapshot:
    """Test portfolio snapshot building."""

    def test_empty_portfolio(self):
        """Empty portfolio returns (Leer)."""
        result = _build_portfolio_snapshot([], None)
        assert result == "(Leer)"

    def test_single_position_portfolio(self):
        """Single position shows name and ticker."""
        positions = [
            make_position(
                id=1,
                asset_class="Aktie",
                name="Apple",
                ticker="AAPL",
                quantity=10,
            )
        ]
        result = _build_portfolio_snapshot(positions, None)

        assert "Aktie" in result
        assert "Apple" in result
        assert "AAPL" in result
        assert "10" in result

    def test_grouped_by_asset_class(self):
        """Positions grouped by asset_class."""
        positions = [
            make_position(id=1, asset_class="Aktie", name="Apple", ticker="AAPL"),
            make_position(id=2, asset_class="Aktie", name="Microsoft", ticker="MSFT"),
            make_position(id=3, asset_class="Anleihe", name="Bund", ticker="BU100", in_portfolio=True),
        ]
        result = _build_portfolio_snapshot(positions, None)

        # Should have separate sections
        assert "### Aktie" in result
        assert "### Anleihe" in result
        assert "Apple" in result
        assert "Bund" in result

    def test_watchlist_excluded(self):
        """Only portfolio positions shown, not watchlist."""
        positions = [
            make_position(id=1, name="AAPL", ticker="AAPL", in_portfolio=True),
            make_position(id=2, name="MSFT", ticker="MSFT", in_portfolio=False, in_watchlist=True),
        ]
        result = _build_portfolio_snapshot(positions, None)

        assert "AAPL" in result
        assert "MSFT" not in result  # Watchlist excluded


class TestWatchlistSummary:
    """Test watchlist summary building."""

    def test_empty_watchlist(self):
        """Empty watchlist returns (Leer)."""
        result = _build_watchlist_summary([])
        assert result == "(Leer)"

    def test_single_watchlist_position(self):
        """Single watchlist position shows."""
        positions = [
            make_position(id=1, asset_class="Aktie", name="Tesla", ticker="TSLA", in_watchlist=True)
        ]
        result = _build_watchlist_summary(positions)

        assert "Tesla" in result
        assert "TSLA" in result
        assert "[Aktie]" in result

    def test_max_10_positions(self):
        """Only first 10 watchlist positions shown."""
        positions = [
            make_position(id=i, name=f"Stock{i}", ticker=f"STK{i}", in_watchlist=True)
            for i in range(15)
        ]
        result = _build_watchlist_summary(positions)

        # Should show first 10
        assert "Stock0" in result
        assert "Stock9" in result
        # Should indicate more
        assert "+ 5 weitere" in result
        # Should not show all
        assert "Stock14" not in result

    def test_with_multiple_asset_classes(self):
        """Watchlist with mixed asset classes."""
        positions = [
            make_position(id=1, asset_class="Aktie", name="Stock1", ticker="STK1"),
            make_position(id=2, asset_class="Anleihe", name="Bond1", ticker="BND1"),
        ]
        result = _build_watchlist_summary(positions)

        assert "Stock1" in result
        assert "[Aktie]" in result
        assert "Bond1" in result
        assert "[Anleihe]" in result


class TestInvestmentCompassContextBuilding:
    """Test context building and lineage tracking."""

    @pytest.mark.asyncio
    async def test_context_with_no_repositories(self):
        """Context builds with None repositories (guards for missing data)."""
        mock_llm = AsyncMock()
        mock_llm.model = "test-model"
        mock_llm.chat = AsyncMock(return_value="Test response")

        agent = InvestmentCompassAgent(
            positions_repo=MagicMock(get_portfolio=lambda: [], get_watchlist=lambda: []),
            market_repo=None,
            analyses_repo=MagicMock(get_latest_bulk=lambda *args, **kwargs: {}),
            portfolio_story_repo=None,  # None!
            llm=mock_llm,
            skills_repo=None,
        )

        result = await agent.analyze(user_query="Test query")

        # Should not crash and should return valid result
        assert result.response == "Test response"
        assert "portfolio_data" in result.lineage["agents_used"]

    @pytest.mark.asyncio
    async def test_lineage_includes_agents_used(self):
        """Lineage tracks which agents provided context."""
        positions = [make_position(id=1, name="AAPL", ticker="AAPL")]

        mock_positions_repo = MagicMock()
        mock_positions_repo.get_portfolio.return_value = positions
        mock_positions_repo.get_watchlist.return_value = []

        mock_analyses_repo = MagicMock()
        # Simulate storychecker verdicts available
        mock_analyses_repo.get_latest_bulk.return_value = {
            1: MagicMock(position_id=1, verdict="intact", summary="Good")
        }

        mock_portfolio_story_repo = None

        mock_llm = AsyncMock()
        mock_llm.model = "test-model"
        mock_llm.chat = AsyncMock(return_value="Analysis result")

        agent = InvestmentCompassAgent(
            positions_repo=mock_positions_repo,
            market_repo=None,
            analyses_repo=mock_analyses_repo,
            portfolio_story_repo=mock_portfolio_story_repo,
            llm=mock_llm,
            skills_repo=None,
        )

        result = await agent.analyze(user_query="What about AAPL?")

        # Lineage should track portfolio_data
        assert "portfolio_data" in result.lineage["agents_used"]
        # And potentially storychecker if verdicts were fetched
        # (depends on mock setup)
        assert result.lineage["model"] == "test-model"

    @pytest.mark.asyncio
    async def test_skill_tracking_in_lineage(self):
        """Lineage includes skill if provided."""
        mock_llm = AsyncMock()
        mock_llm.model = "test-model"
        mock_llm.chat = AsyncMock(return_value="Result")

        agent = InvestmentCompassAgent(
            positions_repo=MagicMock(get_portfolio=lambda: [], get_watchlist=lambda: []),
            market_repo=None,
            analyses_repo=MagicMock(get_latest_bulk=lambda *args, **kwargs: {}),
            portfolio_story_repo=None,
            llm=mock_llm,
            skills_repo=None,
        )

        result = await agent.analyze(user_query="Test", skill_name="Buffett")

        assert "Buffett" in result.lineage["skills_used"]

    @pytest.mark.asyncio
    async def test_llm_receives_full_context(self):
        """LLM is called with combined system prompt + context + query."""
        positions = [make_position(id=1, name="AAPL", ticker="AAPL")]

        mock_positions_repo = MagicMock()
        mock_positions_repo.get_portfolio.return_value = positions
        mock_positions_repo.get_watchlist.return_value = []

        mock_analyses_repo = MagicMock()
        mock_analyses_repo.get_latest_bulk.return_value = {}

        mock_llm = AsyncMock()
        mock_llm.model = "test-model"
        mock_llm.chat = AsyncMock(return_value="Response text")

        agent = InvestmentCompassAgent(
            positions_repo=mock_positions_repo,
            market_repo=None,
            analyses_repo=mock_analyses_repo,
            portfolio_story_repo=None,
            llm=mock_llm,
            skills_repo=None,
        )

        await agent.analyze(user_query="My question?")

        # Verify LLM was called
        mock_llm.chat.assert_called_once()
        call_args = mock_llm.chat.call_args
        # First arg should be list of Message objects
        messages = call_args[0][0]
        assert len(messages) == 1
        # Content should include portfolio data and query
        content = messages[0].content
        assert "Portfolio (aktuell)" in content  # Portfolio snapshot header
        assert "My question?" in content  # User query

    @pytest.mark.asyncio
    async def test_empty_portfolio_analysis(self):
        """Analysis works with empty portfolio."""
        mock_positions_repo = MagicMock()
        mock_positions_repo.get_portfolio.return_value = []
        mock_positions_repo.get_watchlist.return_value = []

        mock_analyses_repo = MagicMock()
        mock_analyses_repo.get_latest_bulk.return_value = {}

        mock_llm = AsyncMock()
        mock_llm.model = "test-model"
        mock_llm.chat = AsyncMock(return_value="No portfolio data")

        agent = InvestmentCompassAgent(
            positions_repo=mock_positions_repo,
            market_repo=None,
            analyses_repo=mock_analyses_repo,
            portfolio_story_repo=None,
            llm=mock_llm,
            skills_repo=None,
        )

        result = await agent.analyze(user_query="Empty portfolio query")

        assert result.response == "No portfolio data"
        # Should still track portfolio_data as agent used
        assert "portfolio_data" in result.lineage["agents_used"]

    @pytest.mark.asyncio
    async def test_skill_prompt_injection(self):
        """Skill prompt is injected into system prompt."""
        mock_llm = AsyncMock()
        mock_llm.model = "test-model"
        mock_llm.chat = AsyncMock(return_value="Buffett analysis")

        agent = InvestmentCompassAgent(
            positions_repo=MagicMock(get_portfolio=lambda: [], get_watchlist=lambda: []),
            market_repo=None,
            analyses_repo=MagicMock(get_latest_bulk=lambda *args, **kwargs: {}),
            portfolio_story_repo=None,
            llm=mock_llm,
            skills_repo=None,
        )

        skill_prompt = "Fokus: Value investing und Moats"
        await agent.analyze(user_query="Query", skill_name="Buffett", skill_prompt=skill_prompt)

        # Verify skill prompt was included in the LLM call
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        content = messages[0].content

        assert "Buffett" in content
        assert skill_prompt in content
