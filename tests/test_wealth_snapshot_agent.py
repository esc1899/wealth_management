"""Tests for WealthSnapshotAgent."""

import pytest
from datetime import datetime, date
from unittest.mock import Mock, MagicMock
from core.storage.wealth_snapshots import WealthSnapshotRepository
from core.storage.dividend_snapshots import DividendSnapshotRepository
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

    def test_prepare_snapshot_stale_position_with_no_value(self, agent):
        """Test stale position that has valuation_date but no estimated_value.

        This covers the edge case where a manual position is > 30 days old
        but has no estimated_value set. The UI must handle None values gracefully.
        """
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        valuations = []
        market_agent.get_portfolio_valuation.return_value = valuations

        # Manual position: has valuation_date but NO estimated_value
        old_valuation_date = "2026-03-01"  # > 30 days old
        manual_pos = Position(
            id=1,
            asset_class="Festgeld",
            investment_type="Geld",
            name="Festgeld Sparkasse",
            quantity=None,
            unit="€",
            added_date=date(2025, 1, 1),
            # extra_data has valuation_date but NO estimated_value
            extra_data={"valuation_date": old_valuation_date},
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

            # Should detect stale position even without estimated_value
            assert len(preview.stale_positions) > 0
            stale = preview.stale_positions[0]
            assert stale["name"] == "Festgeld Sparkasse"
            assert stale["value"] is None  # Key assertion: value can be None
            assert stale["days_old"] > 30


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


class TestEndToEndWorkflow:
    """Integration tests for prepare → take snapshot workflow."""

    def test_prepare_then_take_snapshot_flow(self, agent):
        """Test the complete prepare-preview-snapshot workflow."""
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        # Step 1: User calls prepare_snapshot() to preview data
        valuations = [
            PortfolioValuation(
                symbol="AAPL",
                name="Apple Inc.",
                asset_class="Aktie",
                investment_type="Aktie",
                quantity=100,
                unit="Stück",
                purchase_price_eur=150,
                current_price_eur=200,
                current_value_eur=20_000,
                cost_basis_eur=15_000,
                pnl_eur=5_000,
                pnl_pct=33.3,
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
                current_value_eur=500_000,
                cost_basis_eur=None,
                pnl_eur=None,
                pnl_pct=None,
                fetched_at=None,
            ),
        ]
        market_agent.get_portfolio_valuation.return_value = valuations
        pos_repo.get_portfolio.return_value = []

        # Prepare should show full breakdown
        preview = agent_obj.prepare_snapshot(date_str="2026-04-10")
        assert preview.total_eur == 520_000
        assert preview.coverage_pct == 100.0
        assert len(preview.missing_pos) == 0

        # Step 2: User clicks take_snapshot
        wealth_repo.get_by_date.return_value = None
        wealth_repo.create.return_value = Mock(
            id=1,
            date="2026-04-10",
            total_eur=520_000,
            breakdown={"Aktie": 20_000, "Immobilie": 500_000},
            coverage_pct=100.0,
            missing_pos=None,
            is_manual=False,
            note=None,
        )

        # Take snapshot with same date
        snapshot = agent_obj.take_snapshot(
            date_str="2026-04-10",
            is_manual=False,
            note=None,
        )

        # Verify snapshot was created
        assert snapshot.total_eur == 520_000
        assert snapshot.coverage_pct == 100.0
        wealth_repo.create.assert_called_once()

        # Verify snapshot data matches prepare preview
        call_args = wealth_repo.create.call_args
        assert call_args.kwargs["total_eur"] == preview.total_eur
        assert call_args.kwargs["coverage_pct"] == preview.coverage_pct


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


class TestEditSnapshot:
    """Tests for snapshot editing."""

    def test_edit_snapshot_recalculates_total(self, agent):
        """Test that edit_snapshot sums the new breakdown correctly."""
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        existing_snapshot = Mock(
            id=1,
            date="2026-04-10",
            total_eur=100_000,
            breakdown={"Aktie": 30_000, "Immobilie": 70_000},
        )
        wealth_repo.get_by_date.return_value = existing_snapshot

        # User corrects Immobilie value
        new_breakdown = {"Aktie": 30_000, "Immobilie": 85_000}
        wealth_repo.update.return_value = Mock(
            id=1,
            date="2026-04-10",
            total_eur=115_000,  # Auto-calculated from breakdown sum
            breakdown=new_breakdown,
            note="Immobilie korrigiert",
        )

        result = agent_obj.edit_snapshot(
            date_str="2026-04-10",
            new_breakdown=new_breakdown,
            note="Immobilie korrigiert",
        )

        # Verify update was called with correct total
        wealth_repo.update.assert_called_once()
        call_kwargs = wealth_repo.update.call_args.kwargs
        assert call_kwargs["total_eur"] == 115_000  # Sum of new breakdown
        assert call_kwargs["breakdown"] == new_breakdown
        assert result.total_eur == 115_000

    def test_edit_snapshot_not_found_raises(self, agent):
        """Test that editing non-existent snapshot raises ValueError."""
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        wealth_repo.get_by_date.return_value = None

        with pytest.raises(ValueError, match="No snapshot"):
            agent_obj.edit_snapshot("2026-04-10", {"Aktie": 100_000})


class TestDeleteSnapshot:
    """Tests for snapshot deletion."""

    def test_delete_snapshot(self, agent):
        """Test that delete_snapshot removes the snapshot."""
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        existing = Mock(id=1, date="2026-04-10")
        wealth_repo.get_by_date.return_value = existing

        agent_obj.delete_snapshot("2026-04-10")

        wealth_repo.delete.assert_called_once_with(1)

    def test_delete_nonexistent_snapshot_raises(self, agent):
        """Test that deleting non-existent snapshot raises ValueError."""
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        wealth_repo.get_by_date.return_value = None

        with pytest.raises(ValueError, match="No snapshot"):
            agent_obj.delete_snapshot("2026-04-10")


class TestTakeSnapshotOverwrite:
    """Tests for the overwrite feature."""

    def test_take_snapshot_overwrite_true_replaces_existing(self, agent):
        """Test that overwrite=True deletes old snapshot and creates new one."""
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        existing = Mock(id=1, date="2026-04-10", total_eur=100_000)
        wealth_repo.get_by_date.return_value = existing

        valuations = [
            PortfolioValuation(
                symbol="AAPL",
                name="Apple",
                asset_class="Aktie",
                investment_type="Aktie",
                quantity=10,
                unit="Stück",
                purchase_price_eur=150,
                current_price_eur=200,
                current_value_eur=2_000,
                cost_basis_eur=1_500,
                pnl_eur=500,
                pnl_pct=33.3,
                fetched_at=datetime.utcnow(),
            ),
        ]
        market_agent.get_portfolio_valuation.return_value = valuations

        wealth_repo.create.return_value = Mock(
            id=2,
            date="2026-04-10",
            total_eur=2_000,
            breakdown={"Aktie": 2_000},
            coverage_pct=100.0,
        )

        # Call with overwrite=True
        result = agent_obj.take_snapshot(date_str="2026-04-10", overwrite=True)

        # Verify delete was called first
        wealth_repo.delete.assert_called_once_with(1)
        # Verify create was called after
        wealth_repo.create.assert_called_once()
        assert result.total_eur == 2_000

    def test_take_snapshot_overwrite_false_default_raises(self, agent):
        """Test that overwrite=False (default) raises ValueError if exists."""
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        existing = Mock(id=1, date="2026-04-10", total_eur=100_000)
        wealth_repo.get_by_date.return_value = existing

        with pytest.raises(ValueError, match="already exists"):
            agent_obj.take_snapshot(date_str="2026-04-10", overwrite=False)

        # Delete should NOT be called
        wealth_repo.delete.assert_not_called()


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_prepare_with_empty_portfolio(self, agent):
        """Prepare should handle empty portfolio gracefully."""
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        market_agent.get_portfolio_valuation.return_value = []
        pos_repo.get_portfolio.return_value = []

        preview = agent_obj.prepare_snapshot(date_str="2026-04-10")

        # Should be valid SnapshotPreview with all empty/zero values
        assert preview.total_eur == 0
        assert preview.coverage_pct == 100.0  # 0 positions = 100% coverage
        assert preview.missing_pos == []
        assert preview.stale_positions == []

    def test_prepare_all_positions_missing_values(self, agent):
        """Prepare should handle portfolio with no valuations."""
        agent_obj, (pos_repo, market_repo, wealth_repo, market_agent) = agent

        valuations = [
            PortfolioValuation(
                symbol=None,
                name="Festgeld 1",
                asset_class="Festgeld",
                investment_type="Geld",
                quantity=None,
                unit="€",
                purchase_price_eur=None,
                current_price_eur=None,
                current_value_eur=None,  # No value
                cost_basis_eur=None,
                pnl_eur=None,
                pnl_pct=None,
                fetched_at=None,
            ),
            PortfolioValuation(
                symbol=None,
                name="Immobilie",
                asset_class="Immobilie",
                investment_type="Immobilien",
                quantity=None,
                unit="Stück",
                purchase_price_eur=None,
                current_price_eur=None,
                current_value_eur=None,  # No value
                cost_basis_eur=None,
                pnl_eur=None,
                pnl_pct=None,
                fetched_at=None,
            ),
        ]
        market_agent.get_portfolio_valuation.return_value = valuations
        pos_repo.get_portfolio.return_value = []

        preview = agent_obj.prepare_snapshot(date_str="2026-04-10")

        # All positions missing
        assert preview.total_eur == 0
        assert preview.coverage_pct == 0  # 0 out of 2
        assert len(preview.missing_pos) == 2
        assert "Festgeld 1" in preview.missing_pos
        assert "Immobilie" in preview.missing_pos


def _make_position(ticker="AAPL", asset_class="Aktie", quantity=10.0, unit="Stück",
                   auto_fetch=True, extra_data=None) -> Position:
    return Position(
        id=1,
        name="Test",
        asset_class=asset_class,
        investment_type=asset_class,
        ticker=ticker,
        quantity=quantity,
        unit=unit,
        in_portfolio=True,
        added_date=date(2026, 1, 1),
        extra_data=extra_data or {},
    )


class TestBackfillSnapshots:
    def _make_agent(self, positions, price_map, existing_dates=None):
        """positions: list[Position], price_map: {date_str: price}, existing_dates: set"""
        pos_repo = Mock(spec=PositionsRepository)
        pos_repo.get_portfolio.return_value = positions
        market_repo = Mock(spec=MarketDataRepository)
        market_repo.get_price_for_date_or_prior.side_effect = lambda sym, d, max_days_back=3: price_map.get(d)
        wealth_repo = Mock(spec=WealthSnapshotRepository)
        wealth_repo.get_by_date.side_effect = lambda d: "exists" if d in (existing_dates or set()) else None
        wealth_repo.create.return_value = Mock()
        market_agent = Mock()
        return WealthSnapshotAgent(
            positions_repo=pos_repo,
            market_repo=market_repo,
            wealth_repo=wealth_repo,
            market_data_agent=market_agent,
        ), wealth_repo

    def test_creates_snapshot_for_missing_weekday(self):
        from datetime import timedelta
        today = date.today()
        # Find a recent weekday
        d = today - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        price_map = {d.isoformat(): 100.0}
        pos = _make_position(quantity=5.0)
        agent, wealth_repo = self._make_agent([pos], price_map)
        created = agent.backfill_snapshots(days=7)
        assert created >= 1
        wealth_repo.create.assert_called()

    def test_skips_existing_snapshot(self):
        from datetime import timedelta
        today = date.today()
        d = today - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        price_map = {d.isoformat(): 100.0}
        pos = _make_position(quantity=5.0)
        agent, wealth_repo = self._make_agent([pos], price_map, existing_dates={d.isoformat()})
        agent.backfill_snapshots(days=7)
        wealth_repo.create.assert_not_called()

    def test_skips_weekends(self):
        from datetime import timedelta
        # Build a price_map only for weekends in the last 7 days
        today = date.today()
        weekend_prices = {}
        for i in range(1, 8):
            d = today - timedelta(days=i)
            if d.weekday() >= 5:
                weekend_prices[d.isoformat()] = 100.0
        pos = _make_position(quantity=5.0)
        agent, wealth_repo = self._make_agent([pos], weekend_prices)
        agent.backfill_snapshots(days=7)
        wealth_repo.create.assert_not_called()

    def test_skips_day_with_no_price_data(self):
        pos = _make_position(quantity=5.0)
        agent, wealth_repo = self._make_agent([pos], price_map={})  # no prices stored
        agent.backfill_snapshots(days=7)
        wealth_repo.create.assert_not_called()

    def test_manual_position_uses_estimated_value(self):
        from datetime import timedelta
        today = date.today()
        d = today - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        manual_pos = _make_position(
            ticker=None, asset_class="Immobilie", auto_fetch=False,
            extra_data={"estimated_value": 250_000.0}
        )
        agent, wealth_repo = self._make_agent([manual_pos], price_map={})
        created = agent.backfill_snapshots(days=3)
        assert created >= 1
        call_kwargs = wealth_repo.create.call_args_list[0][1]
        assert call_kwargs["total_eur"] == pytest.approx(250_000.0)

    def test_returns_zero_for_empty_portfolio(self):
        agent, wealth_repo = self._make_agent([], price_map={})
        assert agent.backfill_snapshots(days=7) == 0
        wealth_repo.create.assert_not_called()


class TestRecalculateSnapshot:
    def _make_agent(self, positions, price_map, existing_snapshot=None):
        pos_repo = Mock(spec=PositionsRepository)
        pos_repo.get_portfolio.return_value = positions
        market_repo = Mock(spec=MarketDataRepository)
        market_repo.get_price_for_date_or_prior.side_effect = lambda sym, d: price_map.get(d)
        wealth_repo = Mock(spec=WealthSnapshotRepository)
        wealth_repo.get_by_date.return_value = existing_snapshot
        wealth_repo.create.return_value = Mock(coverage_pct=100.0)
        market_agent = Mock()
        return WealthSnapshotAgent(
            positions_repo=pos_repo,
            market_repo=market_repo,
            wealth_repo=wealth_repo,
            market_data_agent=market_agent,
        ), wealth_repo

    def test_recalculate_overwrites_existing(self):
        pos = _make_position(quantity=10.0)
        existing = Mock(id=42)
        agent, wealth_repo = self._make_agent([pos], {"2026-01-15": 200.0}, existing_snapshot=existing)
        result = agent.recalculate_snapshot("2026-01-15")
        wealth_repo.delete.assert_called_once_with(42)
        wealth_repo.create.assert_called_once()
        assert result is not None

    def test_recalculate_creates_when_no_existing(self):
        pos = _make_position(quantity=10.0)
        agent, wealth_repo = self._make_agent([pos], {"2026-01-15": 200.0}, existing_snapshot=None)
        result = agent.recalculate_snapshot("2026-01-15")
        wealth_repo.delete.assert_not_called()
        wealth_repo.create.assert_called_once()
        call_kwargs = wealth_repo.create.call_args[1]
        assert call_kwargs["total_eur"] == pytest.approx(2000.0)
        assert call_kwargs["note"] == "recalculated"
        assert call_kwargs["is_manual"] is True

    def test_recalculate_returns_none_when_no_price_data(self):
        pos = _make_position(quantity=10.0)
        agent, wealth_repo = self._make_agent([pos], {}, existing_snapshot=None)
        result = agent.recalculate_snapshot("2026-01-15")
        assert result is None
        wealth_repo.create.assert_not_called()

    def test_recalculate_coverage_reflects_missing(self):
        pos_with_price = _make_position(ticker="AAPL", quantity=10.0)
        pos_no_price = Position(
            id=2, name="NoData Inc", asset_class="Aktie", investment_type="Aktie",
            ticker="NODATA", quantity=5.0, unit="Stück", in_portfolio=True,
            added_date=date(2026, 1, 1), extra_data={},
        )
        # price_map only has AAPL prices (keyed by date), NODATA returns None
        price_map_by_ticker = {"AAPL": 100.0}

        pos_repo = Mock(spec=PositionsRepository)
        pos_repo.get_portfolio.return_value = [pos_with_price, pos_no_price]
        market_repo = Mock(spec=MarketDataRepository)
        market_repo.get_price_for_date_or_prior.side_effect = lambda sym, d: price_map_by_ticker.get(sym)
        wealth_repo = Mock(spec=WealthSnapshotRepository)
        wealth_repo.get_by_date.return_value = None
        wealth_repo.create.return_value = Mock(coverage_pct=50.0)
        market_agent = Mock()
        agent = WealthSnapshotAgent(
            positions_repo=pos_repo, market_repo=market_repo,
            wealth_repo=wealth_repo, market_data_agent=market_agent,
        )
        agent.recalculate_snapshot("2026-01-15")
        call_kwargs = wealth_repo.create.call_args[1]
        assert call_kwargs["coverage_pct"] == pytest.approx(50.0)
        assert "NoData Inc" in call_kwargs["missing_pos"]

    def test_recalculate_with_gold_units(self):
        """Gold positions (unit='g') must apply troy-oz conversion: value = (price/31.1035) * grams."""
        TROY_OZ_TO_G = 31.1035
        gold_price_eur_per_oz = 3110.35  # €100 per gram at this price
        gold_grams = 10.0
        expected_value = (gold_price_eur_per_oz / TROY_OZ_TO_G) * gold_grams  # 1000.0

        pos = Position(
            id=1, name="Gold", asset_class="Edelmetall", investment_type="Edelmetall",
            ticker="GC=F", quantity=gold_grams, unit="g", in_portfolio=True,
            added_date=date(2026, 1, 1), extra_data={},
        )
        pos_repo = Mock(spec=PositionsRepository)
        pos_repo.get_portfolio.return_value = [pos]
        market_repo = Mock(spec=MarketDataRepository)
        market_repo.get_price_for_date_or_prior.return_value = gold_price_eur_per_oz
        wealth_repo = Mock(spec=WealthSnapshotRepository)
        wealth_repo.get_by_date.return_value = None
        wealth_repo.create.return_value = Mock(coverage_pct=100.0, missing_pos=None)
        agent = WealthSnapshotAgent(
            positions_repo=pos_repo, market_repo=market_repo,
            wealth_repo=wealth_repo, market_data_agent=Mock(),
        )
        agent.recalculate_snapshot("2026-01-15")
        call_kwargs = wealth_repo.create.call_args[1]
        assert call_kwargs["total_eur"] == pytest.approx(expected_value)


class TestTakeDividendSnapshot:
    def _make_agent(self, valuations, existing_dividend=None):
        pos_repo = Mock(spec=PositionsRepository)
        market_repo = Mock(spec=MarketDataRepository)
        wealth_repo = Mock(spec=WealthSnapshotRepository)
        dividend_repo = Mock(spec=DividendSnapshotRepository)
        dividend_repo.get_by_date.return_value = existing_dividend
        dividend_repo.create.return_value = Mock(total_eur=sum(
            v.annual_dividend_eur for v in valuations if v.annual_dividend_eur
        ), coverage_pct=100.0)
        market_agent = Mock()
        market_agent.get_portfolio_valuation.return_value = valuations
        agent = WealthSnapshotAgent(
            positions_repo=pos_repo, market_repo=market_repo,
            wealth_repo=wealth_repo, market_data_agent=market_agent,
            dividend_repo=dividend_repo,
        )
        return agent, dividend_repo

    def _make_valuation(self, symbol="AAPL", asset_class="Aktie", annual_dividend_eur=None):
        v = Mock()
        v.symbol = symbol
        v.asset_class = asset_class
        v.annual_dividend_eur = annual_dividend_eur
        v.in_portfolio = True
        return v

    def test_basic_snapshot_sums_dividends(self):
        vals = [
            self._make_valuation("AAPL", annual_dividend_eur=100.0),
            self._make_valuation("MSFT", annual_dividend_eur=200.0),
        ]
        agent, dividend_repo = self._make_agent(vals)
        agent.take_dividend_snapshot("2026-01-15")
        call_kwargs = dividend_repo.create.call_args[1]
        assert call_kwargs["total_eur"] == pytest.approx(300.0)

    def test_positions_without_dividend_are_excluded(self):
        vals = [
            self._make_valuation("AAPL", annual_dividend_eur=100.0),
            self._make_valuation("BRK", annual_dividend_eur=None),
            self._make_valuation("NVDA", annual_dividend_eur=0.0),
        ]
        agent, dividend_repo = self._make_agent(vals)
        agent.take_dividend_snapshot("2026-01-15")
        call_kwargs = dividend_repo.create.call_args[1]
        assert call_kwargs["total_eur"] == pytest.approx(100.0)

    def test_raises_if_snapshot_exists_and_overwrite_false(self):
        existing = Mock(id=99)
        agent, _ = self._make_agent([], existing_dividend=existing)
        with pytest.raises(ValueError, match="already exists"):
            agent.take_dividend_snapshot("2026-01-15", overwrite=False)

    def test_overwrites_existing_when_flag_set(self):
        existing = Mock(id=42)
        vals = [self._make_valuation("AAPL", annual_dividend_eur=50.0)]
        agent, dividend_repo = self._make_agent(vals, existing_dividend=existing)
        agent.take_dividend_snapshot("2026-01-15", overwrite=True)
        dividend_repo.delete.assert_called_once_with(42)
        dividend_repo.create.assert_called_once()

    def test_raises_without_dividend_repo(self):
        pos_repo = Mock(spec=PositionsRepository)
        market_repo = Mock(spec=MarketDataRepository)
        wealth_repo = Mock(spec=WealthSnapshotRepository)
        market_agent = Mock()
        agent = WealthSnapshotAgent(
            positions_repo=pos_repo, market_repo=market_repo,
            wealth_repo=wealth_repo, market_data_agent=market_agent,
        )
        with pytest.raises(ValueError, match="not initialized"):
            agent.take_dividend_snapshot()
