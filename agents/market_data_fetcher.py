"""
Market data fetcher — wraps yfinance with symbol validation, rate limiting,
and EUR conversion. This is the only module that imports yfinance.
"""

import logging
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait, FIRST_COMPLETED
from datetime import date, datetime, timezone
from typing import Optional

import yfinance as yf
import pandas as pd

from core.storage.models import DividendRecord, HistoricalPrice, PriceRecord

logger = logging.getLogger(__name__)

# Symbols: uppercase alphanumeric plus . - ^ = (covers stocks, ETFs, crypto, commodities)
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9\-\.\^=]{1,20}$")

# Currencies that are already EUR — no conversion needed
EUR_CURRENCIES = {"EUR"}

# yfinance ticker for EUR/X exchange rates, keyed by source currency
_FOREX_TICKER = "{currency}EUR=X"


class RateLimiter:
    """Token bucket: ensures a minimum gap between requests."""

    def __init__(self, calls_per_second: float = 5.0):
        self._min_interval = 1.0 / calls_per_second
        self._last_call = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            gap = self._min_interval - (now - self._last_call)
            sleep_time = max(0.0, gap)
            # Reserve the slot and release the lock before sleeping so other
            # threads can schedule their own slots concurrently.
            self._last_call = now + sleep_time
        if sleep_time > 0:
            time.sleep(sleep_time)


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
        self._rate_limiter = rate_limiter or RateLimiter()
        self._fx_cache: dict[str, float] = {}
        self._fx_cache_lock = threading.Lock()

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

        def _fetch_one(symbol: str) -> tuple[str, Optional[PriceRecord]]:
            try:
                return symbol, self._fetch_single(symbol)
            except Exception:
                return symbol, None

        with ThreadPoolExecutor(max_workers=min(20, len(valid) or 1)) as pool:
            futs = {pool.submit(_fetch_one, s): s for s in valid}
            done, not_done = futures_wait(futs, timeout=15)
            for fut in done:
                try:
                    _, record = fut.result()
                    if record:
                        records.append(record)
                    else:
                        failed.append(futs[fut])
                except Exception:
                    failed.append(futs[fut])
            for fut in not_done:
                fut.cancel()
                failed.append(futs[fut])

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

            raw_currency = getattr(ticker.fast_info, "currency", None) or ""
            is_pence = raw_currency == "GBp"
            eur_rate = self._get_eur_rate(self._detect_currency(ticker))
            records = []
            for ts, row in df.iterrows():
                close_price = row["Close"] / 100 if is_pence else row["Close"]
                close_eur = close_price * eur_rate
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

    def fetch_dividend(self, symbol: str) -> Optional[DividendRecord]:
        """
        Fetch forward annual dividend rate and yield via ticker.info (slow path).
        Returns None if no dividend data or fetch fails.
        Note: This is a heavier call than price fetches, so use sparingly.
        """
        symbol = symbol.upper().strip()
        if not validate_symbol(symbol):
            return None

        try:
            self._rate_limiter.wait()
            ticker = yf.Ticker(symbol)
            info = ticker.info

            # Extract dividend data from info
            rate_native = info.get("trailingAnnualDividendRate")
            yield_pct = info.get("trailingAnnualDividendYield")
            currency = info.get("currency", "USD").upper()

            # If no dividend data, return None (not an error — many stocks don't pay dividends)
            if rate_native is None or rate_native <= 0:
                return DividendRecord(
                    symbol=symbol,
                    rate_eur=None,
                    yield_pct=None,
                    currency=currency,
                    fetched_at=datetime.now(timezone.utc),
                )

            # GBp handling for UK pence-traded stocks
            if currency == "GBp":
                rate_native = rate_native / 100
                currency = "GBP"

            # Convert to EUR
            eur_rate = self._get_eur_rate(currency)
            rate_eur = rate_native * eur_rate

            return DividendRecord(
                symbol=symbol,
                rate_eur=round(rate_eur, 6),
                yield_pct=round(yield_pct, 6) if yield_pct else None,
                currency=currency,
                fetched_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.warning("Failed to fetch dividend for %s: %s", symbol, e)
            return None

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

        # Fetch previous close from fast_info (reuses same ticker, no extra network request)
        previous_close_eur: Optional[float] = None
        try:
            raw_prev = getattr(ticker.fast_info, "previous_close", None)
            if raw_prev and raw_prev > 0:
                if currency == "GBP":  # was GBp before conversion above
                    raw_prev = raw_prev / 100
                previous_close_eur = round(raw_prev * eur_rate, 6)
        except Exception:
            pass  # previous_close is best-effort; day_pnl will be None without it

        return PriceRecord(
            symbol=symbol,
            price_eur=round(price_eur, 6),
            currency_original=currency,
            price_original=round(price, 6),
            exchange_rate=round(eur_rate, 6),
            fetched_at=datetime.now(timezone.utc),
            previous_close_eur=previous_close_eur,
        )

    def _extract_price_and_currency(self, ticker: yf.Ticker) -> tuple:
        """Try fast_info first, then fall back to history for price."""
        try:
            info = ticker.fast_info
            price = getattr(info, "last_price", None)
            currency = getattr(info, "currency", None)
            if price and price > 0 and currency:
                return price, currency
        except Exception as e:
            logger.warning("yfinance fast_info failed for %s: %s", ticker.ticker, e)

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
        except Exception as e:
            logger.warning("yfinance history fallback failed for %s: %s", ticker.ticker, e)

        return None, None

    def _detect_currency(self, ticker: yf.Ticker) -> str:
        try:
            currency = getattr(ticker.fast_info, "currency", None)
            if currency:
                return currency.upper()
        except Exception as e:
            logger.warning("_detect_currency failed for %s, defaulting to USD: %s", ticker.ticker, e)
        return "USD"

    def _get_eur_rate(self, currency: str) -> float:
        """Return the EUR conversion rate for a given currency. Cached per session."""
        if currency in EUR_CURRENCIES:
            return 1.0
        with self._fx_cache_lock:
            if currency in self._fx_cache:
                return self._fx_cache[currency]
        rate = self._fetch_eur_rate(currency)
        with self._fx_cache_lock:
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
        except Exception as e:
            logger.warning("FX rate fetch failed for %s, defaulting to 1.0: %s", currency, e)
        # Fallback: 1.0 (no conversion) — safest default when FX unavailable
        return 1.0
