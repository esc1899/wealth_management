"""
Market Data Agent — orchestrates price fetching, storage, and scheduling.
"""

from __future__ import annotations
import logging


from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from agents.market_data_fetcher import MarketDataFetcher
from core.asset_class_config import get_asset_class_registry
from core.currency import is_cash_unit
from core.storage.base import build_encryption_service, get_connection, init_db, migrate_db
from core.storage.market_data import MarketDataRepository
from core.storage.positions import PositionsRepository



logger = logging.getLogger(__name__)
@dataclass
class FetchResult:
    fetched: int = 0
    failed: list[str] = field(default_factory=list)
    history_fetched: int = 0
    started_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def success(self) -> bool:
        return self.fetched > 0


@dataclass
class PortfolioValuation:
    symbol: str
    name: str
    asset_class: str
    investment_type: str
    quantity: Optional[float]
    unit: str
    purchase_price_eur: Optional[float]
    current_price_eur: Optional[float]
    current_value_eur: Optional[float]
    cost_basis_eur: Optional[float]
    pnl_eur: Optional[float]
    pnl_pct: Optional[float]
    fetched_at: Optional[datetime]
    day_pnl_eur: Optional[float] = None   # today vs. previous close
    day_pnl_pct: Optional[float] = None
    in_portfolio: bool = True
    in_watchlist: bool = False
    annual_dividend_eur: Optional[float] = None  # calculated: rate_eur × quantity
    dividend_yield_pct: Optional[float] = None   # from dividend_data or extra_data
    dividend_source: Optional[str] = None        # "yfinance", "festgeld", "anleihe", None


