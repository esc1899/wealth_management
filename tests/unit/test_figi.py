"""
Unit tests for core/figi.py — OpenFIGI lookup helpers.
Network calls are mocked; no real HTTP requests.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.figi import openfigi_lookup, to_yahoo_ticker, RELEVANT_EXCH, EXCH_SUFFIX


# ---------------------------------------------------------------------------
# to_yahoo_ticker
# ---------------------------------------------------------------------------

class TestToYahooTicker:
    def test_us_ticker_no_suffix(self):
        assert to_yahoo_ticker({"ticker": "AAPL", "exchCode": "UW"}) == "AAPL"

    def test_xetra_suffix(self):
        assert to_yahoo_ticker({"ticker": "SAP", "exchCode": "GY"}) == "SAP.DE"

    def test_frankfurt_suffix(self):
        assert to_yahoo_ticker({"ticker": "SAP", "exchCode": "GF"}) == "SAP.F"

    def test_swiss_suffix(self):
        assert to_yahoo_ticker({"ticker": "LISN", "exchCode": "SW"}) == "LISN.SW"

    def test_london_suffix(self):
        assert to_yahoo_ticker({"ticker": "SHEL", "exchCode": "LN"}) == "SHEL.L"

    def test_empty_ticker_returns_empty(self):
        assert to_yahoo_ticker({"ticker": "", "exchCode": "GY"}) == ""

    def test_missing_ticker_key_returns_empty(self):
        assert to_yahoo_ticker({"exchCode": "GY"}) == ""

    def test_unknown_exchange_no_suffix(self):
        assert to_yahoo_ticker({"ticker": "XYZ", "exchCode": "ZZ"}) == "XYZ"


# ---------------------------------------------------------------------------
# openfigi_lookup — mocked HTTP
# ---------------------------------------------------------------------------

def _mock_response(data: list) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = [{"data": data}]
    return resp


def _equity(ticker: str, exch: str, sec_type: str = "Common Stock") -> dict:
    return {
        "ticker": ticker,
        "exchCode": exch,
        "marketSector": "Equity",
        "securityType": sec_type,
    }


class TestOpenfigiFilerling:
    @patch("core.figi.requests.post")
    def test_returns_equity_on_known_exchange(self, mock_post):
        mock_post.return_value = _mock_response([_equity("AAPL", "UW")])
        results = openfigi_lookup("ID_ISIN", "US0378331005")
        assert len(results) == 1
        assert results[0]["ticker"] == "AAPL"

    @patch("core.figi.requests.post")
    def test_filters_non_equity_market_sector(self, mock_post):
        mock_post.return_value = _mock_response([
            {"ticker": "AAPL", "exchCode": "UW", "marketSector": "Corp", "securityType": "Bond"},
            _equity("AAPL", "UW"),
        ])
        results = openfigi_lookup("ID_ISIN", "US0378331005")
        assert len(results) == 1

    @patch("core.figi.requests.post")
    def test_filters_unknown_exchange(self, mock_post):
        mock_post.return_value = _mock_response([
            _equity("AAPL", "UNKNOWN_EXCH"),
        ])
        results = openfigi_lookup("ID_ISIN", "US0378331005")
        assert results == []

    @patch("core.figi.requests.post")
    def test_filters_options_and_warrants(self, mock_post):
        mock_post.return_value = _mock_response([
            _equity("AAPL", "UW", "Option"),
            _equity("AAPL", "UW", "Warrant"),
            _equity("AAPL", "UW", "Common Stock"),
        ])
        results = openfigi_lookup("ID_ISIN", "US0378331005")
        assert len(results) == 1
        assert results[0]["securityType"] == "Common Stock"

    @patch("core.figi.requests.post")
    def test_deduplicates_by_exchange(self, mock_post):
        mock_post.return_value = _mock_response([
            _equity("SAP", "GY"),
            _equity("SAP", "GY"),  # duplicate exchange
        ])
        results = openfigi_lookup("ID_ISIN", "DE0007164600")
        assert len(results) == 1

    @patch("core.figi.requests.post")
    def test_keeps_multiple_exchanges(self, mock_post):
        mock_post.return_value = _mock_response([
            _equity("AMZN", "UW"),
            _equity("AMZN", "GY"),
            _equity("AMZN", "LN"),
        ])
        results = openfigi_lookup("ID_ISIN", "US0231351067")
        assert len(results) == 3

    @patch("core.figi.requests.post")
    def test_returns_empty_on_http_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=429)
        results = openfigi_lookup("ID_ISIN", "US0378331005")
        assert results == []

    @patch("core.figi.requests.post")
    def test_returns_empty_on_no_data(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.json.return_value = [{}]
        results = openfigi_lookup("ID_ISIN", "US0378331005")
        assert results == []

    @patch("core.figi.requests.post")
    def test_returns_empty_on_network_error(self, mock_post):
        mock_post.side_effect = Exception("connection refused")
        results = openfigi_lookup("ID_ISIN", "US0378331005")
        assert results == []

    @patch("core.figi.requests.post")
    def test_uppercases_input(self, mock_post):
        mock_post.return_value = _mock_response([])
        openfigi_lookup("ID_ISIN", "us0378331005")
        call_body = mock_post.call_args.kwargs["json"]
        assert call_body[0]["idValue"] == "US0378331005"
