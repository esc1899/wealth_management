"""Unit tests for core/ticker_validator.py."""
from unittest.mock import MagicMock, patch

from core.ticker_validator import COMMON_SUFFIXES, validate_ticker


def _fast_info(last_price):
    fi = MagicMock()
    fi.last_price = last_price
    return fi


class TestValidateTicker:
    @patch("core.ticker_validator.yf.Ticker")
    def test_valid_ticker_returns_true(self, mock_cls):
        mock_cls.return_value.fast_info = _fast_info(150.0)
        assert validate_ticker("AAPL") is True

    @patch("core.ticker_validator.yf.Ticker")
    def test_missing_price_returns_false(self, mock_cls):
        mock_cls.return_value.fast_info = _fast_info(None)
        assert validate_ticker("NONEXISTENT") is False

    @patch("core.ticker_validator.yf.Ticker")
    def test_exception_returns_false(self, mock_cls):
        mock_cls.side_effect = Exception("network error")
        assert validate_ticker("AAPL") is False

    @patch("core.ticker_validator.yf.Ticker")
    def test_ticker_with_suffix_is_valid(self, mock_cls):
        mock_cls.return_value.fast_info = _fast_info(45.0)
        assert validate_ticker("FMG.AX") is True

    @patch("core.ticker_validator.yf.Ticker")
    def test_delisted_ticker_returns_false(self, mock_cls):
        mock_cls.return_value.fast_info = _fast_info(None)
        assert validate_ticker("SCANFL") is False


class TestCommonSuffixes:
    def test_not_empty(self):
        assert len(COMMON_SUFFIXES) >= 6

    def test_all_start_with_dot(self):
        assert all(s.startswith(".") for s in COMMON_SUFFIXES)

    def test_contains_key_suffixes(self):
        assert ".AX" in COMMON_SUFFIXES
        assert ".T" in COMMON_SUFFIXES
        assert ".OL" in COMMON_SUFFIXES
        assert ".L" in COMMON_SUFFIXES
        assert ".DE" in COMMON_SUFFIXES
