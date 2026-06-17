"""
Yearly performance attribution — computes per-position contribution to portfolio return
for a given calendar year.

Data source: historical_prices (start = last close of prev year Dec 31, end = last close
of current year Dec 31 or live price if current year is still running).
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
    wealth_repo=None,
) -> List[AttributionYearRow]:
    """
    For each portfolio position (not watchlist, not excluded) with a ticker:
    - Start price: last closing price of Dec 31 of the PREVIOUS year (period-return convention)
    - End price: last closing price of Dec 31 of the computed year, or current_price_eur if current year

    Quantity source: when ``wealth_repo`` is given, the quantity held at the start of the
    year is read from the nearest wealth snapshot's ``holdings`` (so a later quantity change
    no longer distorts a past year). Falls back to today's ``v.quantity`` when no snapshot
    carries composition near Jan 1.

    Purchase-date correction: if a position was bought after Jan 1, cost_basis_eur
    replaces the historical start price to avoid distorted returns.

    Positions without historical data are included with delta=None, contribution=0.
    """
    today = date.today()
    is_current_year = (year == today.year)

    period_start = date(year, 1, 1)
    year_start = period_start.isoformat()
    year_end = f"{year:04d}-12-31"

    # Previous year range — start price = last close of prev year
    prev_year_start = f"{year - 1:04d}-01-01"
    prev_year_end = f"{year - 1:04d}-12-31"

    # Quantity held at the start of the year (forward-only; None → today's qty)
    start_qty_map = wealth_repo.holdings_near_date(year_start) if wealth_repo is not None else None

    def _start_qty(v):
        if start_qty_map and start_qty_map.get(v.symbol) is not None:
            return start_qty_map[v.symbol]
        return v.quantity

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
        sv = _get_start_value_yearly(market_repo, v, prev_year_start, prev_year_end, period_start, _start_qty(v))
        if sv:
            total_start_value += sv

    rows: List[AttributionYearRow] = []
    for v in portfolio_vals:
        unit = getattr(v, "unit", None) or ""
        qty = _start_qty(v)

        purchase_date = getattr(v, "purchase_date", None)
        bought_mid_period = purchase_date is not None and purchase_date > period_start

        if bought_mid_period and getattr(v, "cost_basis_eur", None):
            start_val = v.cost_basis_eur
            start_price = None
        else:
            start_price = market_repo.get_last_price_in_range(v.symbol, prev_year_start, prev_year_end)
            start_val = _to_value(start_price, qty, unit)

        if is_current_year:
            end_price = v.current_price_eur
        else:
            end_price = market_repo.get_last_price_in_range(v.symbol, year_start, year_end)
        # Price-return on the quantity held entering the period (intra-period flows excluded)
        end_val = _to_value(end_price, qty, unit)

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


def _get_start_value_yearly(market_repo, v, prev_year_start: str, prev_year_end: str, period_start: date, start_qty=None) -> Optional[float]:
    """Return start value for a valuation, using cost_basis_eur for mid-period purchases."""
    purchase_date = getattr(v, "purchase_date", None)
    if purchase_date is not None and purchase_date > period_start:
        return getattr(v, "cost_basis_eur", None)
    qty = start_qty if start_qty is not None else v.quantity
    start_price = market_repo.get_last_price_in_range(v.symbol, prev_year_start, prev_year_end)
    return _to_value(start_price, qty, getattr(v, "unit", None))


def _to_value(
    price: Optional[float], qty: Optional[float], unit: Optional[str]
) -> Optional[float]:
    if not price or not qty:
        return None
    if unit == "g":
        return (price / _TROY_OZ_TO_G) * qty
    return price * qty


