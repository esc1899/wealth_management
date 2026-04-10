"""Tests for WealthSnapshotAgent."""

import pytest
from datetime import datetime, date
from unittest.mock import Mock, MagicMock
from core.storage.wealth_snapshots import WealthSnapshotRepository
from core.storage.positions import PositionsRepository
from core.storage.market_data import MarketDataRepository
from core.storage.models import Position
from agents.wealth_snapshot_agent import WealthSnapshotAgent, SnapshotPreview
from agents.market_data_agent import PortfolioValuation


@pytest.fixture
def mock_repos():
    """Create mock repositories."""
    positions_repo = Mock(spec=PositionsRepository)
    market_repo = Mock(spec=MarketDataRepository)
    wealth_repo = Mock(spec=WealthSnapshotRepository)
    return positions_repo, market_repo, wealth_repo


@pytest.fixture
def mock_market_data_agent():
    """Create mock MarketDataAgent."""
    agent = Mock()
    return agent


@pytest.fixture
def agent(mock_repos, mock_market_data_agent):
    """Create WealthSnapshotAgent with mocks."""
    positions_repo, market_repo, wealth_repo = mock_repos
    return WealthSnapshotAgent(
        positions_repo=positions_repo,
        market_repo=market_repo,
        wealth_repo=wealth_repo,
        market_data_agent=mock_market_data_agent,
    ), (positions_repo, market_repo, wealth_repo, mock_market_data_agent)


class TestTakeSnapshot:
    def test_take_snapshot_basic(self, agent):
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        # Mock wealth repo to return None (no existing snapshot)
        wealth_repo.get_by_date.return_value = None

        # Setup mocks
        valuations = [
            PortfolioValuation(
                symbol="AAPL",
                name="Apple",
                asset_class="Aktie",
                investment_type="Aktie",
                quantity=10,
                unit="Stück",
                purchase_price_eur=150,
                current_price_eur=180,
                current_value_eur=1800,
                cost_basis_eur=1500,
                pnl_eur=300,
                pnl_pct=20.0,
                fetched_at=datetime.utcnow(),
            ),
            PortfolioValuation(
                symbol=None,
                name="Immobilie München",
                asset_class="Immobilie",
                investment_type="Immobilien",
                quantity=None,
                unit="Stück",
                purchase_price_eur=None,
                current_price_eur=None,
                current_value_eur=300_000,
                cost_basis_eur=None,
                pnl_eur=None,
                pnl_pct=None,
                fetched_at=None,
            ),
        ]
        market_agent.get_portfolio_valuation.return_value = valuations

        # Mock wealth repo to succeed
        wealth_repo.create.return_value = Mock(
            id=1,
            date="2026-04-10",
            total_eur=301_800.0,
            breakdown={"Aktie": 1800, "Immobilie": 300_000},
            coverage_pct=100.0,
            missing_pos=None,
            is_manual=False,
        )

        # Call
        snapshot = agent_obj.take_snapshot(
            date_str="2026-04-10",
            is_manual=False,
        )

        # Verify
        assert snapshot.total_eur == 301_800.0
        assert snapshot.breakdown == {"Aktie": 1800, "Immobilie": 300_000}
        assert snapshot.coverage_pct == 100.0
        wealth_repo.create.assert_called_once()

    def test_take_snapshot_with_missing_positions(self, agent):
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        # Mock wealth repo to return None (no existing snapshot)
        wealth_repo.get_by_date.return_value = None

        valuations = [
            PortfolioValuation(
                symbol="AAPL",
                name="Apple",
                asset_class="Aktie",
                investment_type="Aktie",
                quantity=10,
                unit="Stück",
                purchase_price_eur=150,
                current_price_eur=180,
                current_value_eur=1800,
                cost_basis_eur=1500,
                pnl_eur=300,
                pnl_pct=20.0,
                fetched_at=datetime.utcnow(),
            ),
            PortfolioValuation(
                symbol=None,
                name="Festgeld (Sparkasse)",
                asset_class="Festgeld",
                investment_type="Geld",
                quantity=None,
                unit="€",
                purchase_price_eur=None,
                current_price_eur=None,
                current_value_eur=None,  # No value!
                cost_basis_eur=None,
                pnl_eur=None,
                pnl_pct=None,
                fetched_at=None,
            ),
        ]
        market_agent.get_portfolio_valuation.return_value = valuations

        wealth_repo.create.return_value = Mock(
            id=1,
            date="2026-04-10",
            total_eur=1800.0,
            breakdown={"Aktie": 1800},
            coverage_pct=50.0,
            missing_pos=["Festgeld (Sparkasse)"],
            is_manual=False,
        )

        snapshot = agent_obj.take_snapshot(date_str="2026-04-10")

        # Verify
        assert snapshot.coverage_pct == 50.0
        assert "Festgeld (Sparkasse)" in snapshot.missing_pos
        assert snapshot.total_eur == 1800.0

    def test_take_snapshot_default_date_is_today(self, agent):
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        # Mock wealth repo to return None (no existing snapshot)
        wealth_repo.get_by_date.return_value = None

        market_agent.get_portfolio_valuation.return_value = []
        wealth_repo.create.return_value = Mock(
            id=1,
            date=date.today().isoformat(),
            total_eur=0,
            breakdown={},
            coverage_pct=0,
            missing_pos=[],
            is_manual=False,
        )

        snapshot = agent_obj.take_snapshot()

        # Verify that create was called with today's date
        args, kwargs = wealth_repo.create.call_args
        assert kwargs.get("date_str") == date.today().isoformat()

    def test_take_snapshot_duplicate_fails(self, agent):
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        market_agent.get_portfolio_valuation.return_value = []
        wealth_repo.create.side_effect = ValueError("Snapshot for 2026-04-10 already exists")

        with pytest.raises(ValueError, match="already exists"):
            agent_obj.take_snapshot(date_str="2026-04-10")


