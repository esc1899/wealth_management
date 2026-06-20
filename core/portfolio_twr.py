"""
Portfolio time-weighted return (TWR) vs. a benchmark — derived from the
wealth-snapshot time series. Pure, deterministic computations (no LLM, no network).

Why TWR on a holdings basis (FEAT-73):
The raw ``total_eur`` series is contaminated by deposits/withdrawals — fresh capital
inflates the value independently of performance, so comparing it to an index is
meaningless. A *chained* TWR sidesteps this without needing any cashflow ledger:

    Within a sub-period (snapshot prev → cur) the share counts are held FIXED, so the
    period return is pure price movement (+ dividends received in the window):

        base = Σ qty_prev[t] · price_prev[t]                 (prev basket at prev prices)
        end  = Σ qty_prev[t] · price_cur[t]  + dividends      (same basket, repriced)
        r    = (end) / base − 1
        TWR  = Π (1 + r) − 1

    Share-count changes — whether fresh capital OR a reinvested dividend — happen only
    at the period boundary and appear in NO return term; they merely re-base the basket
    for the next sub-period. So the cashflow problem is structurally absent, and a
    reinvested dividend cannot be double-counted (the reinvest buy is never a cashflow).

The per-title prices live in the snapshot ``holdings`` themselves (``price_eur``), so
the portfolio TWR is self-consistent and needs no external price lookup — except for a
title fully sold between two snapshots (then ``price_at`` is consulted, else the prev
price is carried, contributing 0 to that sub-period).

Dividends are estimated by prorating each holding's forward ``annual_dividend_eur`` over
the window (days/365). This is the honest smooth estimate (snapshot ``price_eur`` already
reflects ex-div drops); it sums to ~the annual figure as the series matures.

Forward-only: only snapshots that stored ``holdings`` contribute (since 2026-06-17).
With too few sub-periods the series is short and volatility returns None ("baut sich auf").
The benchmark (e.g. EUNL.DE, an accumulating MSCI World ETF) carries reinvested
dividends in its price already, so its price return == total return — no adjustment.
"""

from __future__ import annotations

import statistics
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

# date (str) → price/level, or None if unavailable.
LevelFn = Callable[[str], Optional[float]]
# (ticker, date_str) → price, or None. Used only for titles missing from a later snapshot.
PriceAtFn = Callable[[str, str], Optional[float]]


def _parse(value) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _days_between(a: str, b: str) -> float:
    da, db = _parse(a), _parse(b)
    if da is None or db is None:
        return 0.0
    return max(0.0, (db - da).days)


def _holdings_map(snap) -> Dict[str, Tuple[float, float, Optional[float]]]:
    """{ticker: (quantity, price_eur, annual_dividend_eur)} for usable holdings."""
    out: Dict[str, Tuple[float, float, Optional[float]]] = {}
    for h in (getattr(snap, "holdings", None) or []):
        ticker = h.get("ticker")
        qty = h.get("quantity")
        price = h.get("price_eur")
        if not ticker or qty is None or price is None:
            continue
        out[ticker] = (float(qty), float(price), h.get("annual_dividend_eur"))
    return out


def portfolio_twr_series(
    snapshots,
    price_at: Optional[PriceAtFn] = None,
    include_dividends: bool = True,
) -> List[dict]:
    """Chained time-weighted return from holdings-bearing snapshots.

    Returns ``[{date, twr_pct}, ...]`` in ascending date order, cumulative since the
    first holdings-bearing snapshot (first point is always 0.0). Empty if no snapshot
    carries holdings. ``twr_pct`` is the cumulative total return in percent.
    """
    snaps = [s for s in snapshots if getattr(s, "holdings", None)]
    snaps.sort(key=lambda s: str(s.date))
    if not snaps:
        return []

    series: List[dict] = [{"date": snaps[0].date, "twr_pct": 0.0}]
    cum = 1.0
    for prev, cur in zip(snaps, snaps[1:]):
        pmap = _holdings_map(prev)
        cmap = _holdings_map(cur)
        days = _days_between(prev.date, cur.date)
        base = 0.0
        end = 0.0
        div = 0.0
        for ticker, (qty, pprice, pdiv) in pmap.items():
            base += qty * pprice
            if ticker in cmap:
                cprice = cmap[ticker][1]
            elif price_at is not None:
                cprice = price_at(ticker, cur.date) or pprice
            else:
                cprice = pprice  # title gone, no current price → 0 contribution
            end += qty * cprice
            if include_dividends and pdiv:
                div += float(pdiv) * days / 365.0
        if base > 0:
            cum *= 1 + (end + div) / base - 1
        series.append({"date": cur.date, "twr_pct": (cum - 1) * 100})
    return series


def benchmark_twr_series(dates: List[str], level_fn: LevelFn) -> List[dict]:
    """Cumulative benchmark return aligned to the given snapshot ``dates``.

    Returns ``[{date, twr_pct}, ...]`` anchored (0.0) at the first date with a level.
    Dates before the anchor, or with no level, carry ``twr_pct=None``.
    """
    series: List[dict] = []
    cum = 1.0
    prev_level: Optional[float] = None
    for d in dates:
        lvl = level_fn(d)
        if lvl is None or lvl <= 0:
            series.append({"date": d, "twr_pct": None if prev_level is None else (cum - 1) * 100})
            continue
        if prev_level is None:
            series.append({"date": d, "twr_pct": 0.0})
        else:
            cum *= lvl / prev_level
            series.append({"date": d, "twr_pct": (cum - 1) * 100})
        prev_level = lvl
    return series


def drawdown_series(twr_points: List[dict]) -> Tuple[List[dict], float]:
    """From a cumulative TWR series, return (per-date drawdown %, max drawdown %).

    Drawdown is measured against the running peak of the TWR index (cashflow-immune,
    unlike a drawdown computed from ``total_eur``). ``max_drawdown`` is <= 0.
    """
    out: List[dict] = []
    peak: Optional[float] = None
    max_dd = 0.0
    for p in twr_points:
        pct = p.get("twr_pct")
        if pct is None:
            continue
        level = 1 + pct / 100
        peak = level if peak is None else max(peak, level)
        dd = (level / peak - 1) * 100 if peak > 0 else 0.0
        max_dd = min(max_dd, dd)
        out.append({"date": p["date"], "drawdown_pct": dd})
    return out, max_dd


def volatility_annualized(
    twr_points: List[dict], min_points: int = 20, trading_days: int = 252
) -> Optional[float]:
    """Annualised volatility (%) from the TWR index period returns.

    Returns None until at least ``min_points`` TWR points exist ("baut sich auf").
    Assumes ~daily snapshots for the sqrt(trading_days) annualisation factor.
    """
    levels = [1 + p["twr_pct"] / 100 for p in twr_points if p.get("twr_pct") is not None]
    if len(levels) < min_points:
        return None
    rets = [levels[i] / levels[i - 1] - 1 for i in range(1, len(levels)) if levels[i - 1] > 0]
    if len(rets) < 2:
        return None
    return statistics.pstdev(rets) * (trading_days ** 0.5) * 100
