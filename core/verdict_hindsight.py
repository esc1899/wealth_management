"""Verdict Hindsight — deterministic feedback loop on price-directed verdicts (FEAT-59).

The system makes ~15 agents emit judgments but never grades any against what happened
next. This module closes that loop for the two *price-directed* agents — Consensus-Gap
and Devil's Advocate — with a purely deterministic computation (no LLM):

    for each past verdict → realized price change from the verdict date to +1M/+3M/+6M,
    grouped by (agent, verdict label).

Deliberately framed as a **journal / directional signal**, not a hit rate:
  - small sample (a private portfolio),
  - survivorship bias — sold/deleted positions drop out of the join (blind spot from
    FEAT-38), surfaced as ``excluded_*`` counts rather than hidden,
  - overlapping windows for re-run verdicts on the same position are not independent.

Story-intact (Storychecker) and fundamentals (Fundamental-Analyzer) verdicts are NOT
price forecasts and are intentionally excluded — grading them against price would be a
category error. They need their own outcome signal later.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

# Agents whose verdicts express a directional view that price can confirm or refute.
# Fundamental-Analyzer is included because its valuation verdict (under-/overvalued) IS a
# directional price call — unlike Storychecker (story intact) / Capital-Allocator (fit),
# which make state/quality claims and need their own outcome signal.
DIRECTIONAL_AGENTS: Tuple[str, ...] = (
    "consensus_gap",
    "devils_advocate",
    "fundamental_analyzer",
)

# Verdict labels ordered from most bullish (🟢) to most bearish (🔴). The order is used
# only for display ranking — the computation itself makes no directional claim.
VERDICT_ORDER: Dict[str, List[str]] = {
    "consensus_gap": ["wächst", "stabil", "schließt", "eingeholt"],
    "devils_advocate": ["robust", "angreifbar", "fragil", "kritisch"],
    "fundamental_analyzer": ["unterbewertet", "fair", "überbewertet"],
}

# Non-directional verdict labels that must not be graded against price (e.g. the
# Fundamental-Analyzer's "unbekannt" = could not value). Counted separately, never scored.
EXCLUDED_VERDICTS = {"unbekannt", "unknown"}

# Forward horizons: (label, days). 1M is included so the loop yields signal immediately;
# 3M/6M fill in as verdicts mature.
HORIZONS: List[Tuple[str, int]] = [("1M", 30), ("3M", 90), ("6M", 180)]

# A verdict date / target date may fall on a weekend or holiday — accept the nearest
# trading day within this window on either side.
PRICE_WINDOW_DAYS = 7

# Callable resolving (ticker, YYYY-MM-DD) → closing price in EUR, or None if unavailable.
PriceFn = Callable[[str, str], Optional[float]]

# Callable resolving a date (str) → benchmark level (portfolio value or index price).
# When provided, forward returns become EXCESS returns (verdict minus benchmark).
BenchmarkFn = Callable[[str], Optional[float]]


@dataclass
class HorizonStat:
    """Aggregated forward return for one (agent, verdict, horizon) bucket."""

    horizon: str
    days: int
    n: int = 0
    median_pct: Optional[float] = None
    mean_pct: Optional[float] = None
    best_pct: Optional[float] = None
    worst_pct: Optional[float] = None


@dataclass
class VerdictHindsight:
    """One verdict label of one agent, with its forward-return stats per horizon."""

    agent: str
    verdict: str
    total_verdicts: int = 0       # all occurrences of this label (matured or not)
    distinct_positions: int = 0   # distinct tickers behind those verdicts (concentration)
    horizons: Dict[str, HorizonStat] = field(default_factory=dict)


@dataclass
class HindsightReport:
    by_agent: Dict[str, List[VerdictHindsight]]
    horizons: List[Tuple[str, int]]
    as_of: date
    total_verdicts: int = 0       # all directional verdicts joined to a surviving ticker
    evaluated_verdicts: int = 0   # had a usable entry price
    excluded_no_price: int = 0    # no entry price within the window (e.g. fresh ticker)
    excluded_unknown: int = 0     # non-directional label (e.g. "unbekannt"), not gradeable
    total_emitted: int = 0        # all verdicts ever emitted, incl. deleted positions

    @property
    def excluded_survivorship(self) -> int:
        """Verdicts dropped because their position was sold/deleted (survivorship gap)."""
        return max(0, self.total_emitted - self.total_verdicts)

    @property
    def is_empty(self) -> bool:
        return self.evaluated_verdicts == 0


def _parse_date(value) -> Optional[date]:
    """Best-effort parse of an ISO timestamp/date string into a date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value)[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _stat(returns: List[float], horizon: str, days: int) -> HorizonStat:
    if not returns:
        return HorizonStat(horizon=horizon, days=days, n=0)
    return HorizonStat(
        horizon=horizon,
        days=days,
        n=len(returns),
        median_pct=statistics.median(returns),
        mean_pct=statistics.fmean(returns),
        best_pct=max(returns),
        worst_pct=min(returns),
    )


def compute_hindsight(
    verdict_rows: List[dict],
    price_fn: PriceFn,
    *,
    as_of: Optional[date] = None,
    total_emitted: Optional[int] = None,
    benchmark_fn: Optional[BenchmarkFn] = None,
) -> HindsightReport:
    """Grade past directional verdicts against realized forward price moves.

    Args:
        verdict_rows: rows of ``{agent, verdict, created_at, ticker}`` (already joined to
            a ticker — survivorship handled by the caller's query).
        price_fn: resolves (ticker, date) → close in EUR (nearest trading day), or None.
        as_of: evaluation date; horizons whose target lies after this are "not yet
            matured" and skipped. Defaults to today.
        total_emitted: all verdicts ever emitted by these agents (incl. positions since
            sold/deleted). When given, ``excluded_survivorship`` reports the gap so the
            blind spot is visible. Defaults to the number of rows passed in.
        benchmark_fn: optional date → benchmark level (portfolio value or index price).
            When given, every forward return is reported as an EXCESS return (verdict
            move minus benchmark move over the same window); observations whose benchmark
            level is missing at entry or target are dropped from that horizon.

    Returns:
        A HindsightReport grouped by agent then verdict (display-ordered).
    """
    as_of = as_of or date.today()

    # bucket[(agent, verdict, horizon_key)] -> list of forward returns in %
    buckets: Dict[Tuple[str, str, str], List[float]] = {}
    total_counts: Dict[Tuple[str, str], int] = {}
    positions_seen: Dict[Tuple[str, str], set] = {}

    total = evaluated = excluded_price = excluded_unknown = 0

    for row in verdict_rows:
        agent = row["agent"]
        verdict = row["verdict"]
        ticker = row["ticker"]
        entry_date = _parse_date(row["created_at"])
        if entry_date is None:
            continue

        total += 1
        if verdict in EXCLUDED_VERDICTS:
            excluded_unknown += 1
            continue
        total_counts[(agent, verdict)] = total_counts.get((agent, verdict), 0) + 1

        entry_price = price_fn(ticker, entry_date.isoformat())
        if not entry_price or entry_price <= 0:
            excluded_price += 1
            continue
        evaluated += 1
        positions_seen.setdefault((agent, verdict), set()).add(ticker)

        # Benchmark level at the verdict date (same for all horizons of this verdict).
        bench_entry = benchmark_fn(entry_date.isoformat()) if benchmark_fn else None
        if benchmark_fn and (not bench_entry or bench_entry <= 0):
            continue  # excess mode but no benchmark anchor → cannot grade this verdict

        for horizon_key, days in HORIZONS:
            target = entry_date + timedelta(days=days)
            if target > as_of:
                continue  # not yet matured
            fwd_price = price_fn(ticker, target.isoformat())
            if not fwd_price or fwd_price <= 0:
                continue
            ret_pct = (fwd_price / entry_price - 1.0) * 100.0
            if benchmark_fn:
                bench_target = benchmark_fn(target.isoformat())
                if not bench_target or bench_target <= 0:
                    continue  # no benchmark at target → cannot compute excess
                ret_pct -= (bench_target / bench_entry - 1.0) * 100.0
            buckets.setdefault((agent, verdict, horizon_key), []).append(ret_pct)

    by_agent: Dict[str, List[VerdictHindsight]] = {}
    for agent in DIRECTIONAL_AGENTS:
        ordered = VERDICT_ORDER.get(agent, [])
        # Include any unexpected verdict label not in the canonical order, appended last.
        seen = [v for (a, v) in total_counts if a == agent]
        labels = ordered + [v for v in sorted(set(seen)) if v not in ordered]

        rows: List[VerdictHindsight] = []
        for verdict in labels:
            count = total_counts.get((agent, verdict), 0)
            if count == 0:
                continue
            horizons = {
                key: _stat(buckets.get((agent, verdict, key), []), key, days)
                for key, days in HORIZONS
            }
            rows.append(
                VerdictHindsight(
                    agent=agent,
                    verdict=verdict,
                    total_verdicts=count,
                    distinct_positions=len(positions_seen.get((agent, verdict), ())),
                    horizons=horizons,
                )
            )
        if rows:
            by_agent[agent] = rows

    return HindsightReport(
        by_agent=by_agent,
        horizons=HORIZONS,
        as_of=as_of,
        total_verdicts=total,
        evaluated_verdicts=evaluated,
        excluded_no_price=excluded_price,
        excluded_unknown=excluded_unknown,
        total_emitted=total_emitted if total_emitted is not None else total,
    )
