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
        mock_repo.get_watchlist.return_value = [
            _make_watchlist_position(1, "AAPL"),
            _make_watchlist_position(2, "MSFT"),
            _make_watchlist_position(3, "SAP.DE"),
        ]
        result = agent._tool_clear_watchlist()
        assert result["deleted"] == 3
        assert mock_repo.delete.call_count == 3

    def test_deletes_correct_ids(self, agent, mock_repo):
        mock_repo.get_watchlist.return_value = [
            _make_watchlist_position(7, "AAPL"),
            _make_watchlist_position(42, "MSFT"),
        ]
        agent._tool_clear_watchlist()
        deleted_ids = {call.args[0] for call in mock_repo.delete.call_args_list}
        assert deleted_ids == {7, 42}

    def test_empty_watchlist_returns_zero(self, agent, mock_repo):
        mock_repo.get_watchlist.return_value = []
        result = agent._tool_clear_watchlist()
        assert result["deleted"] == 0
        mock_repo.delete.assert_not_called()

    def test_partial_delete_counts_only_successful(self, agent, mock_repo):
        mock_repo.get_watchlist.return_value = [
            _make_watchlist_position(1, "AAPL"),
            _make_watchlist_position(2, "MSFT"),
        ]
        mock_repo.delete.side_effect = [True, False]
        result = agent._tool_clear_watchlist()
        assert result["deleted"] == 1


class TestClearPortfolio:
    def test_deletes_all_portfolio_entries(self, agent, mock_repo):
        mock_repo.get_portfolio.return_value = [
            _make_watchlist_position(1, "AAPL"),
            _make_watchlist_position(2, "SAP.DE"),
        ]
        result = agent._tool_clear_portfolio()
        assert result["deleted"] == 2
        assert mock_repo.delete.call_count == 2

    def test_deletes_correct_ids(self, agent, mock_repo):
        mock_repo.get_portfolio.return_value = [
            _make_watchlist_position(10, "AAPL"),
            _make_watchlist_position(20, "SAP.DE"),
        ]
        agent._tool_clear_portfolio()
        deleted_ids = {call.args[0] for call in mock_repo.delete.call_args_list}
        assert deleted_ids == {10, 20}

    def test_empty_portfolio_returns_zero(self, agent, mock_repo):
        mock_repo.get_portfolio.return_value = []
        result = agent._tool_clear_portfolio()
        assert result["deleted"] == 0
        mock_repo.delete.assert_not_called()

    def test_partial_delete_counts_only_successful(self, agent, mock_repo):
        mock_repo.get_portfolio.return_value = [
            _make_watchlist_position(1, "AAPL"),
            _make_watchlist_position(2, "MSFT"),
        ]
        mock_repo.delete.side_effect = [True, False]
        result = agent._tool_clear_portfolio()
        assert result["deleted"] == 1


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