class TestPrepareSnapshot:
    def test_prepare_snapshot_all_complete(self, agent):
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        valuations = [
            PortfolioValuation(
                symbol="AAPL",
                name="Apple",
                asset_class="Aktie",
                investment_type="Aktie",
                quantity=10,
                unit="Stück",
                purchase_price_eur=150,
                current_price_eur=180,
                current_value_eur=1800,
                cost_basis_eur=1500,
                pnl_eur=300,
                pnl_pct=20.0,
                fetched_at=datetime.utcnow(),
            ),
        ]
        market_agent.get_portfolio_valuation.return_value = valuations
        pos_repo.get_portfolio.return_value = []

        preview = agent_obj.prepare_snapshot(date_str="2026-04-10")

        assert preview.date_str == "2026-04-10"
        assert preview.total_eur == 1800
        assert preview.coverage_pct == 100.0
        assert len(preview.missing_pos) == 0

    def test_prepare_snapshot_detects_stale_manual_valuations(self, agent):
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        # Autofetch position
        valuations = [
            PortfolioValuation(
                symbol="AAPL",
                name="Apple",
                asset_class="Aktie",
                investment_type="Aktie",
                quantity=10,
                unit="Stück",
                purchase_price_eur=150,
                current_price_eur=180,
                current_value_eur=1800,
                cost_basis_eur=1500,
                pnl_eur=300,
                pnl_pct=20.0,
                fetched_at=datetime.utcnow(),
            ),
        ]
        market_agent.get_portfolio_valuation.return_value = valuations

        # Manual position with old valuation_date
        old_valuation_date = "2026-03-01"  # > 30 days old
        manual_pos = Position(
            id=2,
            asset_class="Immobilie",
            investment_type="Immobilien",
            name="Immobilie München",
            quantity=None,
            unit="Stück",
            added_date=date(2025, 1, 1),
            extra_data={"estimated_value": 300_000, "valuation_date": old_valuation_date},
        )
        pos_repo.get_portfolio.return_value = [manual_pos]

        # Mock asset class registry
        import unittest.mock as mock
        with mock.patch(
            "agents.wealth_snapshot_agent.get_asset_class_registry"
        ) as mock_registry:
            mock_cfg = Mock()
            mock_cfg.auto_fetch = False
            mock_registry.return_value.get.return_value = mock_cfg

            preview = agent_obj.prepare_snapshot(date_str="2026-04-10")

            # Should detect stale position
            assert len(preview.stale_positions) > 0
            assert preview.stale_positions[0]["name"] == "Immobilie München"
            assert preview.stale_positions[0]["days_old"] > 30


class TestUpdateManualPosition:
    def test_update_position_value(self, agent):
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        old_pos = Position(
            id=1,
            asset_class="Immobilie",
            investment_type="Immobilien",
            name="Immobilie München",
            quantity=None,
            unit="Stück",
            added_date=date(2025, 1, 1),
            extra_data={"estimated_value": 300_000},
        )
        pos_repo.get.return_value = old_pos

        # Setup mock for update to return updated position
        updated_pos = Position(
            id=1,
            asset_class="Immobilie",
            investment_type="Immobilien",
            name="Immobilie München",
            quantity=None,
            unit="Stück",
            added_date=date(2025, 1, 1),
            extra_data={
                "estimated_value": 320_000,
                "valuation_date": datetime.utcnow().isoformat(),
            },
        )
        pos_repo.update.return_value = updated_pos

        # Call
        result = agent_obj.update_manual_position_value(
            position_id=1,
            new_value_eur=320_000,
            note="Market appreciation",
        )

        # Verify
        assert result.extra_data["estimated_value"] == 320_000
        assert "valuation_date" in result.extra_data
        pos_repo.update.assert_called_once()

    def test_update_nonexistent_position_fails(self, agent):
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        pos_repo.get.return_value = None

        with pytest.raises(ValueError, match="not found"):
            agent_obj.update_manual_position_value(
                position_id=999,
                new_value_eur=500_000,
            )


class TestGettersAndListing:
    def test_get_latest_snapshot(self, agent):
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        mock_snapshot = Mock()
        wealth_repo.latest.return_value = mock_snapshot

        result = agent_obj.get_latest_snapshot()

        assert result == mock_snapshot
        wealth_repo.latest.assert_called_once()

    def test_list_snapshots(self, agent):
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        mock_snapshots = [Mock(), Mock()]
        wealth_repo.list.return_value = mock_snapshots

        result = agent_obj.list_snapshots(days=30)

        assert result == mock_snapshots
        wealth_repo.list.assert_called_once_with(days=30)

    def test_get_snapshot_for_date(self, agent):
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        mock_snapshot = Mock()
        wealth_repo.get_by_date.return_value = mock_snapshot

        result = agent_obj.get_snapshot_for_date("2026-04-10")

        assert result == mock_snapshot
        wealth_repo.get_by_date.assert_called_once_with("2026-04-10")
