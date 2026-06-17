"""
Composition drift over time — derived from the wealth-snapshot time series.
Pure, deterministic computations (no LLM, no network):

- concentration_series: position-level concentration (Top-N share, HHI) per snapshot
  that stored its holdings. Forward-only — snapshots without `holdings` are skipped.
- asset_class_mix_series: relative asset-class weights (%) per snapshot, from the
  always-present `breakdown`. Works for every snapshot (incl. legacy).
"""

from __future__ import annotations

from typing import Dict, List, Tuple


def concentration_series(snapshots) -> List[dict]:
    """Per snapshot WITH holdings, return concentration metrics.

    Each entry: {date, top1_pct, top3_pct, top5_pct, hhi, effective_n, n}.
    Weights are value_eur_i / Σ value_eur over positions with a positive value.
    HHI = Σ weight_i² (fraction, range (0,1]); effective_n = 1 / HHI.
    Snapshots without holdings (legacy) are skipped.
    """
    series: List[dict] = []
    for snap in snapshots:
        holdings = getattr(snap, "holdings", None)
        if not holdings:
            continue
        values = sorted(
            (h.get("value_eur") for h in holdings if (h.get("value_eur") or 0) > 0),
            reverse=True,
        )
        total = sum(values)
        if total <= 0:
            continue
        weights = [v / total for v in values]
        hhi = sum(w * w for w in weights)
        series.append({
            "date": snap.date,
            "top1_pct": sum(weights[:1]) * 100,
            "top3_pct": sum(weights[:3]) * 100,
            "top5_pct": sum(weights[:5]) * 100,
            "hhi": hhi,
            "effective_n": (1 / hhi) if hhi > 0 else 0.0,
            "n": len(values),
        })
    return series


def dividend_history_series(snapshots) -> Dict[str, dict]:
    """Per-position annual dividend over time, from snapshot holdings.

    Returns {ticker: {"name": str, "points": [{date, annual_dividend_eur,
    dividend_yield_pct}, ...]}}. Only snapshots WITH holdings contribute; per position
    only points where annual_dividend_eur is not None are kept. Tickers that never carry
    a dividend data point are omitted. Points follow snapshot order (ascending date).
    """
    out: Dict[str, dict] = {}
    for snap in snapshots:
        holdings = getattr(snap, "holdings", None)
        if not holdings:
            continue
        for h in holdings:
            ticker = h.get("ticker")
            div = h.get("annual_dividend_eur")
            if not ticker or div is None:
                continue
            entry = out.setdefault(ticker, {"name": h.get("name") or ticker, "points": []})
            entry["points"].append({
                "date": snap.date,
                "annual_dividend_eur": div,
                "dividend_yield_pct": h.get("dividend_yield_pct"),
            })
    return out


def asset_class_mix_series(snapshots) -> Tuple[List[str], Dict[str, List[float]]]:
    """Relative asset-class weights (%) per snapshot, from `breakdown`.

    Returns (dates, {asset_class: [pct per date]}). Each snapshot's percentages
    sum to 100 (when its breakdown total > 0); absent classes contribute 0.
    """
    dates: List[str] = [s.date for s in snapshots]
    all_classes = set()
    for s in snapshots:
        all_classes.update((s.breakdown or {}).keys())

    mix: Dict[str, List[float]] = {ac: [] for ac in sorted(all_classes)}
    for s in snapshots:
        breakdown = s.breakdown or {}
        total = sum(v for v in breakdown.values() if v)
        for ac in mix:
            val = breakdown.get(ac, 0) or 0
            mix[ac].append((val / total * 100) if total > 0 else 0.0)
    return dates, mix
