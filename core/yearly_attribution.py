"""
Yearly performance attribution — computes per-position contribution to portfolio return
for a given calendar year.

Same unit-conversion logic as monthly_attribution.py and market_data_agent.py.
"""

from __future__ import annotations

from dataclasses import dataclass
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

    Positions without historical data are included with delta=None, contribution=0.
    """
    year_start = f"{year:04d}-01-01"
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
        start_price = _get_year_start_price(market_repo, v.symbol, year_start, year_end)
        sv = _to_start_value(start_price, v.quantity, getattr(v, "unit", None))
        if sv:
            total_start_value += sv

    rows: List[AttributionYearRow] = []
    for v in portfolio_vals:
        start_price = _get_year_start_price(market_repo, v.symbol, year_start, year_end)
        unit = getattr(v, "unit", None) or ""
        qty = v.quantity
        end_val = v.current_value_eur

        start_val = _to_start_value(start_price, qty, unit)

        delta_pct: Optional[float] = None
        contribution_eur = 0.0
        if start_val and end_val and start_val > 0:
            contribution_eur = end_val - start_val
            delta_pct = contribution_eur / start_val * 100

        weight_pct = (v.current_value_eur / total_end_value * 100) if total_end_value > 0 else 0.0
        contribution_pct = (contribution_eur / total_start_value * 100) if total_start_value > 0 else 0.0

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
        ))

    rows.sort(key=lambda r: r.contribution_eur, reverse=True)
    return rows


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
