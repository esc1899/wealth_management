"""
Monthly performance attribution — computes per-position contribution to portfolio return
for a given calendar month.

Data source: historical_prices (start = last close of prev month, end = last close of
current month or live price if current month is still running).
No LLM required: pure local computation.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import List, Optional


# Same constant as market_data_agent — price from yfinance is EUR/troy_oz,
# positions with unit="g" need this conversion to get EUR value.
_TROY_OZ_TO_G = 31.1035


@dataclass
class AttributionMonthRow:
    symbol: str
    investment_type: str
    unit: str
    start_price_eur: Optional[float]   # EUR per unit as stored in historical_prices (e.g. EUR/troy_oz for gold)
    end_price_eur: Optional[float]     # same unit as start_price_eur
    quantity: Optional[float]
    delta_pct: Optional[float]         # % change of position value (= % change of price, unit-independent)
    weight_pct: float                  # position weight in portfolio at end of period
    contribution_eur: float            # absolute €-gain/loss (unit-converted)
    contribution_pct: float            # contribution_eur / total_portfolio_start_value * 100
    dividend_contribution_eur: float = 0.0  # estimated: annual_dividend_eur / 12


def compute_monthly_attribution(
    valuations,
    market_repo,
    year: int,
    month: int,
) -> List[AttributionMonthRow]:
    """
    For each portfolio position (not watchlist, not excluded) with a ticker:
    - Start price: last closing price of the PREVIOUS month (standard period-return convention)
    - End price: last closing price of the computed month, or current_price_eur if current month

    Unit handling mirrors market_data_agent.get_portfolio_valuation():
      unit="g"  → price is EUR/troy_oz, value = (price / 31.1035) * quantity_grams
      otherwise → value = price * quantity

    Purchase-date correction: if a position was bought after the month started,
    cost_basis_eur replaces the historical start price to avoid distorted returns.

    Positions without historical data are included with delta=None, contribution=0.
    """
    today = date.today()
    is_current_month = (year == today.year and month == today.month)

    period_start = date(year, month, 1)
    month_start = period_start.isoformat()
    month_end = date(year, month, calendar.monthrange(year, month)[1]).isoformat()

    # Previous month range — start price = last close of previous month
    if month == 1:
        prev_year, prev_month_num = year - 1, 12
    else:
        prev_year, prev_month_num = year, month - 1
    prev_month_start = date(prev_year, prev_month_num, 1).isoformat()
    prev_month_end = date(prev_year, prev_month_num, calendar.monthrange(prev_year, prev_month_num)[1]).isoformat()

    portfolio_vals = [
        v for v in valuations
        if v.in_portfolio and not getattr(v, "analysis_excluded", False)
        and v.current_value_eur is not None
        and v.current_value_eur > 0
    ]

    total_end_value = sum(v.current_value_eur for v in portfolio_vals if v.current_value_eur)
    if total_end_value == 0:
        return []

    # First pass: compute total start value for contribution_pct denominator
    total_start_value = 0.0
    for v in portfolio_vals:
        sv = _get_start_value_monthly(market_repo, v, prev_month_start, prev_month_end, period_start)
        if sv:
            total_start_value += sv

    # Second pass: build rows
    rows: List[AttributionMonthRow] = []
    for v in portfolio_vals:
        unit = getattr(v, "unit", None) or ""
        qty = v.quantity

        purchase_date = getattr(v, "purchase_date", None)
        bought_mid_period = purchase_date is not None and purchase_date > period_start

        if bought_mid_period and getattr(v, "cost_basis_eur", None):
            start_val = v.cost_basis_eur
            start_price = None
        else:
            start_price = _get_period_end_price(market_repo, v.symbol, prev_month_start, prev_month_end)
            start_val = _to_value(start_price, qty, unit)

        if is_current_month:
            end_price = v.current_price_eur
            end_val = v.current_value_eur
        else:
            end_price = _get_period_end_price(market_repo, v.symbol, month_start, month_end)
            end_val = _to_value(end_price, qty, unit)

        delta_pct: Optional[float] = None
        contribution_eur = 0.0
        if start_val and end_val and start_val > 0:
            contribution_eur = end_val - start_val
            delta_pct = contribution_eur / start_val * 100

        weight_pct = (v.current_value_eur / total_end_value * 100) if total_end_value > 0 else 0.0
        contribution_pct = (contribution_eur / total_start_value * 100) if total_start_value > 0 else 0.0

        annual_div = getattr(v, "annual_dividend_eur", None)
        dividend_contribution_eur = (annual_div / 12) if annual_div is not None and annual_div > 0 else 0.0

        rows.append(AttributionMonthRow(
            symbol=v.symbol,
            investment_type=v.investment_type,
            unit=unit,
            start_price_eur=start_price,
            end_price_eur=end_price,
            quantity=qty,
            delta_pct=delta_pct,
            weight_pct=weight_pct,
            contribution_eur=contribution_eur,
            contribution_pct=contribution_pct,
            dividend_contribution_eur=dividend_contribution_eur,
        ))

    rows.sort(key=lambda r: r.contribution_eur, reverse=True)
    return rows


def _get_start_value_monthly(market_repo, v, prev_month_start: str, prev_month_end: str, period_start: date) -> Optional[float]:
    """Return start value for a valuation, using cost_basis_eur for mid-period purchases."""
    purchase_date = getattr(v, "purchase_date", None)
    if purchase_date is not None and purchase_date > period_start:
        return getattr(v, "cost_basis_eur", None)
    start_price = _get_period_end_price(market_repo, v.symbol, prev_month_start, prev_month_end)
    return _to_value(start_price, v.quantity, getattr(v, "unit", None))


def _to_value(
    price: Optional[float], qty: Optional[float], unit: Optional[str]
) -> Optional[float]:
    """Convert price + quantity to EUR value, respecting unit conventions."""
    if not price or not qty:
        return None
    if unit == "g":
        return (price / _TROY_OZ_TO_G) * qty
    return price * qty


def _get_period_end_price(market_repo, symbol: str, range_start: str, range_end: str) -> Optional[float]:
    """Return the LAST closing price for symbol within the date range."""
    try:
        rows = market_repo._conn.execute(
            """
            SELECT close_eur FROM historical_prices
            WHERE symbol = ? AND date BETWEEN ? AND ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (symbol.upper(), range_start, range_end),
        ).fetchall()
        if rows:
            return float(rows[0]["close_eur"])
    except Exception:
        pass
    return None
