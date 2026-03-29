"""
Integration tests for the demo database seeder.

- Runs the seeder against an in-memory SQLite DB (no file I/O).
- Mocks yfinance so no real network calls are made.
- Verifies all 17 positions are inserted with positive quantities and prices.
- Verifies values are stored as plain strings (no encryption).
"""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers to build a minimal mock yfinance download result
# ---------------------------------------------------------------------------

def _make_df(price: float, ticker: str = "X") -> pd.DataFrame:
    """Return a single-row DataFrame mimicking yfinance download output."""
    idx = pd.DatetimeIndex(["2020-01-02"])
    return pd.DataFrame({"Close": [price]}, index=idx)


def _make_multi_df(price: float, ticker: str = "X") -> pd.DataFrame:
    """Multi-column Close (yfinance ≥0.2 style)."""
    idx = pd.DatetimeIndex(["2020-01-02"])
    cols = pd.MultiIndex.from_tuples([("Close", ticker)])
    return pd.DataFrame([[price]], index=idx, columns=cols)


MOCK_PRICES: dict[str, float] = {
    "AAPL":    60.0,
    "MSFT":   130.0,
    "AMZN":  3200.0,
    "NESN.SW": 100.0,
    "ASML":   600.0,
    "SIE.DE":  120.0,
    "TM":      140.0,
    "TSM":     100.0,
    "NVO":      80.0,
    "BABA":    220.0,
    "IWDA.AS": 58.0,
    "VWRL.AS": 88.0,
    "AGGG.L":   5.0,
    "REET":    25.0,
    "GC=F":  1850.0,
    "SI=F":    24.0,
    # FX pairs
    "EURUSD=X": 1.10,
    "GBPUSD=X": 1.28,
    "CHFUSD=X": 1.05,
}


def _mock_download(ticker: str, start=None, end=None, progress=False, auto_adjust=True, **kwargs):
    price = MOCK_PRICES.get(ticker, 100.0)
    return _make_df(price, ticker)


def _mock_fast_info(ticker: str):
    """Return a fake fast_info-like object."""
    obj = MagicMock()
    # Currency heuristic mirrors seed script
    t = ticker.upper()
    if t.endswith(".DE") or t.endswith(".AS"):
        obj.currency = "EUR"
    elif t.endswith(".SW"):
        obj.currency = "CHF"
    elif t.endswith(".L"):
        obj.currency = "GBP"
    else:
        obj.currency = "USD"
    obj.last_price = MOCK_PRICES.get(ticker, 100.0)
    return obj


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def in_memory_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDemoSeed:
    @patch("yfinance.download", side_effect=_mock_download)
    @patch("yfinance.Ticker")
    def test_all_17_positions_inserted(self, mock_ticker_cls, mock_download, in_memory_conn):
        mock_ticker_cls.return_value.fast_info = _mock_fast_info("AAPL")

        # Patch fast_info per ticker
        def _ticker_factory(t):
            m = MagicMock()
            m.fast_info = _mock_fast_info(t)
            return m

        mock_ticker_cls.side_effect = _ticker_factory

        from scripts.seed_demo import seed
        inserted = seed(conn=in_memory_conn)

        assert len(inserted) == 17, f"Expected 17 positions, got {len(inserted)}"

    @patch("yfinance.download", side_effect=_mock_download)
    @patch("yfinance.Ticker")
    def test_quantities_are_positive(self, mock_ticker_cls, mock_download, in_memory_conn):
        def _ticker_factory(t):
            m = MagicMock()
            m.fast_info = _mock_fast_info(t)
            return m

        mock_ticker_cls.side_effect = _ticker_factory

        from scripts.seed_demo import seed
        inserted = seed(conn=in_memory_conn)

        for pos in inserted:
            assert pos["quantity"] > 0, f"{pos['name']}: quantity must be > 0"

    @patch("yfinance.download", side_effect=_mock_download)
    @patch("yfinance.Ticker")
    def test_purchase_prices_are_positive(self, mock_ticker_cls, mock_download, in_memory_conn):
        def _ticker_factory(t):
            m = MagicMock()
            m.fast_info = _mock_fast_info(t)
            return m

        mock_ticker_cls.side_effect = _ticker_factory

        from scripts.seed_demo import seed
        inserted = seed(conn=in_memory_conn)

        for pos in inserted:
            assert pos["purchase_price"] > 0, f"{pos['name']}: purchase_price must be > 0"

    @patch("yfinance.download", side_effect=_mock_download)
    @patch("yfinance.Ticker")
    def test_values_stored_as_plain_strings(self, mock_ticker_cls, mock_download, in_memory_conn):
        """Verify no encryption: stored values should be parseable as plain floats."""
        def _ticker_factory(t):
            m = MagicMock()
            m.fast_info = _mock_fast_info(t)
            return m

        mock_ticker_cls.side_effect = _ticker_factory

        from scripts.seed_demo import seed
        seed(conn=in_memory_conn)

        rows = in_memory_conn.execute(
            "SELECT quantity, purchase_price FROM positions WHERE in_portfolio=1"
        ).fetchall()

        assert len(rows) == 17

        for row in rows:
            # Plain float strings must be directly parseable — Fernet tokens would fail
            qty = float(row["quantity"])
            price = float(row["purchase_price"])
            assert qty > 0
            assert price > 0

    @patch("yfinance.download", side_effect=_mock_download)
    @patch("yfinance.Ticker")
    def test_approx_value_near_10k(self, mock_ticker_cls, mock_download, in_memory_conn):
        """Each position's total value (qty * price) should be roughly €10,000."""
        def _ticker_factory(t):
            m = MagicMock()
            m.fast_info = _mock_fast_info(t)
            return m

        mock_ticker_cls.side_effect = _ticker_factory

        from scripts.seed_demo import seed
        inserted = seed(conn=in_memory_conn)

        for pos in inserted:
            total = pos["quantity"] * pos["purchase_price"]
            # Allow wider tolerance due to whole-number rounding (high-price stocks can deviate more)
            assert 8_000 <= total <= 12_000, (
                f"{pos['name']}: total value €{total:.2f} outside expected range"
            )

    @patch("yfinance.download", side_effect=_mock_download)
    @patch("yfinance.Ticker")
    def test_precious_metals_unit_conversion(self, mock_ticker_cls, mock_download, in_memory_conn):
        """Gold (Gramm) and Silber (Gramm) should have higher quantities than Troy Oz."""
        def _ticker_factory(t):
            m = MagicMock()
            m.fast_info = _mock_fast_info(t)
            return m

        mock_ticker_cls.side_effect = _ticker_factory

        from scripts.seed_demo import seed
        inserted = seed(conn=in_memory_conn)

        gold_oz  = next(p for p in inserted if p["name"] == "Gold (Unzen)")
        gold_g   = next(p for p in inserted if p["name"] == "Gold (Gramm)")
        silver_g = next(p for p in inserted if p["name"] == "Silber (Gramm)")

        # Gram positions should have more units than troy oz
        assert gold_g["quantity"] > gold_oz["quantity"]
        # Silver in grams: purchase price per gram should be much less than gold per troy oz
        assert silver_g["purchase_price"] < gold_oz["purchase_price"]
