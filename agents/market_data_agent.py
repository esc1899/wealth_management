"""
Market Data Agent — orchestrates price fetching, storage, and scheduling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from agents.market_data_fetcher import MarketDataFetcher
from core.storage.base import build_encryption_service, get_connection, init_db
from core.storage.market_data import MarketDataRepository
from core.storage.positions import PositionsRepository


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
    quantity: float
    unit: str
    purchase_price_eur: Optional[float]
    current_price_eur: Optional[float]
    current_value_eur: Optional[float]
    cost_basis_eur: Optional[float]
    pnl_eur: Optional[float]
    pnl_pct: Optional[float]
    fetched_at: Optional[datetime]
    in_portfolio: bool = True


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

    # ------------------------------------------------------------------
    # On-demand fetch
    # ------------------------------------------------------------------

    def fetch_all_now(self, fetch_history: bool = False) -> FetchResult:
        result = FetchResult()
        symbols = self._positions.get_tickers_for_price_fetch()
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

        return result

    # ------------------------------------------------------------------
    # Portfolio valuation
    # ------------------------------------------------------------------

    def get_portfolio_valuation(self, include_watchlist: bool = False) -> list[PortfolioValuation]:
        """Join positions with current prices. Set include_watchlist=True to include watchlist entries."""
        positions = self._positions.get_portfolio()
        if include_watchlist:
            positions = positions + self._positions.get_watchlist()
        valuations = []

        for pos in positions:
            if not pos.ticker:
                continue  # skip positions pending ticker resolution

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
                in_portfolio=pos.in_portfolio,
            ))

        return valuations

    def get_total_value_eur(self) -> Optional[float]:
        values = [v.current_value_eur for v in self.get_portfolio_valuation() if v.current_value_eur is not None]
        return sum(values) if values else None

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
        conn.close()
