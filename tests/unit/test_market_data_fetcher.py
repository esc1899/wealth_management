"""
Unit tests for MarketDataFetcher — all yfinance calls are mocked.
No network access in this test suite.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from agents.market_data_fetcher import (
    MarketDataFetcher,
    RateLimiter,
    validate_symbol,
)


# ------------------------------------------------------------------
# Symbol validation
# ------------------------------------------------------------------

class TestValidateSymbol:
    def test_valid_stock(self):
        assert validate_symbol("AAPL") is True

    def test_valid_stock_with_dot(self):
        assert validate_symbol("BRK.B") is True

    def test_valid_etf_exchange_suffix(self):
        assert validate_symbol("VWCE.DE") is True

    def test_valid_crypto(self):
        assert validate_symbol("BTC-USD") is True

    def test_valid_commodity(self):
        assert validate_symbol("GC=F") is True

    def test_valid_index(self):
        assert validate_symbol("^GSPC") is True

    def test_invalid_too_long(self):
        assert validate_symbol("A" * 21) is False

    def test_invalid_empty(self):
        assert validate_symbol("") is False

    def test_invalid_semicolon(self):
        assert validate_symbol("A;DROP") is False

    def test_invalid_space(self):
        assert validate_symbol("AAPL MSFT") is False

    def test_invalid_slash(self):
        assert validate_symbol("../../etc") is False

    def test_lowercase_auto_uppercased(self):
        # validate_symbol normalises to uppercase internally
        assert validate_symbol("aapl") is True


# ------------------------------------------------------------------
# RateLimiter
# ------------------------------------------------------------------

class TestRateLimiter:
    def test_wait_called_on_second_request(self):
        limiter = RateLimiter(calls_per_second=1000)  # very fast
        # Should not raise
        limiter.wait()
        limiter.wait()

    @patch("agents.market_data_fetcher.time.sleep")
    def test_slow_rate_triggers_sleep(self, mock_sleep):
        limiter = RateLimiter(calls_per_second=0.001)  # very slow
        limiter.wait()  # first call — no sleep
        limiter.wait()  # second call — must sleep
        assert mock_sleep.call_count >= 1


# ------------------------------------------------------------------
# fetch_current_prices
# ------------------------------------------------------------------

def _make_fast_info(price: float = 150.0, currency: str = "USD"):
    info = MagicMock()
    info.last_price = price
    info.currency = currency
    return info


def _make_fx_fast_info(rate: float = 0.92):
    info = MagicMock()
    info.last_price = rate
    info.currency = "EUR"
    return info


class TestFetchCurrentPrices:
    @patch("agents.market_data_fetcher.yf.Ticker")
    def test_eur_asset_no_conversion(self, mock_ticker_cls):
        ticker = MagicMock()
        ticker.fast_info = _make_fast_info(price=100.0, currency="EUR")
        mock_ticker_cls.return_value = ticker

        fetcher = MarketDataFetcher(RateLimiter(calls_per_second=1000))
        records, failed = fetcher.fetch_current_prices(["VWCE.DE"])

        assert len(records) == 1
        assert records[0].price_eur == 100.0
        assert records[0].exchange_rate == 1.0
        assert failed == []

    @patch("agents.market_data_fetcher.yf.Ticker")
    def test_usd_asset_converted_to_eur(self, mock_ticker_cls):
        def side_effect(symbol):
            m = MagicMock()
            if symbol == "AAPL":
                m.fast_info = _make_fast_info(price=162.0, currency="USD")
            else:  # USDEUR=X
                m.fast_info = _make_fx_fast_info(rate=0.92)
            return m

        mock_ticker_cls.side_effect = side_effect

        fetcher = MarketDataFetcher(RateLimiter(calls_per_second=1000))
        records, failed = fetcher.fetch_current_prices(["AAPL"])

        assert len(records) == 1
        assert abs(records[0].price_eur - 162.0 * 0.92) < 0.01
        assert failed == []

    def test_invalid_symbol_rejected_immediately(self):
        fetcher = MarketDataFetcher(RateLimiter(calls_per_second=1000))
        with patch("agents.market_data_fetcher.yf.Ticker") as mock_ticker:
            records, failed = fetcher.fetch_current_prices(["A;INJECT"])
            mock_ticker.assert_not_called()
            assert "A;INJECT" in failed

    @patch("agents.market_data_fetcher.yf.Ticker")
    def test_failed_symbol_in_failed_list(self, mock_ticker_cls):
        ticker = MagicMock()
        ticker.fast_info = _make_fast_info(price=None, currency=None)
        ticker.fast_info.last_price = None
        mock_ticker_cls.return_value = ticker

        fetcher = MarketDataFetcher(RateLimiter(calls_per_second=1000))
        records, failed = fetcher.fetch_current_prices(["BADTICKER"])
        assert "BADTICKER" in failed

    @patch("agents.market_data_fetcher.yf.Ticker")
    def test_exception_adds_to_failed(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("network error")
        fetcher = MarketDataFetcher(RateLimiter(calls_per_second=1000))
        records, failed = fetcher.fetch_current_prices(["AAPL"])
        assert "AAPL" in failed
        assert records == []

    @patch("agents.market_data_fetcher.yf.Ticker")
    def test_exchange_rate_cached(self, mock_ticker_cls):
        """FX ticker should be called only once even for multiple USD symbols."""
        call_count = {"fx": 0}

        def side_effect(symbol):
            m = MagicMock()
            if symbol in ("AAPL", "MSFT"):
                m.fast_info = _make_fast_info(price=150.0, currency="USD")
            else:
                call_count["fx"] += 1
                m.fast_info = _make_fx_fast_info(rate=0.92)
            return m

        mock_ticker_cls.side_effect = side_effect

        fetcher = MarketDataFetcher(RateLimiter(calls_per_second=1000))
        fetcher.fetch_current_prices(["AAPL", "MSFT"])
        assert call_count["fx"] == 1


# ------------------------------------------------------------------
# fetch_historical
# ------------------------------------------------------------------

class TestFetchHistorical:
    @patch("agents.market_data_fetcher.yf.Ticker")
    def test_returns_historical_records(self, mock_ticker_cls):
        ticker = MagicMock()
        ticker.fast_info = _make_fast_info(currency="EUR")
        df = pd.DataFrame(
            {"Close": [100.0, 101.0, 102.0], "Volume": [1_000_000, 1_100_000, 900_000]},
            index=pd.to_datetime(["2024-01-10", "2024-01-11", "2024-01-12"]),
        )
        ticker.history.return_value = df
        mock_ticker_cls.return_value = ticker

        fetcher = MarketDataFetcher(RateLimiter(calls_per_second=1000))
        history = fetcher.fetch_historical("VWCE.DE", period="1mo")

        assert len(history) == 3
        assert history[0].close_eur == 100.0
        assert history[0].date == date(2024, 1, 10)

    @patch("agents.market_data_fetcher.yf.Ticker")
    def test_empty_dataframe_returns_empty_list(self, mock_ticker_cls):
        ticker = MagicMock()
        ticker.fast_info = _make_fast_info(currency="EUR")
        ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = ticker

        fetcher = MarketDataFetcher(RateLimiter(calls_per_second=1000))
        assert fetcher.fetch_historical("AAPL") == []

    def test_invalid_symbol_returns_empty_list(self):
        fetcher = MarketDataFetcher(RateLimiter(calls_per_second=1000))
        with patch("agents.market_data_fetcher.yf.Ticker") as mock_ticker:
            result = fetcher.fetch_historical("A;BAD")
            mock_ticker.assert_not_called()
            assert result == []

    @patch("agents.market_data_fetcher.yf.Ticker")
    def test_exception_returns_empty_list(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("timeout")
        fetcher = MarketDataFetcher(RateLimiter(calls_per_second=1000))
        assert fetcher.fetch_historical("AAPL") == []
