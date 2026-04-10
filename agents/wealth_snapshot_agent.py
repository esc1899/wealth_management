"""
Wealth Snapshot Agent — orchestrates periodic snapshots of total portfolio wealth.

Snapshots track total wealth (including non-tradeable assets) over time with
asset class breakdown. The agent can also prepare snapshots by checking data
completeness and warning about stale manual valuations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Dict, List

from core.storage.market_data import MarketDataRepository
from core.storage.positions import PositionsRepository
from core.storage.wealth_snapshots import WealthSnapshotRepository
from core.storage.models import WealthSnapshot, Position
from agents.market_data_agent import MarketDataAgent
from core.asset_class_config import get_asset_class_registry


@dataclass
class SnapshotPreview:
    """Preview of data available for taking a snapshot."""
    date_str: str
    total_eur: float
    breakdown: Dict[str, float]
    coverage_pct: float
    missing_pos: List[str]
    stale_positions: List[Dict] = field(default_factory=list)  # {name, value, last_update}
    warnings: List[str] = field(default_factory=list)


class WealthSnapshotAgent:

    def __init__(
        self,
        positions_repo: PositionsRepository,
        market_repo: MarketDataRepository,
        wealth_repo: WealthSnapshotRepository,
        market_data_agent: MarketDataAgent,
    ):
        self._positions = positions_repo
        self._market = market_repo
        self._wealth = wealth_repo
        self._market_data_agent = market_data_agent

    # ------------------------------------------------------------------
    # Snapshot-Logik
    # ------------------------------------------------------------------

    def take_snapshot(
        self,
        date_str: Optional[str] = None,
        is_manual: bool = False,
        note: Optional[str] = None,
        overwrite: bool = False,
    ) -> WealthSnapshot:
        """
        Take a snapshot of total wealth (portfolio + non-tradeable assets).

        Args:
            date_str: Date in YYYY-MM-DD format (default: today)
            is_manual: True if created by user/agent chat, not scheduled
            note: Optional comment
            overwrite: If True, delete existing snapshot for this date before creating new one

        Returns:
            Persisted WealthSnapshot

        Raises:
            ValueError: If a snapshot for this date already exists and overwrite=False
        """
        if date_str is None:
            date_str = date.today().isoformat()

        # Check if snapshot already exists
        existing = self._wealth.get_by_date(date_str)
        if existing is not None:
            if not overwrite:
                raise ValueError(f"Snapshot for {date_str} already exists")
            # Delete old snapshot before creating new one
            self._wealth.delete(existing.id)

        # Calculate current portfolio valuation
        valuations = self._market_data_agent.get_portfolio_valuation(include_watchlist=False)

        # Group by asset class
        breakdown: Dict[str, float] = {}
        missing_positions = []
        total = 0.0

        for val in valuations:
            if val.current_value_eur is None:
                missing_positions.append(val.name)
            else:
                total += val.current_value_eur
                asset_class = val.asset_class
                breakdown[asset_class] = breakdown.get(asset_class, 0) + val.current_value_eur

        # Calculate coverage
        coverage_pct = (
            (len(valuations) - len(missing_positions)) / len(valuations) * 100
            if valuations
            else 100.0
        )

        # Create snapshot
        snapshot = self._wealth.create(
            date_str=date_str,
            total_eur=total,
            breakdown=breakdown,
            coverage_pct=coverage_pct,
            missing_pos=missing_positions if missing_positions else None,
            is_manual=is_manual,
            note=note,
        )

        return snapshot

    def prepare_snapshot(self, date_str: Optional[str] = None) -> SnapshotPreview:
        """
        Preview what data is available for a snapshot.
        Identifies:
        - Current calculated values
        - Missing position values
        - Stale manual valuations (> 30 days old)

        Args:
            date_str: Date in YYYY-MM-DD (default: today)

        Returns:
            SnapshotPreview with all details
        """
        if date_str is None:
            date_str = date.today().isoformat()

        # Get valuations
        valuations = self._market_data_agent.get_portfolio_valuation(include_watchlist=False)

        # Get all positions for stale-check
        positions = self._positions.get_portfolio()

        # Build breakdown
        breakdown: Dict[str, float] = {}
        missing_positions = []
        total = 0.0

        for val in valuations:
            if val.current_value_eur is None:
                missing_positions.append(val.name)
            else:
                total += val.current_value_eur
                asset_class = val.asset_class
                breakdown[asset_class] = breakdown.get(asset_class, 0) + val.current_value_eur

        coverage_pct = (
            (len(valuations) - len(missing_positions)) / len(valuations) * 100
            if valuations
            else 100.0
        )

        # Detect stale manual positions
        stale_positions = []
        warnings = []
        now = datetime.utcnow()

        for pos in positions:
            registry = get_asset_class_registry()
            cfg = registry.get(pos.asset_class)
            is_manual = cfg and not cfg.auto_fetch if cfg else False

            if is_manual:
                extra = pos.extra_data or {}
                est_val = extra.get("estimated_value")
                val_date_str = extra.get("valuation_date")

                if val_date_str:
                    val_date = datetime.fromisoformat(val_date_str).date()
                    days_old = (datetime.utcnow().date() - val_date).days

                    if days_old > 30:
                        stale_positions.append({
                            "name": pos.name,
                            "value": est_val,
                            "last_update": val_date_str,
                            "days_old": days_old,
                        })
                elif est_val is None:
                    warnings.append(f"No valuation data for: {pos.name}")

        return SnapshotPreview(
            date_str=date_str,
            total_eur=total,
            breakdown=breakdown,
            coverage_pct=coverage_pct,
            missing_pos=missing_positions,
            stale_positions=stale_positions,
            warnings=warnings,
        )

    def update_manual_position_value(
        self,
        position_id: int,
        new_value_eur: float,
        note: Optional[str] = None,
    ) -> Position:
        """
        Update the estimated_value and valuation_date for a manual position.

        Args:
            position_id: ID of position to update
            new_value_eur: New estimated value in EUR
            note: Optional note for the update

        Returns:
            Updated Position

        Raises:
            ValueError: If position not found
        """
        pos = self._positions.get(position_id)
        if pos is None:
            raise ValueError(f"Position {position_id} not found")

        # Update extra_data with new value and date
        extra = pos.extra_data or {}
        extra["estimated_value"] = new_value_eur
        extra["valuation_date"] = datetime.utcnow().isoformat()
        if note:
            extra["valuation_note"] = note

        pos.extra_data = extra

        # Save updated position
        updated = self._positions.update(pos)
        return updated

    def edit_snapshot(
        self,
        date_str: str,
        new_breakdown: Dict[str, float],
        note: Optional[str] = None,
    ) -> WealthSnapshot:
        """
        Edit an existing snapshot — update breakdown and recalculate total.

        Args:
            date_str: Date in YYYY-MM-DD format
            new_breakdown: New asset class breakdown dict {class: eur_value}
            note: Optional note/comment

        Returns:
            Updated WealthSnapshot

        Raises:
            ValueError: If snapshot for this date doesn't exist
        """
        existing = self._wealth.get_by_date(date_str)
        if existing is None:
            raise ValueError(f"No snapshot for {date_str}")

        # Recalculate total from breakdown
        new_total = sum(new_breakdown.values())

        return self._wealth.update(
            snapshot_id=existing.id,
            total_eur=new_total,
            breakdown=new_breakdown,
            note=note,
        )

    def delete_snapshot(self, date_str: str) -> None:
        """
        Delete a snapshot.

        Args:
            date_str: Date in YYYY-MM-DD format

        Raises:
            ValueError: If snapshot for this date doesn't exist
        """
        existing = self._wealth.get_by_date(date_str)
        if existing is None:
            raise ValueError(f"No snapshot for {date_str}")
        self._wealth.delete(existing.id)

    # ------------------------------------------------------------------
    # List and access
    # ------------------------------------------------------------------

    def get_latest_snapshot(self) -> Optional[WealthSnapshot]:
        """Get the most recent snapshot."""
        return self._wealth.latest()

    def list_snapshots(self, days: int = 365) -> List[WealthSnapshot]:
        """List snapshots from the last N days."""
        return self._wealth.list(days=days)

    def get_snapshot_for_date(self, date_str: str) -> Optional[WealthSnapshot]:
        """Get snapshot for a specific date (YYYY-MM-DD)."""
        return self._wealth.get_by_date(date_str)
