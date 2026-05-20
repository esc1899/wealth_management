"""
Dividend Calendar — deterministic 12-month cashflow forecast.

Distributes annual_dividend_eur equally across 12 months (annual / 12).
No DB persistence — computed on demand from live PortfolioValuation objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List


@dataclass
class DividendContribution:
    """Single position's monthly dividend contribution."""
    symbol: str
    name: str
    asset_class: str
    annual_dividend_eur: float
    monthly_eur: float  # = annual_dividend_eur / 12
    dividend_yield_pct: float | None = None
    dividend_source: str | None = None


@dataclass
class MonthlyForecast:
    """Aggregated dividend cashflow for one calendar month."""
    month: str  # "YYYY-MM"
    total_eur: float
    contributions: List[DividendContribution] = field(default_factory=list)


def compute_monthly_cashflow_forecast(
    valuations: list,  # list[PortfolioValuation] — avoid circular import
    months_ahead: int = 12,
) -> list[MonthlyForecast]:
    """Build a 12-month forward cashflow forecast from portfolio valuations.

    Filters to portfolio positions with dividend data.
    Distribution: equal monthly (annual_dividend_eur / 12 per position).
    Start month is the current calendar month.

    Args:
        valuations: PortfolioValuation list from MarketDataAgent
        months_ahead: number of months to forecast (default 12)

    Returns:
        List of MonthlyForecast sorted by month ascending
    """
    today = date.today()
    start_year = today.year
    start_month = today.month

    eligible = [
        v for v in valuations
        if v.in_portfolio
        and v.annual_dividend_eur
        and v.annual_dividend_eur > 0
    ]

    if not eligible:
        return []

    contributions = [
        DividendContribution(
            symbol=v.symbol,
            name=v.name,
            asset_class=v.asset_class,
            annual_dividend_eur=v.annual_dividend_eur,
            monthly_eur=v.annual_dividend_eur / 12,
            dividend_yield_pct=v.dividend_yield_pct,
            dividend_source=v.dividend_source,
        )
        for v in eligible
    ]

    total_monthly = sum(c.monthly_eur for c in contributions)

    forecasts: list[MonthlyForecast] = []
    for i in range(months_ahead):
        m = start_month + i
        y = start_year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        month_str = f"{y:04d}-{m:02d}"
        forecasts.append(
            MonthlyForecast(
                month=month_str,
                total_eur=round(total_monthly, 2),
                contributions=list(contributions),
            )
        )

    return forecasts


def get_top_contributors(
    forecasts: list[MonthlyForecast],
    top_n: int = 5,
) -> list[DividendContribution]:
    """Return top N contributors by annual dividend, descending."""
    if not forecasts:
        return []
    return sorted(
        forecasts[0].contributions,
        key=lambda c: c.annual_dividend_eur,
        reverse=True,
    )[:top_n]


def compute_coverage_pct(
    valuations: list,
    forecasts: list[MonthlyForecast],
) -> float:
    """Percentage of portfolio positions (by count) that have dividend data."""
    portfolio_positions = [v for v in valuations if v.in_portfolio]
    if not portfolio_positions:
        return 0.0
    if not forecasts:
        return 0.0
    paying = len(forecasts[0].contributions)
    return round(paying / len(portfolio_positions) * 100, 1)