class MarketDataAgent:
    def __init__(
        self,
        positions_repo: PositionsRepository,
        market_repo: MarketDataRepository,
        fetcher: MarketDataFetcher,
        db_path: str,
        encryption_key: str,
    ):
        self._positions = positions_repo
        self._market = market_repo
        self._fetcher = fetcher
        self._db_path = db_path
        self._encryption_key = encryption_key
        self._post_fetch_callback: Optional[Callable[[], None]] = None

    def set_post_fetch_callback(self, callback: Callable[[], None]) -> None:
        """Register an optional callback to be invoked after fetch_all_now() completes."""
        self._post_fetch_callback = callback

    # ------------------------------------------------------------------
    # On-demand fetch
    # ------------------------------------------------------------------

    def fetch_all_now(self, fetch_history: bool = False) -> FetchResult:
        result = FetchResult()

        # Only fetch prices for asset classes with auto_fetch=True
        registry = get_asset_class_registry()
        auto_fetch_classes = set(registry.auto_fetch_names())

        all_positions = self._positions.get_portfolio() + self._positions.get_watchlist()
        symbols = list({
            p.ticker.upper()
            for p in all_positions
            if p.ticker and p.asset_class in auto_fetch_classes
        })

        if not symbols:
            return result

        records, failed = self._fetcher.fetch_current_prices(symbols)
        result.failed = failed

        for record in records:
            self._market.upsert_price(record)
            result.fetched += 1

        if fetch_history:
            for symbol in symbols:
                history = self._fetcher.fetch_historical(symbol, period="1y")
                for h in history:
                    self._market.upsert_historical(h)
                result.history_fetched += len(history)

        # Invoke post-fetch callback if registered (e.g., automatic wealth snapshot)
        if self._post_fetch_callback:
            try:
                self._post_fetch_callback()
            except Exception:
                logger.warning("Post-fetch callback failed", exc_info=True)

        return result

    def fetch_dividends_now(self, symbols: Optional[list[str]] = None) -> dict[str, str]:
        """
        Fetch dividend data for given symbols (or all auto-fetch symbols if None).
        Returns {symbol: error_message} for failures, empty dict if all successful.
        """
        if symbols is None:
            # Fetch for all auto-fetch asset classes
            registry = get_asset_class_registry()
            auto_fetch_classes = set(registry.auto_fetch_names())

            all_positions = self._positions.get_portfolio() + self._positions.get_watchlist()
            symbols = list({
                p.ticker.upper()
                for p in all_positions
                if p.ticker and p.asset_class in auto_fetch_classes
            })

        errors = {}
        for symbol in symbols:
            try:
                dividend_record = self._fetcher.fetch_dividend(symbol)
                if dividend_record:
                    self._market.upsert_dividend(dividend_record)
                else:
                    errors[symbol] = "No dividend data returned"
            except Exception as e:
                errors[symbol] = str(e)

        return errors

    # ------------------------------------------------------------------
    # Portfolio valuation
    # ------------------------------------------------------------------

    def get_portfolio_valuation(self, include_watchlist: bool = False) -> list[PortfolioValuation]:
        """Join positions with current prices. Set include_watchlist=True to include watchlist entries."""
        positions = self._positions.get_portfolio()
        if include_watchlist:
            positions = positions + self._positions.get_watchlist()
        valuations = []

        registry = get_asset_class_registry()
        dividend_records = self._market.get_all_dividends()

        for pos in positions:
            cfg = registry.get(pos.asset_class)
            is_auto_fetch = cfg.auto_fetch if cfg else True

            # Initialize dividend fields
            annual_dividend_eur = None
            dividend_yield_pct = None
            dividend_source = None

            if not is_auto_fetch:
                # Manual valuation: use estimated_value from extra_data, or cost basis
                extra = pos.extra_data or {}
                est_val = extra.get("estimated_value")

                if est_val is not None:
                    current_value = float(est_val)
                    current_price = (current_value / pos.quantity) if pos.quantity else current_value
                elif pos.purchase_price is not None and pos.quantity is not None:
                    current_value = pos.purchase_price * pos.quantity
                    current_price = pos.purchase_price
                elif pos.purchase_price is not None:
                    current_value = pos.purchase_price
                    current_price = pos.purchase_price
                elif is_cash_unit(pos.unit) and pos.quantity is not None:
                    # Bargeld: quantity IS the value in the base currency
                    current_value = float(pos.quantity)
                    current_price = 1.0
                else:
                    current_value = None
                    current_price = None

                cost_basis = (
                    pos.purchase_price * pos.quantity
                    if pos.purchase_price is not None and pos.quantity is not None
                    else pos.purchase_price
                )
                pnl_eur = (
                    (current_value - cost_basis)
                    if current_value is not None and cost_basis is not None
                    else None
                )
                pnl_pct = (
                    (pnl_eur / cost_basis * 100)
                    if pnl_eur is not None and cost_basis is not None and cost_basis > 0
                    else None
                )

                # Calculate dividends: override > interest_rate for Festgeld/Anleihe
                override_yield = extra.get("dividend_yield_override") if extra else None
                if override_yield is not None:
                    try:
                        rate_float = float(override_yield)
                        valuation_base = current_value if current_value is not None else cost_basis
                        if valuation_base is not None:
                            annual_dividend_eur = valuation_base * rate_float / 100
                        dividend_yield_pct = rate_float / 100
                        dividend_source = "override"
                    except (ValueError, TypeError):
                        pass
                elif pos.asset_class in {"Festgeld", "Anleihe"} and extra:
                    rate = extra.get("interest_rate")
                    if rate is not None and current_value is not None:
                        try:
                            rate_float = float(rate)
                            annual_dividend_eur = current_value * rate_float / 100
                            dividend_yield_pct = rate_float / 100
                            dividend_source = "festgeld" if pos.asset_class == "Festgeld" else "anleihe"
                        except (ValueError, TypeError):
                            pass

                valuations.append(PortfolioValuation(
                    symbol=pos.ticker or pos.name[:10],
                    name=pos.name,
                    asset_class=pos.asset_class,
                    investment_type=pos.investment_type,
                    quantity=pos.quantity,
                    unit=pos.unit,
                    purchase_price_eur=pos.purchase_price,
                    current_price_eur=current_price,
                    current_value_eur=current_value,
                    cost_basis_eur=cost_basis,
                    pnl_eur=pnl_eur,
                    pnl_pct=pnl_pct,
                    fetched_at=None,
                    in_portfolio=pos.in_portfolio,
                    in_watchlist=pos.in_watchlist,
                    annual_dividend_eur=annual_dividend_eur,
                    dividend_yield_pct=dividend_yield_pct,
                    dividend_source=dividend_source,
                ))
                continue

            if not pos.ticker:
                continue  # skip auto-fetch positions pending ticker resolution

            price_record = self._market.get_price(pos.ticker)
            current_price = price_record.price_eur if price_record else None

            # Edelmetall in Gramm: Preis ist per Troy Oz, Menge in g → umrechnen
            TROY_OZ_TO_G = 31.1035
            if pos.unit == "g" and current_price and pos.quantity:
                current_value = (current_price / TROY_OZ_TO_G) * pos.quantity
            else:
                current_value = current_price * pos.quantity if current_price and pos.quantity else None

            if pos.unit == "g" and pos.purchase_price and pos.quantity:
                cost_basis = pos.purchase_price * pos.quantity
            else:
                cost_basis = pos.purchase_price * pos.quantity if pos.purchase_price and pos.quantity else None
            pnl_eur = (current_value - cost_basis) if current_value is not None and cost_basis is not None else None
            pnl_pct = (pnl_eur / cost_basis * 100) if pnl_eur is not None and cost_basis is not None and cost_basis > 0 else None

            # Daily P&L: current price vs. previous historical close
            prev_close = self._market.get_prev_close(pos.ticker)
            if current_price is not None and prev_close is not None and pos.quantity is not None:
                if pos.unit == "g":
                    prev_value = (prev_close / TROY_OZ_TO_G) * pos.quantity
                else:
                    prev_value = prev_close * pos.quantity
                day_pnl_eur: Optional[float] = current_value - prev_value if current_value is not None else None
                day_pnl_pct: Optional[float] = (day_pnl_eur / prev_value * 100) if day_pnl_eur is not None and prev_value > 0 else None
            else:
                day_pnl_eur = None
                day_pnl_pct = None

            # Calculate dividends: override > yfinance
            extra = pos.extra_data or {}
            override_yield = extra.get("dividend_yield_override")
            if override_yield is not None:
                try:
                    rate_float = float(override_yield)
                    valuation_base = current_value if current_value is not None else cost_basis
                    if valuation_base is not None:
                        annual_dividend_eur = valuation_base * rate_float / 100
                    dividend_yield_pct = rate_float / 100
                    dividend_source = "override"
                except (ValueError, TypeError):
                    pass
            elif pos.ticker in dividend_records:
                div_record = dividend_records[pos.ticker]
                if div_record.rate_eur is not None and pos.quantity is not None:
                    annual_dividend_eur = div_record.rate_eur * pos.quantity
                    dividend_yield_pct = div_record.yield_pct
                    dividend_source = "yfinance"

            valuations.append(PortfolioValuation(
                symbol=pos.ticker,
                name=pos.name,
                asset_class=pos.asset_class,
                investment_type=pos.investment_type,
                quantity=pos.quantity,
                unit=pos.unit,
                purchase_price_eur=pos.purchase_price,
                current_price_eur=current_price,
                current_value_eur=current_value,
                cost_basis_eur=cost_basis,
                pnl_eur=pnl_eur,
                pnl_pct=pnl_pct,
                fetched_at=price_record.fetched_at if price_record else None,
                day_pnl_eur=day_pnl_eur,
                day_pnl_pct=day_pnl_pct,
                in_portfolio=pos.in_portfolio,
                in_watchlist=pos.in_watchlist,
                annual_dividend_eur=annual_dividend_eur,
                dividend_yield_pct=dividend_yield_pct,
                dividend_source=dividend_source,
            ))

        return valuations

    def get_total_value_eur(self) -> Optional[float]:
        values = [v.current_value_eur for v in self.get_portfolio_valuation() if v.current_value_eur is not None]
        return sum(values) if values else None

    # ------------------------------------------------------------------
    # Public data access methods (eliminates private _market access from pages)
    # ------------------------------------------------------------------

    def get_latest_fetch_time(self) -> Optional[datetime]:
        """Return the most recent market data fetch timestamp."""
        return self._market.get_latest_fetch_time()

    def get_historical(self, symbol: str, days: int = 365) -> list:
        """Return historical price records for a symbol (default last 365 days)."""
        return self._market.get_historical(symbol, days=days)

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    def setup_scheduler(self, fetch_hour: int = 18, timezone: str = "Europe/Berlin") -> BackgroundScheduler:
        scheduler = BackgroundScheduler(timezone=timezone)
        scheduler.add_job(
            func=self._scheduled_fetch,
            trigger=CronTrigger(hour=fetch_hour, minute=0, timezone=timezone),
            id="daily_market_fetch",
            replace_existing=True,
        )
        return scheduler

    def _scheduled_fetch(self) -> None:
        conn = get_connection(self._db_path)
        init_db(conn)
        migrate_db(conn)
        enc = build_encryption_service(self._encryption_key, "data/salt.bin")
        market_repo = MarketDataRepository(conn)
        positions_repo = PositionsRepository(conn, enc)

        agent = MarketDataAgent(
            positions_repo=positions_repo,
            market_repo=market_repo,
            fetcher=self._fetcher,
            db_path=self._db_path,
            encryption_key=self._encryption_key,
        )
        agent.fetch_all_now(fetch_history=True)

        # Automatically take wealth and dividend snapshots after scheduled fetch
        try:
            from core.storage.wealth_snapshots import WealthSnapshotRepository
            from core.storage.dividend_snapshots import DividendSnapshotRepository
            from agents.wealth_snapshot_agent import WealthSnapshotAgent

            snap_repo = WealthSnapshotRepository(conn)
            div_repo = DividendSnapshotRepository(conn)
            snap_agent = WealthSnapshotAgent(positions_repo, market_repo, snap_repo, agent, div_repo)
            snap_agent.take_snapshot(is_manual=False, overwrite=False)
            snap_agent.take_dividend_snapshot(is_manual=False, overwrite=False)
        except ValueError:
            pass  # Snapshot for today already exists — ok
        except Exception:
            logger.warning("Post-fetch snapshot failed", exc_info=True)

        conn.close()
