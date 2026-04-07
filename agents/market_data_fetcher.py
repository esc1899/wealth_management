"""
Market data fetcher — wraps yfinance with symbol validation, rate limiting,
and EUR conversion. This is the only module that imports yfinance.
"""

import re
import time
import threading
from datetime import date, datetime, timezone
from typing import Optional

import yfinance as yf
import pandas as pd

from core.storage.models import HistoricalPrice, PriceRecord

# Symbols: uppercase alphanumeric plus . - ^ = (covers stocks, ETFs, crypto, commodities)
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9\-\.\^=]{1,20}$")

# Currencies that are already EUR — no conversion needed
EUR_CURRENCIES = {"EUR"}

# yfinance ticker for EUR/X exchange rates, keyed by source currency
_FOREX_TICKER = "{currency}EUR=X"


class RateLimiter:
    """Token bucket: ensures a minimum gap between requests."""

    def __init__(self, calls_per_second: float = 2.0):
        self._min_interval = 1.0 / calls_per_second
        self._last_call = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            gap = self._min_interval - (now - self._last_call)
            if gap > 0:
                time.sleep(gap)
            self._last_call = time.monotonic()


def validate_symbol(symbol: str) -> bool:
    """Return True if symbol passes format validation."""
    return bool(SYMBOL_PATTERN.match(symbol.upper().strip()))


class MarketDataFetcher:
    """
    Fetches current and historical prices via yfinance.
    All prices are returned in EUR.
    Thread-safe via the RateLimiter.
    """

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self._rate_limiter = rate_limiter or RateLimiter(calls_per_second=2.0)
        self._fx_cache: dict[str, float] = {}  # currency -> EUR rate, per instance

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def fetch_current_prices(
        self, symbols: list[str]
    ) -> tuple[list[PriceRecord], list[str]]:
        """
        Fetch current prices for a list of symbols.
        Returns (successful_records, failed_symbols).
        Invalid symbols are rejected immediately without a network call.
        """
        valid = [s.upper().strip() for s in symbols if validate_symbol(s)]
        invalid = [s for s in symbols if not validate_symbol(s)]
        if invalid:
            # Log but do not raise — partial success is acceptable
            pass

        records: list[PriceRecord] = []
        failed: list[str] = list(invalid)

        for symbol in valid:
            try:
                record = self._fetch_single(symbol)
                if record:
                    records.append(record)
                else:
                    failed.append(symbol)
            except Exception:
                failed.append(symbol)

        return records, failed

    def fetch_historical(
        self, symbol: str, period: str = "1y"
    ) -> list[HistoricalPrice]:
        """
        Fetch daily closing prices for a symbol.
        period uses yfinance notation: 1y, 6mo, 3mo, 1mo, 5d, etc.
        Returns empty list on any error.
        """
        symbol = symbol.upper().strip()
        if not validate_symbol(symbol):
            return []

        try:
            self._rate_limiter.wait()
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval="1d")
            if df.empty:
                return []

            eur_rate = self._get_eur_rate(self._detect_currency(ticker))
            records = []
            for ts, row in df.iterrows():
                close_eur = row["Close"] * eur_rate
                if close_eur <= 0:
                    continue
                records.append(
                    HistoricalPrice(
                        symbol=symbol,
                        date=ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10]),
                        close_eur=round(close_eur, 6),
                        volume=int(row["Volume"]) if pd.notna(row.get("Volume")) else None,
                    )
                )
            return records
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_single(self, symbol: str) -> Optional[PriceRecord]:
        self._rate_limiter.wait()
        ticker = yf.Ticker(symbol)

        # Try fast_info first, fall back to regular info
        price, currency = self._extract_price_and_currency(ticker)

        if price is None or price <= 0 or currency is None:
            return None

        # yfinance reports UK pence-traded stocks with currency="GBp" (lowercase p).
        # The price is in pence — divide by 100 to get GBP before EUR conversion.
        if currency == "GBp":
            price = price / 100
            currency = "GBP"

        currency = currency.upper()
        eur_rate = self._get_eur_rate(currency)
        price_eur = price * eur_rate

        return PriceRecord(
            symbol=symbol,
            price_eur=round(price_eur, 6),
            currency_original=currency,
            price_original=round(price, 6),
            exchange_rate=round(eur_rate, 6),
            fetched_at=datetime.now(timezone.utc),
        )

    def _extract_price_and_currency(self, ticker: yf.Ticker) -> tuple:
        """Try fast_info first, then fall back to history for price."""
        try:
            info = ticker.fast_info
            price = getattr(info, "last_price", None)
            currency = getattr(info, "currency", None)
            if price and price > 0 and currency:
                return price, currency
        except Exception:
            pass

        # Fallback: use last close from recent history
        try:
            hist = ticker.history(period="5d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                currency = getattr(ticker.fast_info, "currency", None)
                if not currency:
                    # Try info dict (slower but more complete)
                    info_dict = ticker.info
                    currency = info_dict.get("currency")
                return price, currency
        except Exception:
            pass

        return None, None

    def _detect_currency(self, ticker: yf.Ticker) -> str:
        try:
            currency = getattr(ticker.fast_info, "currency", None)
            if currency:
                return currency.upper()
        except Exception:
            pass
        return "USD"

    def _get_eur_rate(self, currency: str) -> float:
        """Return the EUR conversion rate for a given currency. Cached per session."""
        if currency in EUR_CURRENCIES:
            return 1.0
        if currency in self._fx_cache:
            return self._fx_cache[currency]

        rate = self._fetch_eur_rate(currency)
        self._fx_cache[currency] = rate
        return rate

    def _fetch_eur_rate(self, currency: str) -> float:
        """Fetch live EUR/currency rate from yfinance. Falls back to 1.0 on error."""
        try:
            self._rate_limiter.wait()
            ticker_symbol = _FOREX_TICKER.format(currency=currency)
            fx = yf.Ticker(ticker_symbol)
            rate = getattr(fx.fast_info, "last_price", None)
            if rate and rate > 0:
                return float(rate)
        except Exception:
            pass
        # Fallback: 1.0 (no conversion) — safest default when FX unavailable
        return 1.0
