"""
Market data repository — CRUD for current prices and historical closes.
Public market data is NOT encrypted (no privacy benefit for public data).
"""

import sqlite3
from datetime import date, datetime
from typing import Optional

from core.storage.models import DividendRecord, HistoricalPrice, PriceRecord


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
                (symbol, price_eur, currency_original, price_original, exchange_rate, fetched_at, previous_close_eur)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                price_eur           = excluded.price_eur,
                currency_original   = excluded.currency_original,
                price_original      = excluded.price_original,
                exchange_rate       = excluded.exchange_rate,
                fetched_at          = excluded.fetched_at,
                previous_close_eur  = excluded.previous_close_eur
            """,
            (
                record.symbol,
                record.price_eur,
                record.currency_original,
                record.price_original,
                record.exchange_rate,
                record.fetched_at.isoformat(),
                record.previous_close_eur,
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
        """Insert or update historical close price (overwrites existing for same symbol+date)."""
        cursor = self._conn.execute(
            """
            INSERT OR REPLACE INTO historical_prices (symbol, date, close_eur, volume)
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

    def get_price_for_date_or_prior(self, symbol: str, date_str: str, max_days_back: int = 5) -> Optional[float]:
        """Return closing price for exact date, or the closest prior date within max_days_back days."""
        row = self._conn.execute(
            """
            SELECT close_eur FROM historical_prices
            WHERE symbol = ? AND date <= ? AND date >= date(?, '-' || ? || ' days')
            ORDER BY date DESC LIMIT 1
            """,
            (symbol.upper(), date_str, date_str, max_days_back),
        ).fetchone()
        return float(row["close_eur"]) if row else None

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

    def get_prev_close(self, symbol: str) -> Optional[float]:
        """Return the most recent historical closing price strictly before today.

        Used to compute daily P&L (current_price vs. last exchange close).
        Returns None if no such data point exists.
        """
        row = self._conn.execute(
            """
            SELECT close_eur FROM historical_prices
            WHERE symbol = ? AND date < date('now')
            ORDER BY date DESC
            LIMIT 1
            """,
            (symbol.upper(),),
        ).fetchone()
        return float(row["close_eur"]) if row else None

    def get_price_for_date(self, symbol: str, date_str: str) -> Optional[float]:
        """Return the closing price in EUR for a symbol on a specific date. Returns None if not found."""
        row = self._conn.execute(
            "SELECT close_eur FROM historical_prices WHERE symbol = ? AND date = ?",
            (symbol.upper(), date_str),
        ).fetchone()
        return float(row["close_eur"]) if row else None

    def get_last_price_in_range(self, symbol: str, range_start: str, range_end: str) -> Optional[float]:
        """Return the last closing price in EUR for symbol within [range_start, range_end] inclusive."""
        row = self._conn.execute(
            """
            SELECT close_eur FROM historical_prices
            WHERE symbol = ? AND date BETWEEN ? AND ?
            ORDER BY date DESC LIMIT 1
            """,
            (symbol.upper(), range_start, range_end),
        ).fetchone()
        return float(row["close_eur"]) if row else None

    def get_price_near_date(self, symbol: str, date_str: str, window_days: int = 7) -> Optional[float]:
        """Return the closing price for the trading day closest to ``date_str``.

        Searches within ±``window_days`` and returns the nearest available close (ties
        resolved toward the earlier date). Used for forward-return lookups where the
        target date may fall on a weekend/holiday. Returns None if no close in window.
        """
        row = self._conn.execute(
            """
            SELECT close_eur FROM historical_prices
            WHERE symbol = ?
              AND date BETWEEN date(?, '-' || ? || ' days') AND date(?, '+' || ? || ' days')
            ORDER BY abs(julianday(date) - julianday(?)) ASC, date ASC
            LIMIT 1
            """,
            (symbol.upper(), date_str, window_days, date_str, window_days, date_str),
        ).fetchone()
        return float(row["close_eur"]) if row else None

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
    # Dividend data
    # ------------------------------------------------------------------

    def upsert_dividend(self, record: DividendRecord) -> DividendRecord:
        """Insert or replace dividend data for a symbol."""
        cursor = self._conn.execute(
            """
            INSERT INTO dividend_data (symbol, rate_eur, yield_pct, currency, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                rate_eur  = COALESCE(excluded.rate_eur, dividend_data.rate_eur),
                yield_pct = COALESCE(excluded.yield_pct, dividend_data.yield_pct),
                currency  = excluded.currency,
                fetched_at = excluded.fetched_at
            """,
            (
                record.symbol,
                record.rate_eur,
                record.yield_pct,
                record.currency,
                record.fetched_at.isoformat(),
            ),
        )
        self._conn.commit()
        return record

    def get_dividend(self, symbol: str) -> Optional[DividendRecord]:
        """Get dividend data for a single symbol."""
        row = self._conn.execute(
            "SELECT * FROM dividend_data WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
        return self._deserialize_dividend(row) if row else None

    def get_all_dividends(self) -> dict[str, DividendRecord]:
        """Get all dividend data, keyed by symbol."""
        rows = self._conn.execute(
            "SELECT * FROM dividend_data ORDER BY symbol"
        ).fetchall()
        return {row["symbol"]: self._deserialize_dividend(row) for row in rows}

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
            previous_close_eur=row["previous_close_eur"],
        )

    def _deserialize_historical(self, row: sqlite3.Row) -> HistoricalPrice:
        return HistoricalPrice(
            id=row["id"],
            symbol=row["symbol"],
            date=date.fromisoformat(row["date"]),
            close_eur=row["close_eur"],
            volume=row["volume"],
        )

    def _deserialize_dividend(self, row: sqlite3.Row) -> DividendRecord:
        return DividendRecord(
            symbol=row["symbol"],
            rate_eur=row["rate_eur"],
            yield_pct=row["yield_pct"],
            currency=row["currency"],
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
        )
