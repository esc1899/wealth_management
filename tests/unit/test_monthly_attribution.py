"""
Unit tests for core/monthly_attribution.py
"""

from __future__ import annotations

import sqlite3
from datetime import date
from unittest.mock import MagicMock

import pytest

from core.monthly_attribution import compute_monthly_attribution, AttributionMonthRow


def _make_valuation(symbol, investment_type="Wertpapiere", current_price=100.0, quantity=10.0, current_value=None, in_portfolio=True, unit="Stk"):
    v = MagicMock()
    v.symbol = symbol
    v.investment_type = investment_type
    v.current_price_eur = current_price
    v.quantity = quantity
    v.unit = unit
    v.current_value_eur = current_value if current_value is not None else (current_price * quantity if current_price and quantity else None)
    v.in_portfolio = in_portfolio
    v.analysis_excluded = False
    return v


def _make_market_repo(prices: dict[str, float]) -> MagicMock:
    """Mock repo with in-memory SQLite for historical_prices."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE historical_prices (
            id INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            close_eur REAL NOT NULL,
            volume INTEGER
        )
    """)
    for symbol, price in prices.items():
        conn.execute(
            "INSERT INTO historical_prices (symbol, date, close_eur) VALUES (?, ?, ?)",
            (symbol.upper(), "2026-05-02", price),
        )
    conn.commit()
    repo = MagicMock()
    repo._conn = conn
    return repo


class TestComputeMonthlyAttribution:
    def test_basic_gain(self):
        vals = [_make_valuation("AAPL", current_price=110.0, quantity=10.0)]
        market_repo = _make_market_repo({"AAPL": 100.0})
        rows = compute_monthly_attribution(vals, market_repo, 2026, 5)
        assert len(rows) == 1
        r = rows[0]
        assert r.symbol == "AAPL"
        assert r.delta_pct == pytest.approx(10.0)
        assert r.contribution_eur == pytest.approx(100.0)  # (110-100) * 10

    def test_loss(self):
        vals = [_make_valuation("TLT", current_price=90.0, quantity=5.0)]
        market_repo = _make_market_repo({"TLT": 100.0})
        rows = compute_monthly_attribution(vals, market_repo, 2026, 5)
        assert len(rows) == 1
        assert rows[0].contribution_eur == pytest.approx(-50.0)
        assert rows[0].delta_pct == pytest.approx(-10.0)

    def test_no_historical_data(self):
        vals = [_make_valuation("MSFT", current_price=400.0, quantity=2.0)]
        market_repo = _make_market_repo({})  # no data
        rows = compute_monthly_attribution(vals, market_repo, 2026, 5)
        assert len(rows) == 1
        assert rows[0].delta_pct is None
        assert rows[0].contribution_eur == 0.0

    def test_excludes_watchlist(self):
        vals = [
            _make_valuation("AAPL", in_portfolio=True, current_price=110.0, quantity=10.0),
            _make_valuation("GOOG", in_portfolio=False, current_price=200.0, quantity=5.0),
        ]
        market_repo = _make_market_repo({"AAPL": 100.0, "GOOG": 190.0})
        rows = compute_monthly_attribution(vals, market_repo, 2026, 5)
        symbols = [r.symbol for r in rows]
        assert "AAPL" in symbols
        assert "GOOG" not in symbols

    def test_sorted_by_contribution_descending(self):
        vals = [
            _make_valuation("LOSER", current_price=80.0, quantity=10.0),
            _make_valuation("WINNER", current_price=120.0, quantity=10.0),
        ]
        market_repo = _make_market_repo({"LOSER": 100.0, "WINNER": 100.0})
        rows = compute_monthly_attribution(vals, market_repo, 2026, 5)
        assert rows[0].symbol == "WINNER"
        assert rows[1].symbol == "LOSER"

    def test_empty_portfolio(self):
        rows = compute_monthly_attribution([], MagicMock(), 2026, 5)
        assert rows == []

    def test_gold_grams_unit_conversion(self):
        """Gold in grams: price is EUR/troy_oz, quantity is grams. Must apply /31.1035."""
        TROY_OZ_TO_G = 31.1035
        start_price_per_oz = 3000.0
        end_price_per_oz = 3100.0
        quantity_g = 31.1035  # exactly 1 troy oz worth of gold in grams

        # current_value_eur is already correctly computed by market_data_agent:
        # (end_price / TROY_OZ_TO_G) * quantity_g = (3100 / 31.1035) * 31.1035 = 3100
        correct_end_value = (end_price_per_oz / TROY_OZ_TO_G) * quantity_g  # = 3100

        vals = [_make_valuation(
            "XAUUSD",
            current_price=end_price_per_oz,
            quantity=quantity_g,
            current_value=correct_end_value,
            unit="g",
        )]
        market_repo = _make_market_repo({"XAUUSD": start_price_per_oz})
        rows = compute_monthly_attribution(vals, market_repo, 2026, 5)

        assert len(rows) == 1
        r = rows[0]
        # start_value = (3000 / 31.1035) * 31.1035 = 3000
        # end_value = 3100
        # contribution = 3100 - 3000 = 100 EUR (not 3100-3000)*31.1035 !)
        assert r.contribution_eur == pytest.approx(100.0, abs=0.01)
        assert r.delta_pct == pytest.approx(100.0 / 3000.0 * 100, abs=0.01)  # ~3.33%
