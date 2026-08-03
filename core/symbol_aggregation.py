"""Aggregate per-position valuations into one row per symbol.

The same ticker can be held in several depots — two ``positions`` rows share one
ticker. Charts keyed on the symbol stack those bars, but sorting happens on the
individual rows, so the merged bar is placed at the *first* position's value and
the second one is added on top afterwards. Aggregating before sorting/plotting
keeps the x-order consistent with the bar heights.

Percentages are re-derived from the summed bases (not averaged), so a symbol held
twice reports the same figure as if it were a single position.
"""

from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass
class SymbolDayPnL:
    symbol: str
    day_pnl_eur: float
    day_pnl_pct: Optional[float]


@dataclass
class SymbolPnL:
    symbol: str
    pnl_eur: float
    pnl_pct: Optional[float]
    value_eur: Optional[float]


def aggregate_day_pnl(valuations: Iterable) -> List[SymbolDayPnL]:
    """Sum today's P&L per symbol. Percentage = summed P&L / summed previous close value."""
    acc: dict[str, list[float]] = {}  # symbol -> [pnl_eur, prev_value_eur]
    for v in valuations:
        if v.day_pnl_eur is None:
            continue
        entry = acc.setdefault(v.symbol, [0.0, 0.0])
        entry[0] += v.day_pnl_eur
        if v.current_value_eur is not None:
            entry[1] += v.current_value_eur - v.day_pnl_eur
    return [
        SymbolDayPnL(
            symbol=symbol,
            day_pnl_eur=pnl,
            day_pnl_pct=(pnl / prev * 100) if prev > 0 else None,
        )
        for symbol, (pnl, prev) in acc.items()
    ]


def aggregate_pnl(valuations: Iterable) -> List[SymbolPnL]:
    """Sum total P&L per symbol. Percentage = summed P&L / summed cost basis."""
    acc: dict[str, list[float]] = {}  # symbol -> [pnl_eur, cost_basis_eur, value_eur]
    for v in valuations:
        if v.pnl_eur is None:
            continue
        entry = acc.setdefault(v.symbol, [0.0, 0.0, 0.0])
        entry[0] += v.pnl_eur
        if v.cost_basis_eur is not None:
            entry[1] += v.cost_basis_eur
        if v.current_value_eur is not None:
            entry[2] += v.current_value_eur
    return [
        SymbolPnL(
            symbol=symbol,
            pnl_eur=pnl,
            pnl_pct=(pnl / cost * 100) if cost > 0 else None,
            value_eur=value,
        )
        for symbol, (pnl, cost, value) in acc.items()
    ]


def make_start_qty_resolver(valuations: Iterable, start_qty_map: Optional[dict]):
    """Build ``resolve(valuation) -> quantity held at period start``.

    Snapshot holdings are keyed by ticker, so a ticker held in two depots yields one
    combined quantity. Attribution iterates per position, so the combined figure is
    split across those positions in proportion to today's quantities — the per-symbol
    total (the only figure the attribution math depends on) stays exact, and a position
    excluded from the analysis drops its share instead of pulling the whole ticker.

    Falls back to today's quantity when the snapshot has no entry for the symbol.
    Build the resolver from *all* valuations, not the filtered subset, so the split
    ratios cover every depot holding the ticker.
    """
    today_qty: dict[str, float] = {}
    for v in valuations:
        if v.quantity:
            today_qty[v.symbol] = today_qty.get(v.symbol, 0.0) + v.quantity

    def resolve(v):
        snapshot_qty = start_qty_map.get(v.symbol) if start_qty_map else None
        if snapshot_qty is None:
            return v.quantity
        total_today = today_qty.get(v.symbol, 0.0)
        if not total_today or not v.quantity:
            return snapshot_qty
        return snapshot_qty * (v.quantity / total_today)

    return resolve


def sum_contributions_by_symbol(rows: Iterable) -> List[tuple[str, float]]:
    """Sum ``contribution_eur`` of attribution rows per symbol, insertion-ordered."""
    acc: dict[str, float] = {}
    for r in rows:
        acc[r.symbol] = acc.get(r.symbol, 0.0) + r.contribution_eur
    return list(acc.items())
