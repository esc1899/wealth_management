"""
Monthly performance attribution — computes per-position contribution to portfolio return
for a given calendar month.

Data source: historical_prices (start of month) + current_prices (end/current).
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


def compute_monthly_attribution(
    valuations,
    market_repo,
    year: int,
    month: int,
) -> List[AttributionMonthRow]:
    """
    For each portfolio position (not watchlist, not excluded) with a ticker:
    - Find first available closing price in historical_prices for the given month
    - Use current_value_eur (already unit-converted) as end value
    - Apply same unit conversion as market_data_agent for start value

    Unit handling mirrors market_data_agent.get_portfolio_valuation():
      unit="g"  → price is EUR/troy_oz, value = (price / 31.1035) * quantity_grams
      otherwise → value = price * quantity

    Positions without historical data are included with delta=None, contribution=0.
    """
    month_start = date(year, month, 1).isoformat()
    month_end = date(year, month, calendar.monthrange(year, month)[1]).isoformat()

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
        start_price = _get_month_start_price(market_repo, v.symbol, month_start, month_end)
        sv = _to_start_value(start_price, v.quantity, getattr(v, "unit", None))
        if sv:
            total_start_value += sv

    # Second pass: build rows
    rows: List[AttributionMonthRow] = []
    for v in portfolio_vals:
        start_price = _get_month_start_price(market_repo, v.symbol, month_start, month_end)
        unit = getattr(v, "unit", None) or ""
        qty = v.quantity
        end_val = v.current_value_eur   # already correctly unit-converted by market_data_agent

        start_val = _to_start_value(start_price, qty, unit)

        delta_pct: Optional[float] = None
        contribution_eur = 0.0
        if start_val and end_val and start_val > 0:
            contribution_eur = end_val - start_val
            delta_pct = contribution_eur / start_val * 100

        weight_pct = (v.current_value_eur / total_end_value * 100) if total_end_value > 0 else 0.0
        contribution_pct = (contribution_eur / total_start_value * 100) if total_start_value > 0 else 0.0

        rows.append(AttributionMonthRow(
            symbol=v.symbol,
            investment_type=v.investment_type,
            unit=unit,
            start_price_eur=start_price,
            end_price_eur=v.current_price_eur,
            quantity=qty,
            delta_pct=delta_pct,
            weight_pct=weight_pct,
            contribution_eur=contribution_eur,
            contribution_pct=contribution_pct,
        ))

    rows.sort(key=lambda r: r.contribution_eur, reverse=True)
    return rows


def _to_start_value(
    price: Optional[float], qty: Optional[float], unit: Optional[str]
) -> Optional[float]:
    """Convert start price + quantity to EUR value, respecting unit conventions."""
    if not price or not qty:
        return None
    if unit == "g":
        return (price / _TROY_OZ_TO_G) * qty
    return price * qty


def _get_month_start_price(market_repo, symbol: str, month_start: str, month_end: str) -> Optional[float]:
    """Return the first closing price for symbol within the month range."""
    try:
        rows = market_repo._conn.execute(
            """
            SELECT close_eur FROM historical_prices
            WHERE symbol = ? AND date BETWEEN ? AND ?
            ORDER BY date ASC
            LIMIT 1
            """,
            (symbol.upper(), month_start, month_end),
        ).fetchall()
        if rows:
            return float(rows[0]["close_eur"])
    except Exception:
        pass
    return None
