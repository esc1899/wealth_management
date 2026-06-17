"""
Wealth Snapshot Agent — orchestrates periodic snapshots of total portfolio wealth.

Snapshots track total wealth (including non-tradeable assets) over time with
asset class breakdown. The agent can also prepare snapshots by checking data
completeness and warning about stale manual valuations.
"""

from __future__ import annotations
import logging


from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List

from core.storage.market_data import MarketDataRepository
from core.storage.positions import PositionsRepository
from core.storage.wealth_snapshots import WealthSnapshotRepository
from core.storage.dividend_snapshots import DividendSnapshotRepository
from core.storage.models import WealthSnapshot, DividendSnapshot, Position
from agents.market_data_agent import MarketDataAgent
from core.asset_class_config import get_asset_class_registry
from core.currency import is_cash_unit



logger = logging.getLogger(__name__)

# Troy ounce → gram (gold/commodity quantities stored in grams, prices per troy oz)
TROY_OZ_TO_G = 31.1035


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
        dividend_repo: Optional[DividendSnapshotRepository] = None,
    ):
        self._positions = positions_repo
        self._market = market_repo
        self._wealth = wealth_repo
        self._market_data_agent = market_data_agent
        self._dividend = dividend_repo

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

        # Initialize breakdown with all asset classes (0.0 as default)
        registry = get_asset_class_registry()
        breakdown: Dict[str, float] = {ac: 0.0 for ac in registry.all_names()}

        missing_positions = []
        total = 0.0
        holdings: List[Dict] = []

        for val in valuations:
            if val.current_value_eur is None:
                missing_positions.append(val.name)
            else:
                total += val.current_value_eur
                asset_class = val.asset_class
                breakdown[asset_class] = breakdown.get(asset_class, 0) + val.current_value_eur
            holdings.append(self._holding_from_valuation(val))

        # Calculate coverage
        coverage_pct = (
            (len(valuations) - len(missing_positions)) / len(valuations) * 100
            if valuations
            else 100.0
        )

        # Create snapshot — store composition so this date can be re-priced later
        # against its actual holdings (not a future portfolio approximation).
        snapshot = self._wealth.create(
            date_str=date_str,
            total_eur=total,
            breakdown=breakdown,
            coverage_pct=coverage_pct,
            missing_pos=missing_positions if missing_positions else None,
            is_manual=is_manual,
            note=note,
            holdings=holdings,
        )

        return snapshot

    @staticmethod
    def _holding_from_valuation(val) -> Dict:
        """Serialise a PortfolioValuation into a stored snapshot holding."""
        return {
            "name": val.name,
            "ticker": val.symbol,
            "asset_class": val.asset_class,
            "quantity": val.quantity,
            "unit": val.unit,
            "price_eur": val.current_price_eur,
            "value_eur": val.current_value_eur,
            "annual_dividend_eur": val.annual_dividend_eur,
            "dividend_yield_pct": val.dividend_yield_pct,
        }

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

        # Build breakdown — initialize all asset classes with 0.0
        registry = get_asset_class_registry()
        breakdown: Dict[str, float] = {ac: 0.0 for ac in registry.all_names()}
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

    def take_dividend_snapshot(
        self,
        date_str: Optional[str] = None,
        is_manual: bool = False,
        note: Optional[str] = None,
        overwrite: bool = False,
    ) -> DividendSnapshot:
        """
        Take a snapshot of total annual dividend income (portfolio-wide, per asset class).

        Args:
            date_str: Date in YYYY-MM-DD format (default: today)
            is_manual: True if created by user/agent chat, not scheduled
            note: Optional comment
            overwrite: If True, delete existing snapshot for this date before creating new one

        Returns:
            Persisted DividendSnapshot

        Raises:
            ValueError: If dividend_repo not initialized, or snapshot exists and overwrite=False
        """
        if self._dividend is None:
            raise ValueError("Dividend snapshot repository not initialized")

        if date_str is None:
            date_str = date.today().isoformat()

        # Check if snapshot already exists
        existing = self._dividend.get_by_date(date_str)
        if existing is not None:
            if not overwrite:
                raise ValueError(f"Dividend snapshot for {date_str} already exists")
            # Delete old snapshot before creating new one
            self._dividend.delete(existing.id)

        # Get portfolio valuation to extract dividend data
        valuations = self._market_data_agent.get_portfolio_valuation(include_watchlist=False)

        # Initialize breakdown with all asset classes (0.0 as default)
        registry = get_asset_class_registry()
        breakdown: Dict[str, float] = {ac: 0.0 for ac in registry.all_names()}

        total = 0.0

        for val in valuations:
            if val.annual_dividend_eur is not None and val.annual_dividend_eur > 0:
                total += val.annual_dividend_eur
                asset_class = val.asset_class
                breakdown[asset_class] = breakdown.get(asset_class, 0) + val.annual_dividend_eur

        # For dividend snapshots, coverage is typically 100% (0 annual dividend is valid/expected)
        coverage_pct = 100.0

        # Create snapshot
        snapshot = self._dividend.create(
            date_str=date_str,
            total_eur=total,
            breakdown=breakdown,
            coverage_pct=coverage_pct,
            missing_pos=None,
            is_manual=is_manual,
            note=note,
        )

        return snapshot

    # ------------------------------------------------------------------
    # List and access
    # ------------------------------------------------------------------

    def _compute_wealth_for_date(
        self,
        date_str: str,
        positions: List[Position],
        registry,
        *,
        max_days_back: int = 5,
        fetch_if_missing: bool = False,
    ) -> tuple:
        """Compute (total_eur, breakdown, missing, approximated) for one date.

        Shared core of backfill / recalculate / rebuild. Distinguishes an exact
        historical close (max_days_back=0 hit) from a prior-date fallback so the
        caller can report honest coverage. With fetch_if_missing=True, a ticker
        whose exact date is absent triggers a one-off 1y history re-fetch before
        falling back — so a stale neighbouring price no longer masks a gap.

        `approximated` counts auto-fetch positions priced from a neighbouring day.
        """
        breakdown: Dict[str, float] = {ac: 0.0 for ac in registry.all_names()}
        total = 0.0
        missing: List[str] = []
        approximated = 0

        for pos in positions:
            cfg = registry.get(pos.asset_class)
            is_auto = cfg.auto_fetch if cfg else False

            if not is_auto:
                # Manual / non-tradeable: use stored estimated_value
                est_val = (pos.extra_data or {}).get("estimated_value")
                if est_val is not None:
                    v = float(est_val)
                    total += v
                    breakdown[pos.asset_class] = breakdown.get(pos.asset_class, 0.0) + v
                else:
                    missing.append(pos.name)
                continue

            if is_cash_unit(pos.unit) and pos.quantity is not None:
                # Cash: quantity IS the EUR value
                total += pos.quantity
                breakdown[pos.asset_class] = breakdown.get(pos.asset_class, 0.0) + pos.quantity
                continue

            if not pos.ticker or pos.quantity is None:
                missing.append(pos.name)
                continue

            # Exact-date lookup first (max_days_back=0 returns the price only on an exact hit)
            price = self._market.get_price_for_date_or_prior(pos.ticker, date_str, max_days_back=0)
            if price is None and fetch_if_missing:
                self._market_data_agent.fetch_historical_for_symbol(pos.ticker)
                price = self._market.get_price_for_date_or_prior(pos.ticker, date_str, max_days_back=0)

            is_exact = price is not None
            if price is None:
                price = self._market.get_price_for_date_or_prior(
                    pos.ticker, date_str, max_days_back=max_days_back
                )
            if price is None:
                missing.append(pos.name)
                continue
            if not is_exact:
                approximated += 1

            value = (price / TROY_OZ_TO_G) * pos.quantity if pos.unit == "g" else price * pos.quantity
            total += value
            breakdown[pos.asset_class] = breakdown.get(pos.asset_class, 0.0) + value

        return total, breakdown, missing, approximated

    def backfill_snapshots(self, days: int = 14) -> int:
        """
        Create snapshots for missing trading days using stored historical prices.
        Uses current positions as approximation (accurate when no trades occurred).
        Returns number of snapshots created.
        """
        today = date.today()
        positions = self._positions.get_portfolio()
        if not positions:
            return 0

        registry = get_asset_class_registry()

        created = 0
        for days_back in range(1, days + 1):
            target_date = today - timedelta(days=days_back)
            if target_date.weekday() >= 5:  # skip weekends
                continue
            target_str = target_date.isoformat()
            if self._wealth.get_by_date(target_str) is not None:
                continue

            total, breakdown, missing, _ = self._compute_wealth_for_date(
                target_str, positions, registry, max_days_back=3
            )
            if total <= 0:
                continue  # no data for this day (e.g. market holiday with no stored prices)

            coverage = (len(positions) - len(missing)) / len(positions) * 100
            self._wealth.create(
                date_str=target_str,
                total_eur=total,
                breakdown=breakdown,
                coverage_pct=coverage,
                missing_pos=missing if missing else None,
                is_manual=False,
                note="backfill",
            )
            created += 1

        if created:
            logger.info("Backfilled %d wealth snapshots", created)
        return created

    def _reprice_holdings(
        self, holdings: List[Dict], date_str: str, *, fetch_if_missing: bool = True
    ) -> tuple:
        """Re-price a snapshot's stored holdings with the historical price of that date.

        Uses the *recorded* quantities/composition — so an accurate snapshot is only
        ever re-priced, never re-composed from today's portfolio. Cash / manual
        positions (no ticker) keep their recorded value. Returns
        (total, breakdown, missing, approximated, updated_holdings) where the updated
        holdings carry the corrected price_eur / value_eur.
        """
        registry = get_asset_class_registry()
        breakdown: Dict[str, float] = {ac: 0.0 for ac in registry.all_names()}
        total = 0.0
        missing: List[str] = []
        approximated = 0
        updated: List[Dict] = []

        for raw in holdings:
            h = dict(raw)
            ac = h.get("asset_class")
            ticker = h.get("ticker")
            qty = h.get("quantity")

            if not ticker or qty is None:
                # Cash / manual / non-tradeable: keep the value recorded that day
                val = h.get("value_eur")
                if val is None:
                    missing.append(h.get("name"))
                else:
                    total += val
                    breakdown[ac] = breakdown.get(ac, 0.0) + val
                updated.append(h)
                continue

            price = self._market.get_price_for_date_or_prior(ticker, date_str, max_days_back=0)
            if price is None and fetch_if_missing:
                self._market_data_agent.fetch_historical_for_symbol(ticker)
                price = self._market.get_price_for_date_or_prior(ticker, date_str, max_days_back=0)
            is_exact = price is not None
            if price is None:
                price = self._market.get_price_for_date_or_prior(ticker, date_str, max_days_back=5)
            if price is None:
                missing.append(h.get("name"))
                updated.append(h)
                continue
            if not is_exact:
                approximated += 1

            value = (price / TROY_OZ_TO_G) * qty if h.get("unit") == "g" else price * qty
            h["price_eur"] = price
            h["value_eur"] = value
            total += value
            breakdown[ac] = breakdown.get(ac, 0.0) + value
            updated.append(h)

        return total, breakdown, missing, approximated, updated

    def recalculate_snapshot(self, date_str: str) -> Optional[WealthSnapshot]:
        """
        Recalculate an existing snapshot. If the snapshot stored its composition
        (holdings), re-price exactly those holdings for the date — accurate even if
        the portfolio has since changed. Legacy snapshots without holdings fall back
        to an approximation using today's portfolio (note="recalculated"), forcing a
        1y re-fetch when the exact date is missing. Returns the updated snapshot.
        """
        existing = self._wealth.get_by_date(date_str)

        if existing is not None and existing.holdings:
            total, breakdown, missing, _, updated = self._reprice_holdings(
                existing.holdings, date_str
            )
            if total <= 0:
                return None
            denom = len(existing.holdings) or 1
            coverage = (denom - len(missing)) / denom * 100
            self._wealth.delete(existing.id)
            return self._wealth.create(
                date_str=date_str, total_eur=total, breakdown=breakdown,
                coverage_pct=coverage, missing_pos=missing or None,
                is_manual=True, note="repriced", holdings=updated,
            )

        # Legacy fallback: no stored composition → approximate with current holdings
        positions = self._positions.get_portfolio()
        if not positions:
            return None
        registry = get_asset_class_registry()
        total, breakdown, missing, _ = self._compute_wealth_for_date(
            date_str, positions, registry, fetch_if_missing=True
        )
        if total <= 0:
            return None
        coverage = (len(positions) - len(missing)) / len(positions) * 100
        if existing is not None:
            self._wealth.delete(existing.id)
        return self._wealth.create(
            date_str=date_str, total_eur=total, breakdown=breakdown,
            coverage_pct=coverage, missing_pos=missing if missing else None,
            is_manual=True, note="recalculated",
        )

    def rebuild_wealth_history(self, refetch: bool = True) -> Dict:
        """
        Rebuild wealth snapshots from fresh market data — holdings-aware.

        Only snapshots that stored their composition (holdings) are re-priced, using
        the *recorded* quantities so the result stays truthful even after portfolio
        changes. Legacy snapshots without holdings are left untouched (reported under
        ``skipped_legacy``) because they cannot be reconstructed accurately. Re-fetches
        prices + 1y history (and dividends) once, then refreshes today's snapshot.

        Returns {recomputed, skipped_legacy, low_coverage_dates, missing_dates, failed}.
        """
        summary: Dict = {
            "recomputed": 0,
            "skipped_legacy": [],
            "low_coverage_dates": [],
            "missing_dates": [],
            "failed": [],
        }

        if refetch:
            result = self._market_data_agent.fetch_all_now(
                fetch_history=True, include_watchlist=False
            )
            summary["failed"] = list(result.failed)
            try:
                self._market_data_agent.fetch_dividends_now()
            except Exception:
                logger.warning("rebuild: dividend re-fetch failed", exc_info=True)

        today = date.today().isoformat()
        for snap in self._wealth.list(days=None) or []:
            if snap.date == today:
                continue  # handled by take_snapshot below
            if not snap.holdings:
                summary["skipped_legacy"].append(snap.date)
                continue
            total, breakdown, missing, _, updated = self._reprice_holdings(
                snap.holdings, snap.date
            )
            if total <= 0:
                summary["missing_dates"].append(snap.date)
                continue
            denom = len(snap.holdings) or 1
            coverage = (denom - len(missing)) / denom * 100
            existing = self._wealth.get_by_date(snap.date)
            if existing is not None:
                self._wealth.delete(existing.id)
            self._wealth.create(
                date_str=snap.date, total_eur=total, breakdown=breakdown,
                coverage_pct=coverage, missing_pos=missing or None,
                is_manual=True, note="repriced", holdings=updated,
            )
            summary["recomputed"] += 1
            if coverage < 100.0:
                summary["low_coverage_dates"].append(snap.date)

        # Refresh today's live snapshot + dividend snapshot from current prices.
        try:
            self.take_snapshot(is_manual=True, overwrite=True)
            summary["recomputed"] += 1
            if self._dividend is not None:
                self.take_dividend_snapshot(is_manual=True, overwrite=True)
        except Exception:
            logger.warning("rebuild: today's snapshot failed", exc_info=True)

        logger.info(
            "Rebuilt wealth history: %d repriced, %d legacy skipped, %d low coverage, %d no data",
            summary["recomputed"], len(summary["skipped_legacy"]),
            len(summary["low_coverage_dates"]), len(summary["missing_dates"]),
        )
        return summary

    def get_latest_snapshot(self) -> Optional[WealthSnapshot]:
        """Get the most recent snapshot."""
        return self._wealth.latest()

    def list_snapshots(self, days: int = 365) -> List[WealthSnapshot]:
        """List snapshots from the last N days."""
        return self._wealth.list(days=days)

    def get_snapshot_for_date(self, date_str: str) -> Optional[WealthSnapshot]:
        """Get snapshot for a specific date (YYYY-MM-DD)."""
        return self._wealth.get_by_date(date_str)
