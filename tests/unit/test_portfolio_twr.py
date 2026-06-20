"""Unit tests for core/portfolio_twr.py — pure, no DB/network."""

from types import SimpleNamespace

import pytest

from core.portfolio_twr import (
    portfolio_twr_series,
    benchmark_twr_series,
    drawdown_series,
    volatility_annualized,
)


def _snap(date_str, holdings=None):
    return SimpleNamespace(date=date_str, holdings=holdings)


def _h(ticker, qty, price, annual_div=None):
    return {"ticker": ticker, "quantity": qty, "price_eur": price, "annual_dividend_eur": annual_div}


class TestPortfolioTwrSeries:
    def test_empty_without_holdings(self):
        assert portfolio_twr_series([_snap("2026-06-01", holdings=None)]) == []
        assert portfolio_twr_series([]) == []

    def test_single_snapshot_anchors_at_zero(self):
        out = portfolio_twr_series([_snap("2026-06-17", [_h("A", 10, 100)])])
        assert out == [{"date": "2026-06-17", "twr_pct": 0.0}]

    def test_pure_price_move_no_dividend(self):
        # one title, +10% price move between two snapshots
        snaps = [
            _snap("2026-06-17", [_h("A", 10, 100.0)]),
            _snap("2026-06-18", [_h("A", 10, 110.0)]),
        ]
        out = portfolio_twr_series(snaps, include_dividends=False)
        assert out[0]["twr_pct"] == pytest.approx(0.0)
        assert out[1]["twr_pct"] == pytest.approx(10.0)

    def test_share_increase_is_not_a_return(self):
        # Reinvested dividend / fresh capital: qty goes 10 → 12 at flat price.
        # TWR must stay ~0 because the basket re-bases at the boundary; the share
        # increase is NOT a cashflow and contributes no return.
        snaps = [
            _snap("2026-06-17", [_h("A", 10, 100.0)]),
            _snap("2026-06-18", [_h("A", 12, 100.0)]),  # +2 shares, same price
        ]
        out = portfolio_twr_series(snaps, include_dividends=False)
        assert out[1]["twr_pct"] == pytest.approx(0.0)

    def test_chaining_compounds(self):
        # +10% then +10% → 1.1*1.1-1 = 21%
        snaps = [
            _snap("2026-06-17", [_h("A", 1, 100.0)]),
            _snap("2026-06-18", [_h("A", 1, 110.0)]),
            _snap("2026-06-19", [_h("A", 1, 121.0)]),
        ]
        out = portfolio_twr_series(snaps, include_dividends=False)
        assert out[-1]["twr_pct"] == pytest.approx(21.0)

    def test_two_titles_value_weighted(self):
        # A: 100→110 (+10%), B: 100→100 (flat), equal value → +5% blended
        snaps = [
            _snap("2026-06-17", [_h("A", 1, 100.0), _h("B", 1, 100.0)]),
            _snap("2026-06-18", [_h("A", 1, 110.0), _h("B", 1, 100.0)]),
        ]
        out = portfolio_twr_series(snaps, include_dividends=False)
        assert out[1]["twr_pct"] == pytest.approx(5.0)

    def test_dividend_adds_to_return(self):
        # Flat price, but a full year between snapshots with annual_dividend_eur=5 on a
        # 100-value holding → +5% from income.
        snaps = [
            _snap("2026-06-17", [_h("A", 1, 100.0, annual_div=5.0)]),
            _snap("2027-06-17", [_h("A", 1, 100.0, annual_div=5.0)]),
        ]
        out = portfolio_twr_series(snaps, include_dividends=True)
        assert out[1]["twr_pct"] == pytest.approx(5.0, abs=0.05)

    def test_sold_title_uses_price_at_fallback(self):
        # A held at prev, gone in cur. price_at supplies the current price.
        snaps = [
            _snap("2026-06-17", [_h("A", 1, 100.0)]),
            _snap("2026-06-18", [_h("B", 1, 50.0)]),  # A no longer present
        ]
        out = portfolio_twr_series(snaps, include_dividends=False, price_at=lambda tk, d: 120.0)
        assert out[1]["twr_pct"] == pytest.approx(20.0)

    def test_unsorted_input_is_ordered(self):
        snaps = [
            _snap("2026-06-18", [_h("A", 1, 110.0)]),
            _snap("2026-06-17", [_h("A", 1, 100.0)]),
        ]
        out = portfolio_twr_series(snaps, include_dividends=False)
        assert [p["date"] for p in out] == ["2026-06-17", "2026-06-18"]
        assert out[-1]["twr_pct"] == pytest.approx(10.0)


class TestBenchmarkTwrSeries:
    def test_aligned_cumulative(self):
        levels = {"2026-06-17": 100.0, "2026-06-18": 110.0, "2026-06-19": 121.0}
        out = benchmark_twr_series(list(levels), levels.get)
        assert out[0]["twr_pct"] == pytest.approx(0.0)
        assert out[1]["twr_pct"] == pytest.approx(10.0)
        assert out[2]["twr_pct"] == pytest.approx(21.0)

    def test_anchor_skips_leading_missing(self):
        levels = {"2026-06-17": None, "2026-06-18": 100.0, "2026-06-19": 105.0}
        out = benchmark_twr_series(list(levels), levels.get)
        assert out[0]["twr_pct"] is None
        assert out[1]["twr_pct"] == pytest.approx(0.0)
        assert out[2]["twr_pct"] == pytest.approx(5.0)


class TestDrawdownSeries:
    def test_drawdown_from_peak(self):
        twr = [
            {"date": "d1", "twr_pct": 0.0},
            {"date": "d2", "twr_pct": 20.0},  # peak
            {"date": "d3", "twr_pct": 8.0},   # 1.08/1.20 - 1 = -10%
        ]
        out, max_dd = drawdown_series(twr)
        assert out[-1]["drawdown_pct"] == pytest.approx(-10.0)
        assert max_dd == pytest.approx(-10.0)

    def test_no_drawdown_when_monotonic(self):
        twr = [{"date": "d1", "twr_pct": 0.0}, {"date": "d2", "twr_pct": 5.0}]
        out, max_dd = drawdown_series(twr)
        assert max_dd == pytest.approx(0.0)
        assert all(p["drawdown_pct"] <= 0 for p in out)


class TestVolatility:
    def test_none_below_min_points(self):
        twr = [{"date": f"d{i}", "twr_pct": float(i)} for i in range(5)]
        assert volatility_annualized(twr, min_points=20) is None

    def test_computes_when_enough_points(self):
        # alternating returns → non-zero vol
        twr = []
        level = 1.0
        for i in range(30):
            level *= 1.01 if i % 2 == 0 else 0.99
            twr.append({"date": f"d{i}", "twr_pct": (level - 1) * 100})
        vol = volatility_annualized(twr, min_points=20)
        assert vol is not None and vol > 0
