"""
Yearly performance attribution — computes per-position contribution to portfolio return
for a given calendar year.

Same unit-conversion logic as monthly_attribution.py and market_data_agent.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional


_TROY_OZ_TO_G = 31.1035


@dataclass
class AttributionYearRow:
    symbol: str
    investment_type: str
    unit: str
    start_price_eur: Optional[float]   # EUR per unit as stored in historical_prices
    end_price_eur: Optional[float]
    quantity: Optional[float]
    delta_pct: Optional[float]
    weight_pct: float
    contribution_eur: float
    contribution_pct: float
    dividend_contribution_eur: float = 0.0  # estimated: annual_dividend_eur (current rate, not actual payments)


def compute_yearly_attribution(
    valuations,
    market_repo,
    year: int,
) -> List[AttributionYearRow]:
    """
    For each portfolio position (not watchlist, not excluded) with a ticker:
    - Find first available closing price in historical_prices for Jan of the given year
    - Use current_value_eur (already unit-converted) as end value
    - Apply same unit conversion as market_data_agent for start value

    Purchase-date correction: if a position was bought after Jan 1, cost_basis_eur
    replaces the historical start price to avoid distorted returns.

    Positions without historical data are included with delta=None, contribution=0.
    """
    period_start = date(year, 1, 1)
    year_start = period_start.isoformat()
    year_end = f"{year:04d}-12-31"

    portfolio_vals = [
        v for v in valuations
        if v.in_portfolio and not getattr(v, "analysis_excluded", False)
        and v.current_value_eur is not None
        and v.current_value_eur > 0
    ]

    total_end_value = sum(v.current_value_eur for v in portfolio_vals if v.current_value_eur)
    if total_end_value == 0:
        return []

    total_start_value = 0.0
    for v in portfolio_vals:
        sv = _get_start_value_yearly(market_repo, v, year_start, year_end, period_start)
        if sv:
            total_start_value += sv

    rows: List[AttributionYearRow] = []
    for v in portfolio_vals:
        unit = getattr(v, "unit", None) or ""
        qty = v.quantity
        end_val = v.current_value_eur

        purchase_date = getattr(v, "purchase_date", None)
        bought_mid_period = purchase_date is not None and purchase_date > period_start

        if bought_mid_period and getattr(v, "cost_basis_eur", None):
            start_val = v.cost_basis_eur
            start_price = None
        else:
            start_price = _get_year_start_price(market_repo, v.symbol, year_start, year_end)
            start_val = _to_start_value(start_price, qty, unit)

        delta_pct: Optional[float] = None
        contribution_eur = 0.0
        if start_val and end_val and start_val > 0:
            contribution_eur = end_val - start_val
            delta_pct = contribution_eur / start_val * 100

        weight_pct = (v.current_value_eur / total_end_value * 100) if total_end_value > 0 else 0.0
        contribution_pct = (contribution_eur / total_start_value * 100) if total_start_value > 0 else 0.0

        annual_div = getattr(v, "annual_dividend_eur", None)
        dividend_contribution_eur = annual_div if annual_div is not None and annual_div > 0 else 0.0

        rows.append(AttributionYearRow(
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
            dividend_contribution_eur=dividend_contribution_eur,
        ))

    rows.sort(key=lambda r: r.contribution_eur, reverse=True)
    return rows


def _get_start_value_yearly(market_repo, v, year_start: str, year_end: str, period_start: date) -> Optional[float]:
    """Return start value for a valuation, using cost_basis_eur for mid-period purchases."""
    purchase_date = getattr(v, "purchase_date", None)
    if purchase_date is not None and purchase_date > period_start:
        return getattr(v, "cost_basis_eur", None)
    start_price = _get_year_start_price(market_repo, v.symbol, year_start, year_end)
    return _to_start_value(start_price, v.quantity, getattr(v, "unit", None))


def _to_start_value(
    price: Optional[float], qty: Optional[float], unit: Optional[str]
) -> Optional[float]:
    if not price or not qty:
        return None
    if unit == "g":
        return (price / _TROY_OZ_TO_G) * qty
    return price * qty


def _get_year_start_price(market_repo, symbol: str, year_start: str, year_end: str) -> Optional[float]:
    """Return the first closing price for symbol within the year range."""
    try:
        rows = market_repo._conn.execute(
            """
            SELECT close_eur FROM historical_prices
            WHERE symbol = ? AND date BETWEEN ? AND ?
            ORDER BY date ASC
            LIMIT 1
            """,
            (symbol.upper(), year_start, year_end),
        ).fetchall()
        if rows:
            return float(rows[0]["close_eur"])
    except Exception:
        pass
    return None
