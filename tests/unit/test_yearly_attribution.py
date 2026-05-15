"""
Unit tests for core/yearly_attribution.py
"""

from __future__ import annotations

import sqlite3
from datetime import date
from unittest.mock import MagicMock

import pytest

from core.yearly_attribution import compute_yearly_attribution, AttributionYearRow


def _make_valuation(symbol, investment_type="Wertpapiere", current_price=100.0, quantity=10.0, current_value=None, in_portfolio=True, unit="Stk", purchase_date=None, cost_basis_eur=None, annual_dividend_eur=None):
    v = MagicMock()
    v.symbol = symbol
    v.investment_type = investment_type
    v.current_price_eur = current_price
    v.quantity = quantity
    v.unit = unit
    v.current_value_eur = current_value if current_value is not None else (current_price * quantity if current_price and quantity else None)
    v.in_portfolio = in_portfolio
    v.analysis_excluded = False
    v.purchase_date = purchase_date
    v.cost_basis_eur = cost_basis_eur if cost_basis_eur is not None else (current_price * quantity if current_price and quantity else None)
    v.annual_dividend_eur = annual_dividend_eur
    return v


def _make_market_repo(rows: list[tuple[str, str, float]]) -> MagicMock:
    """
    Mock repo with in-memory SQLite for historical_prices.
    rows: list of (symbol, date_str, close_eur)
    """
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
    for symbol, date_str, price in rows:
        conn.execute(
            "INSERT INTO historical_prices (symbol, date, close_eur) VALUES (?, ?, ?)",
            (symbol.upper(), date_str, price),
        )
    conn.commit()
    repo = MagicMock()
    repo._conn = conn
    return repo


