"""
Integration tests for the demo database seeder.

- Runs the seeder against an in-memory SQLite DB (no file I/O).
- Mocks yfinance so no real network calls are made.
- Verifies all 20 positions are inserted with positive quantities and prices.
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
    "BTC-USD": 35000.0,
    "NVDA":    480.0,
    "LLY":     580.0,
    "BRK-B":   360.0,
    "ADBE":    560.0,
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
    def test_all_positions_inserted(self, mock_ticker_cls, mock_download, in_memory_conn):
        mock_ticker_cls.return_value.fast_info = _mock_fast_info("AAPL")

        # Patch fast_info per ticker
        def _ticker_factory(t):
            m = MagicMock()
            m.fast_info = _mock_fast_info(t)
            return m

        mock_ticker_cls.side_effect = _ticker_factory

        from scripts.seed_demo import seed
        inserted = seed(conn=in_memory_conn)

        # 20 portfolio + 4 watchlist-only positions
        assert len(inserted) == 24, f"Expected 24 positions, got {len(inserted)}"

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

        assert len(rows) == 20

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

        # Exclude manual positions (Festgeld, Immobilie) which have a fixed purchase value,
        # not the ~€10k target used for auto-fetch positions.
        _manual_names = {"Festgeld DKB 3J", "Eigentumswohnung München"}
        for pos in inserted:
            if pos["name"] in _manual_names:
                continue
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

    @patch("yfinance.download", side_effect=_mock_download)
    @patch("yfinance.Ticker")
    def test_watchlist_positions_seeded(self, mock_ticker_cls, mock_download, in_memory_conn):
        """4 watchlist-only positions (in_portfolio=0, in_watchlist=1) exist."""
        def _ticker_factory(t):
            m = MagicMock()
            m.fast_info = _mock_fast_info(t)
            return m

        mock_ticker_cls.side_effect = _ticker_factory

        from scripts.seed_demo import seed
        seed(conn=in_memory_conn)

        n_watchlist = in_memory_conn.execute(
            "SELECT COUNT(*) FROM positions WHERE in_watchlist = 1 AND in_portfolio = 0"
        ).fetchone()[0]
        assert n_watchlist == 4

    @patch("yfinance.download", side_effect=_mock_download)
    @patch("yfinance.Ticker")
    def test_extra_surfaces_seeded(self, mock_ticker_cls, mock_download, in_memory_conn):
        """Every demo surface beyond positions/prices/3-checks has rows."""
        def _ticker_factory(t):
            m = MagicMock()
            m.fast_info = _mock_fast_info(t)
            return m

        mock_ticker_cls.side_effect = _ticker_factory

        from scripts.seed_demo import seed
        seed(conn=in_memory_conn)

        def _count(sql: str) -> int:
            return in_memory_conn.execute(sql).fetchone()[0]

        # Watchlist-only agents
        assert _count("SELECT COUNT(*) FROM position_analyses WHERE agent = 'capital_allocator'") == 4
        assert _count("SELECT COUNT(*) FROM position_analyses WHERE agent = 'devils_advocate'") == 4
        # Time-series + analysis surfaces
        assert _count("SELECT COUNT(*) FROM wealth_snapshots") >= 12
        assert _count("SELECT COUNT(*) FROM dividend_data") == 9
        assert _count("SELECT COUNT(*) FROM portfolio_story_analyses") == 1
        assert _count("SELECT COUNT(*) FROM portfolio_story_position_fits") >= 1
        assert _count("SELECT COUNT(*) FROM portfolio_story") == 1
        assert _count("SELECT COUNT(*) FROM news_runs") == 2
        assert _count("SELECT COUNT(*) FROM sector_rotation_runs") == 1
        assert _count("SELECT COUNT(*) FROM sector_verdicts") == 4
        assert _count("SELECT COUNT(*) FROM structural_scan_runs") == 1
        # Cowork
        assert _count("SELECT COUNT(*) FROM research_requests") == 2
        assert _count("SELECT COUNT(*) FROM research_answers") == 1

    @patch("yfinance.download", side_effect=_mock_download)
    @patch("yfinance.Ticker")
    def test_wealth_snapshot_uptrend(self, mock_ticker_cls, mock_download, in_memory_conn):
        """Latest snapshot value should exceed the oldest (gentle uptrend)."""
        def _ticker_factory(t):
            m = MagicMock()
            m.fast_info = _mock_fast_info(t)
            return m

        mock_ticker_cls.side_effect = _ticker_factory

        from scripts.seed_demo import seed
        seed(conn=in_memory_conn)

        rows = in_memory_conn.execute(
            "SELECT total_eur FROM wealth_snapshots ORDER BY date ASC"
        ).fetchall()
        assert rows[-1]["total_eur"] > rows[0]["total_eur"]
