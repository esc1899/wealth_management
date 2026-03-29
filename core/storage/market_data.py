"""
Market data repository — CRUD for current prices and historical closes.
Public market data is NOT encrypted (no privacy benefit for public data).
"""

import sqlite3
from datetime import date, datetime
from typing import Optional

from core.storage.models import HistoricalPrice, PriceRecord


class MarketDataRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # Current prices
    # ------------------------------------------------------------------

    def upsert_price(self, record: PriceRecord) -> PriceRecord:
        """Insert or replace current price for a symbol."""
        cursor = self._conn.execute(
            """
            INSERT INTO current_prices
                (symbol, price_eur, currency_original, price_original, exchange_rate, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                price_eur         = excluded.price_eur,
                currency_original = excluded.currency_original,
                price_original    = excluded.price_original,
                exchange_rate     = excluded.exchange_rate,
                fetched_at        = excluded.fetched_at
            """,
            (
                record.symbol,
                record.price_eur,
                record.currency_original,
                record.price_original,
                record.exchange_rate,
                record.fetched_at.isoformat(),
            ),
        )
        self._conn.commit()
        return record.model_copy(update={"id": cursor.lastrowid})

    def get_price(self, symbol: str) -> Optional[PriceRecord]:
        row = self._conn.execute(
            "SELECT * FROM current_prices WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
        return self._deserialize_price(row) if row else None

    def get_all_prices(self) -> list[PriceRecord]:
        rows = self._conn.execute(
            "SELECT * FROM current_prices ORDER BY symbol"
        ).fetchall()
        return [self._deserialize_price(row) for row in rows]

    def get_latest_fetch_time(self) -> Optional[datetime]:
        row = self._conn.execute(
            "SELECT MAX(fetched_at) AS ts FROM current_prices"
        ).fetchone()
        if row and row["ts"]:
            return datetime.fromisoformat(row["ts"])
        return None

    # ------------------------------------------------------------------
    # Historical prices
    # ------------------------------------------------------------------

    def upsert_historical(self, record: HistoricalPrice) -> HistoricalPrice:
        """Insert historical close, ignore if already exists (history is immutable)."""
        cursor = self._conn.execute(
            """
            INSERT OR IGNORE INTO historical_prices (symbol, date, close_eur, volume)
            VALUES (?, ?, ?, ?)
            """,
            (
                record.symbol,
                record.date.isoformat(),
                record.close_eur,
                record.volume,
            ),
        )
        self._conn.commit()
        return record.model_copy(update={"id": cursor.lastrowid or None})

    def get_historical(self, symbol: str, days: int = 365) -> list[HistoricalPrice]:
        rows = self._conn.execute(
            """
            SELECT * FROM historical_prices
            WHERE symbol = ?
              AND date >= date('now', '-' || ? || ' days')
            ORDER BY date ASC
            """,
            (symbol.upper(), days),
        ).fetchall()
        return [self._deserialize_historical(row) for row in rows]

    def get_all_symbols_historical(self, days: int = 90) -> dict[str, list[HistoricalPrice]]:
        """Return historical data for all symbols, grouped by symbol."""
        rows = self._conn.execute(
            """
            SELECT * FROM historical_prices
            WHERE date >= date('now', ? || ' days')
            ORDER BY symbol, date ASC
            """,
            (f"-{days}",),
        ).fetchall()
        result: dict[str, list[HistoricalPrice]] = {}
        for row in rows:
            entry = self._deserialize_historical(row)
            result.setdefault(entry.symbol, []).append(entry)
        return result

    # ------------------------------------------------------------------
    # Deserializers
    # ------------------------------------------------------------------

    def _deserialize_price(self, row: sqlite3.Row) -> PriceRecord:
        return PriceRecord(
            id=row["id"],
            symbol=row["symbol"],
            price_eur=row["price_eur"],
            currency_original=row["currency_original"],
            price_original=row["price_original"],
            exchange_rate=row["exchange_rate"],
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
        )

    def _deserialize_historical(self, row: sqlite3.Row) -> HistoricalPrice:
        return HistoricalPrice(
            id=row["id"],
            symbol=row["symbol"],
            date=date.fromisoformat(row["date"]),
            close_eur=row["close_eur"],
            volume=row["volume"],
        )