class TestComputeYearlyAttribution:
    # today = 2026-05-15 (per system date in tests)
    # current year = 2026 → start price from Dec 2025, end price = current_price_eur
    # past year = 2025 → start price from Dec 2024, end price from Dec 2025 historical

    def test_basic_gain_current_year(self):
        """Current year: start = last Dec 2025 close, end = current_price_eur."""
        vals = [_make_valuation("AAPL", current_price=110.0, quantity=10.0)]
        # Dec 2025 close = 100.0 (start price for 2026)
        market_repo = _make_market_repo([("AAPL", "2025-12-31", 100.0)])
        rows = compute_yearly_attribution(vals, market_repo, 2026)
        assert len(rows) == 1
        r = rows[0]
        assert r.symbol == "AAPL"
        assert r.delta_pct == pytest.approx(10.0)
        assert r.contribution_eur == pytest.approx(100.0)  # (110-100)*10

    def test_basic_loss_current_year(self):
        vals = [_make_valuation("TLT", current_price=90.0, quantity=5.0)]
        market_repo = _make_market_repo([("TLT", "2025-12-31", 100.0)])
        rows = compute_yearly_attribution(vals, market_repo, 2026)
        assert len(rows) == 1
        assert rows[0].contribution_eur == pytest.approx(-50.0)
        assert rows[0].delta_pct == pytest.approx(-10.0)

    def test_past_year_uses_historical_end(self):
        """Past year (2025): start = last Dec 2024 close, end = last Dec 2025 close."""
        vals = [_make_valuation("MSFT", current_price=999.0, quantity=10.0)]
        market_repo = _make_market_repo([
            ("MSFT", "2024-12-31", 100.0),
            ("MSFT", "2025-12-31", 110.0),
        ])
        rows = compute_yearly_attribution(vals, market_repo, 2025)
        assert len(rows) == 1
        r = rows[0]
        # start = 100*10=1000, end = 110*10=1100, contribution = 100
        assert r.contribution_eur == pytest.approx(100.0)
        assert r.delta_pct == pytest.approx(10.0)
        # end_price must be historical, NOT the live 999.0
        assert r.end_price_eur == pytest.approx(110.0)

    def test_current_year_uses_live_end(self):
        """Current year end price is current_price_eur, not historical."""
        vals = [_make_valuation("GOOG", current_price=200.0, quantity=5.0)]
        market_repo = _make_market_repo([("GOOG", "2025-12-30", 190.0)])
        rows = compute_yearly_attribution(vals, market_repo, 2026)
        assert len(rows) == 1
        r = rows[0]
        assert r.end_price_eur == pytest.approx(200.0)  # live price
        assert r.contribution_eur == pytest.approx(50.0)  # (200-190)*5

    def test_no_historical_data(self):
        """No prev-year data → delta=None, contribution=0."""
        vals = [_make_valuation("MSFT", current_price=400.0, quantity=2.0)]
        market_repo = _make_market_repo([])
        rows = compute_yearly_attribution(vals, market_repo, 2026)
        assert len(rows) == 1
        assert rows[0].delta_pct is None
        assert rows[0].contribution_eur == 0.0

    def test_excludes_watchlist(self):
        vals = [
            _make_valuation("AAPL", in_portfolio=True, current_price=110.0, quantity=10.0),
            _make_valuation("GOOG", in_portfolio=False, current_price=200.0, quantity=5.0),
        ]
        market_repo = _make_market_repo([
            ("AAPL", "2025-12-31", 100.0),
            ("GOOG", "2025-12-31", 190.0),
        ])
        rows = compute_yearly_attribution(vals, market_repo, 2026)
        symbols = [r.symbol for r in rows]
        assert "AAPL" in symbols
        assert "GOOG" not in symbols

    def test_sorted_by_contribution_descending(self):
        vals = [
            _make_valuation("LOSER", current_price=80.0, quantity=10.0),
            _make_valuation("WINNER", current_price=120.0, quantity=10.0),
        ]
        market_repo = _make_market_repo([
            ("LOSER", "2025-12-31", 100.0),
            ("WINNER", "2025-12-31", 100.0),
        ])
        rows = compute_yearly_attribution(vals, market_repo, 2026)
        assert rows[0].symbol == "WINNER"
        assert rows[1].symbol == "LOSER"

    def test_empty_portfolio(self):
        rows = compute_yearly_attribution([], MagicMock(), 2026)
        assert rows == []

    def test_gold_grams_unit_conversion(self):
        """Gold in grams: price is EUR/troy_oz, quantity is grams."""
        TROY_OZ_TO_G = 31.1035
        start_price_per_oz = 3000.0
        end_price_per_oz = 3100.0
        quantity_g = 31.1035

        correct_end_value = (end_price_per_oz / TROY_OZ_TO_G) * quantity_g  # = 3100

        vals = [_make_valuation(
            "XAUUSD",
            current_price=end_price_per_oz,
            quantity=quantity_g,
            current_value=correct_end_value,
            unit="g",
        )]
        # Dec 2025 close = start price for 2026
        market_repo = _make_market_repo([("XAUUSD", "2025-12-31", start_price_per_oz)])
        rows = compute_yearly_attribution(vals, market_repo, 2026)

        assert len(rows) == 1
        r = rows[0]
        # start_value = (3000 / 31.1035) * 31.1035 = 3000
        # end_value = 3100 (current_value_eur for current year)
        assert r.contribution_eur == pytest.approx(100.0, abs=0.01)
        assert r.delta_pct == pytest.approx(100.0 / 3000.0 * 100, abs=0.01)

    def test_purchase_mid_year_uses_cost_basis(self):
        """Position bought in March → cost_basis replaces start price."""
        vals = [_make_valuation(
            "NEW",
            current_price=120.0,
            quantity=10.0,
            current_value=1200.0,
            purchase_date=date(2026, 3, 15),
            cost_basis_eur=1000.0,
        )]
        # Dec 2025 data should be ignored for mid-period buys
        market_repo = _make_market_repo([("NEW", "2025-12-31", 50.0)])
        rows = compute_yearly_attribution(vals, market_repo, 2026)
        assert len(rows) == 1
        r = rows[0]
        assert r.contribution_eur == pytest.approx(200.0)   # 1200 - 1000
        assert r.delta_pct == pytest.approx(20.0)            # 200/1000 * 100
        assert r.start_price_eur is None                     # no historical price used

    def test_purchase_before_year_uses_historical(self):
        """Position bought before Jan 1 → normal prev-year close lookup."""
        vals = [_make_valuation(
            "OLD",
            current_price=110.0,
            quantity=10.0,
            current_value=1100.0,
            purchase_date=date(2025, 6, 1),
            cost_basis_eur=800.0,
        )]
        market_repo = _make_market_repo([("OLD", "2025-12-31", 100.0)])
        rows = compute_yearly_attribution(vals, market_repo, 2026)
        assert len(rows) == 1
        r = rows[0]
        assert r.contribution_eur == pytest.approx(100.0)   # 1100 - 1000 (historical)
        assert r.start_price_eur == pytest.approx(100.0)

    def test_dividend_contribution_yearly(self):
        """annual_dividend_eur is stored directly in dividend_contribution_eur."""
        vals = [_make_valuation("DIV", current_price=110.0, quantity=10.0, annual_dividend_eur=240.0)]
        market_repo = _make_market_repo([("DIV", "2025-12-31", 100.0)])
        rows = compute_yearly_attribution(vals, market_repo, 2026)
        assert len(rows) == 1
        assert rows[0].dividend_contribution_eur == pytest.approx(240.0)

    def test_no_dividend_gives_zero_yearly(self):
        """Positions without dividend data get dividend_contribution_eur = 0."""
        vals = [_make_valuation("NODIV", current_price=110.0, quantity=10.0, annual_dividend_eur=None)]
        market_repo = _make_market_repo([("NODIV", "2025-12-31", 100.0)])
        rows = compute_yearly_attribution(vals, market_repo, 2026)
        assert rows[0].dividend_contribution_eur == 0.0

    def test_past_year_no_end_data_gives_zero(self):
        """Past year with no historical Dec end data → contribution=0, delta=None."""
        vals = [_make_valuation("XYZ", current_price=999.0, quantity=10.0)]
        # Only start data (Dec 2024), no Dec 2025 historical data
        market_repo = _make_market_repo([("XYZ", "2024-12-31", 100.0)])
        rows = compute_yearly_attribution(vals, market_repo, 2025)
        assert len(rows) == 1
        assert rows[0].delta_pct is None
        assert rows[0].contribution_eur == 0.0
