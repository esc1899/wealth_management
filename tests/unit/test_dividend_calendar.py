"""
Unit tests for core/dividend_calendar.py — deterministic cashflow forecast.
"""

from __future__ import annotations

from datetime import date
from typing import Optional
from unittest.mock import patch

import pytest

from agents.market_data_agent import PortfolioValuation
from core.dividend_calendar import (
    DividendContribution,
    MonthlyForecast,
    compute_coverage_pct,
    compute_monthly_cashflow_forecast,
    get_top_contributors,
)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_valuation(
    symbol: str,
    annual_dividend_eur: Optional[float],
    in_portfolio: bool = True,
    analysis_excluded: bool = False,
    name: Optional[str] = None,
    asset_class: str = "Aktie",
) -> PortfolioValuation:
    return PortfolioValuation(
        symbol=symbol,
        name=name or symbol,
        asset_class=asset_class,
        investment_type="Aktie",
        quantity=10.0,
        unit="Stück",
        purchase_price_eur=100.0,
        current_price_eur=110.0,
        current_value_eur=1100.0,
        cost_basis_eur=1000.0,
        pnl_eur=100.0,
        pnl_pct=10.0,
        fetched_at=None,
        in_portfolio=in_portfolio,
        in_watchlist=not in_portfolio,
        annual_dividend_eur=annual_dividend_eur,
        dividend_yield_pct=0.02 if annual_dividend_eur else None,
        dividend_source="yfinance" if annual_dividend_eur else None,
        analysis_excluded=analysis_excluded,
    )


_FIXED_TODAY = date(2026, 5, 20)


class TestComputeMonthlyForecast:
    """Tests for compute_monthly_cashflow_forecast."""

    def test_empty_valuations_returns_empty(self):
        result = compute_monthly_cashflow_forecast([])
        assert result == []

    def test_no_dividend_positions_returns_empty(self):
        v = _make_valuation("NODIV", None)
        result = compute_monthly_cashflow_forecast([v])
        assert result == []

    def test_zero_dividend_excluded(self):
        v = _make_valuation("ZERO", 0.0)
        result = compute_monthly_cashflow_forecast([v])
        assert result == []

    def test_single_position_12_months(self):
        v = _make_valuation("AAPL", 120.0)
        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            result = compute_monthly_cashflow_forecast([v])

        assert len(result) == 12
        assert result[0].month == "2026-05"
        assert result[-1].month == "2027-04"

    def test_monthly_amount_equals_annual_divided_by_12(self):
        annual = 240.0
        v = _make_valuation("TEST", annual)
        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            result = compute_monthly_cashflow_forecast([v])

        for forecast in result:
            assert abs(forecast.total_eur - annual / 12) < 0.01

    def test_multiple_positions_sums_correctly(self):
        v1 = _make_valuation("A", 120.0)
        v2 = _make_valuation("B", 60.0)
        expected_monthly = (120.0 + 60.0) / 12

        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            result = compute_monthly_cashflow_forecast([v1, v2])

        assert len(result) == 12
        for forecast in result:
            assert abs(forecast.total_eur - expected_monthly) < 0.01

    def test_filters_out_non_portfolio(self):
        portfolio = _make_valuation("PORT", 120.0, in_portfolio=True)
        watchlist = _make_valuation("WATCH", 120.0, in_portfolio=False)

        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            result = compute_monthly_cashflow_forecast([portfolio, watchlist])

        assert len(result) == 12
        assert len(result[0].contributions) == 1
        assert result[0].contributions[0].symbol == "PORT"

    def test_includes_analysis_excluded(self):
        # Dividend calendar shows ALL paying portfolio positions, incl. analysis_excluded
        included = _make_valuation("INC", 120.0, analysis_excluded=False)
        also_included = _make_valuation("EXC", 120.0, analysis_excluded=True)

        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            result = compute_monthly_cashflow_forecast([included, also_included])

        assert len(result[0].contributions) == 2

    def test_months_ahead_parameter(self):
        v = _make_valuation("X", 100.0)
        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            result = compute_monthly_cashflow_forecast([v], months_ahead=6)

        assert len(result) == 6

    def test_year_boundary_wraps_correctly(self):
        v = _make_valuation("X", 100.0)
        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = date(2026, 11, 1)
            result = compute_monthly_cashflow_forecast([v], months_ahead=4)

        assert result[0].month == "2026-11"
        assert result[1].month == "2026-12"
        assert result[2].month == "2027-01"
        assert result[3].month == "2027-02"

    def test_contributions_carry_correct_fields(self):
        v = _make_valuation("AAPL", 120.0, name="Apple Inc.", asset_class="Aktie")
        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            result = compute_monthly_cashflow_forecast([v])

        c = result[0].contributions[0]
        assert c.symbol == "AAPL"
        assert c.name == "Apple Inc."
        assert c.asset_class == "Aktie"
        assert abs(c.monthly_eur - 10.0) < 0.01
        assert c.annual_dividend_eur == 120.0


class TestGetTopContributors:
    """Tests for get_top_contributors."""

    def test_empty_forecasts_returns_empty(self):
        assert get_top_contributors([]) == []

    def test_returns_sorted_by_annual_desc(self):
        v_small = _make_valuation("S", 60.0)
        v_large = _make_valuation("L", 240.0)
        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            forecasts = compute_monthly_cashflow_forecast([v_small, v_large])

        top = get_top_contributors(forecasts, top_n=2)
        assert top[0].symbol == "L"
        assert top[1].symbol == "S"

    def test_top_n_limits_result(self):
        vals = [_make_valuation(str(i), float(i * 10 + 10)) for i in range(15)]
        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            forecasts = compute_monthly_cashflow_forecast(vals)

        top = get_top_contributors(forecasts, top_n=10)
        assert len(top) == 10

    def test_top_n_larger_than_count_returns_all(self):
        vals = [_make_valuation("A", 100.0), _make_valuation("B", 200.0)]
        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            forecasts = compute_monthly_cashflow_forecast(vals)

        top = get_top_contributors(forecasts, top_n=10)
        assert len(top) == 2


class TestComputeCoveragePct:
    """Tests for compute_coverage_pct."""

    def test_no_positions_returns_zero(self):
        assert compute_coverage_pct([], []) == 0.0

    def test_no_forecasts_returns_zero(self):
        v = _make_valuation("A", None)
        assert compute_coverage_pct([v], []) == 0.0

    def test_all_paying_returns_100(self):
        v1 = _make_valuation("A", 100.0)
        v2 = _make_valuation("B", 200.0)
        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            forecasts = compute_monthly_cashflow_forecast([v1, v2])

        assert compute_coverage_pct([v1, v2], forecasts) == 100.0

    def test_half_paying_returns_50(self):
        paying = _make_valuation("PAY", 100.0)
        nopay = _make_valuation("NOPAY", None)
        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            forecasts = compute_monthly_cashflow_forecast([paying, nopay])

        cov = compute_coverage_pct([paying, nopay], forecasts)
        assert cov == 50.0

    def test_analysis_excluded_counts_in_denominator(self):
        # analysis_excluded positions count toward total portfolio (denominator)
        paying = _make_valuation("PAY", 100.0)
        nopay_excluded = _make_valuation("EXC", None, analysis_excluded=True)
        with patch("core.dividend_calendar.date") as mock_date:
            mock_date.today.return_value = _FIXED_TODAY
            forecasts = compute_monthly_cashflow_forecast([paying, nopay_excluded])

        # denominator = 2 positions, numerator = 1 paying → 50%
        cov = compute_coverage_pct([paying, nopay_excluded], forecasts)
        assert cov == 50.0
