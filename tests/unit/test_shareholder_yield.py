"""Unit tests for core/shareholder_yield.py — buyback yield from yfinance (FEAT-71)."""
from unittest.mock import MagicMock, patch

import pandas as pd

from core.shareholder_yield import buyback_yield, buyback_yield_map


def _series(values, dates=None):
    """Build a shares-outstanding pandas Series like yfinance.get_shares_full returns."""
    idx = pd.to_datetime(dates) if dates else pd.date_range("2025-04-01", periods=len(values))
    return pd.Series(values, index=idx)


class TestBuybackYield:
    @patch("core.shareholder_yield.yf.Ticker")
    def test_net_buyback_positive(self, mock_cls):
        # 100 → 95 shares = 5 % retired
        mock_cls.return_value.get_shares_full.return_value = _series([100.0, 98.0, 95.0])
        assert abs(buyback_yield("AAPL") - 0.05) < 1e-9

    @patch("core.shareholder_yield.yf.Ticker")
    def test_dilution_is_negative(self, mock_cls):
        # 100 → 110 shares = dilution → negative yield
        mock_cls.return_value.get_shares_full.return_value = _series([100.0, 110.0])
        assert buyback_yield("XYZ") < 0

    @patch("core.shareholder_yield.yf.Ticker")
    def test_empty_series_returns_none(self, mock_cls):
        mock_cls.return_value.get_shares_full.return_value = _series([])
        assert buyback_yield("AAPL") is None

    @patch("core.shareholder_yield.yf.Ticker")
    def test_single_point_returns_none(self, mock_cls):
        mock_cls.return_value.get_shares_full.return_value = _series([100.0])
        assert buyback_yield("AAPL") is None

    @patch("core.shareholder_yield.yf.Ticker")
    def test_none_series_returns_none(self, mock_cls):
        mock_cls.return_value.get_shares_full.return_value = None
        assert buyback_yield("AAPL") is None

    @patch("core.shareholder_yield.yf.Ticker")
    def test_exception_returns_none(self, mock_cls):
        mock_cls.side_effect = Exception("network error")
        assert buyback_yield("AAPL") is None

    def test_empty_ticker_returns_none(self):
        assert buyback_yield("") is None
        assert buyback_yield(None) is None

    @patch("core.shareholder_yield.yf.Ticker")
    def test_duplicate_timestamps_collapsed(self, mock_cls):
        # duplicate dates → keep last per date; unsorted input still resolves first vs last
        mock_cls.return_value.get_shares_full.return_value = _series(
            [100.0, 100.0, 90.0], dates=["2025-04-01", "2025-04-01", "2026-04-01"]
        )
        assert abs(buyback_yield("AAPL") - 0.10) < 1e-9

    @patch("core.shareholder_yield.yf.Ticker")
    def test_zero_old_count_returns_none(self, mock_cls):
        mock_cls.return_value.get_shares_full.return_value = _series([0.0, 95.0])
        assert buyback_yield("AAPL") is None


class TestBuybackYieldMap:
    @patch("core.shareholder_yield.buyback_yield")
    def test_maps_uppercased_tickers(self, mock_by):
        mock_by.side_effect = lambda t: {"AAPL": 0.05, "MSFT": 0.02}.get(t)
        result = buyback_yield_map(("aapl", "msft"))
        assert result == {"AAPL": 0.05, "MSFT": 0.02}

    @patch("core.shareholder_yield.buyback_yield")
    def test_deduplicates(self, mock_by):
        mock_by.return_value = 0.03
        result = buyback_yield_map(("AAPL", "aapl", "AAPL"))
        assert list(result.keys()) == ["AAPL"]

    def test_empty_input(self):
        assert buyback_yield_map(()) == {}
        assert buyback_yield_map((None, "")) == {}
