"""
Unit tests for PortfolioAgent — focus on clear_watchlist and tool dispatch.
"""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

from agents.portfolio_agent import PortfolioAgent
from core.storage.models import Position


def _make_watchlist_position(id: int, ticker: str = "AAPL") -> Position:
    return Position(
        id=id,
        ticker=ticker,
        name=ticker,
        asset_class="Aktie",
        investment_type="Wertpapiere",
        unit="Stück",
        added_date=date.today(),
        in_portfolio=False,
    )


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.add.return_value = MagicMock(id=1)
    repo.delete.return_value = True
    repo.get_watchlist.return_value = []
    repo.get_portfolio.return_value = []
    repo.clear_watchlist.return_value = 0  # Mock the new batch method
    repo.clear_portfolio.return_value = 0  # Mock the new batch method
    return repo


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.model = "test-model"
    return llm


@pytest.fixture
def agent(mock_repo, mock_llm):
    return PortfolioAgent(positions_repo=mock_repo, llm=mock_llm)


class TestClearWatchlist:
    def test_deletes_all_watchlist_entries(self, agent, mock_repo):
        mock_repo.clear_watchlist.return_value = 3
        result = agent._tool_clear_watchlist()
        assert result["deleted"] == 3
        mock_repo.clear_watchlist.assert_called_once()

    def test_empty_watchlist_returns_zero(self, agent, mock_repo):
        mock_repo.clear_watchlist.return_value = 0
        result = agent._tool_clear_watchlist()
        assert result["deleted"] == 0
        mock_repo.clear_watchlist.assert_called_once()


class TestClearPortfolio:
    def test_deletes_all_portfolio_entries(self, agent, mock_repo):
        mock_repo.clear_portfolio.return_value = 2
        result = agent._tool_clear_portfolio()
        assert result["deleted"] == 2
        mock_repo.clear_portfolio.assert_called_once()

    def test_empty_portfolio_returns_zero(self, agent, mock_repo):
        mock_repo.clear_portfolio.return_value = 0
        result = agent._tool_clear_portfolio()
        assert result["deleted"] == 0
        mock_repo.clear_portfolio.assert_called_once()


class TestToolDispatch:
    def test_clear_watchlist_dispatched(self, agent, mock_repo):
        mock_repo.get_watchlist.return_value = []
        result = agent._execute_tool("clear_watchlist", {})
        assert "deleted" in result

    def test_clear_portfolio_dispatched(self, agent, mock_repo):
        mock_repo.get_portfolio.return_value = []
        result = agent._execute_tool("clear_portfolio", {})
        assert "deleted" in result

    def test_remove_watchlist_dispatched(self, agent, mock_repo):
        result = agent._execute_tool("remove_from_watchlist", {"entry_id": 5})
        mock_repo.delete.assert_called_once_with(5)

    def test_unknown_tool_returns_error(self, agent):
        result = agent._execute_tool("nonexistent_tool", {})
        assert "error" in result
