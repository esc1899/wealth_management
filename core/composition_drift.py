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


def share_count_series(snapshots) -> Dict[str, dict]:
    """Per-position share count over time, from snapshot holdings — the accumulation ratchet.

    Returns {ticker: {"name": str, "points": [{date, quantity}, ...]}}. Only snapshots WITH
    holdings contribute; per position only points where quantity is not None are kept. Tickers
    that never carry a quantity are omitted. Points follow snapshot order (ascending date).

    Unlike market value, the share count grows monotonically with reinvestment and is
    price-independent — it makes the otherwise-invisible accumulation visible.
    """
    out: Dict[str, dict] = {}
    for snap in snapshots:
        holdings = getattr(snap, "holdings", None)
        if not holdings:
            continue
        for h in holdings:
            ticker = h.get("ticker")
            qty = h.get("quantity")
            if not ticker or qty is None:
                continue
            entry = out.setdefault(ticker, {"name": h.get("name") or ticker, "points": []})
            entry["points"].append({"date": snap.date, "quantity": qty})
    return out


def portfolio_income_series(snapshots) -> List[dict]:
    """Portfolio-level forward annual dividend over time — the aggregate income ratchet.

    Per snapshot WITH holdings: {date, total_annual_dividend_eur, total_value_eur, yield_pct}.
    Sums annual_dividend_eur / value_eur across positions (missing values treated as 0).
    yield_pct = income / value * 100 (0.0 when value <= 0). Snapshots without holdings skipped.
    """
    series: List[dict] = []
    for snap in snapshots:
        holdings = getattr(snap, "holdings", None)
        if not holdings:
            continue
        income = sum((h.get("annual_dividend_eur") or 0) for h in holdings)
        value = sum((h.get("value_eur") or 0) for h in holdings)
        series.append({
            "date": snap.date,
            "total_annual_dividend_eur": income,
            "total_value_eur": value,
            "yield_pct": (income / value * 100) if value > 0 else 0.0,
        })
    return series


def value_decomposition_series(snapshots) -> List[dict]:
    """Decompose cumulative portfolio value growth into price vs. share-accumulation effects.

    Over consecutive holdings-bearing snapshots, for every ticker present in BOTH:
      quantity_effect += (q1 - q0) * p1   (value of shares added, at the new price)
      price_effect    += q0 * (p1 - p0)   (appreciation of the originally held shares)
    This is the exact, residual-free two-factor split (their sum equals Δ(q*p)). A ticker new
    to the later snapshot contributes its full value as quantity_effect (fresh position, not a
    market move); a ticker that disappears is simply dropped from then on.

    Returns [{date, cum_price_effect, cum_quantity_effect}] cumulated forward, starting at 0.0
    on the first holdings-bearing date. Returns [] with fewer than two such snapshots.

    Honest limit: quantity_effect captures EVERY share increase (purchases incl. reinvested
    dividends) — the snapshots cannot separate reinvested dividends from fresh capital.
    """
    holding_snaps = [s for s in snapshots if getattr(s, "holdings", None)]
    if len(holding_snaps) < 2:
        return []

    def _by_ticker(snap) -> Dict[str, dict]:
        out: Dict[str, dict] = {}
        for h in snap.holdings or []:
            ticker = h.get("ticker")
            if ticker:
                out[ticker] = h
        return out

    cum_price = 0.0
    cum_qty = 0.0
    series: List[dict] = [{
        "date": holding_snaps[0].date,
        "cum_price_effect": 0.0,
        "cum_quantity_effect": 0.0,
    }]

    prev = _by_ticker(holding_snaps[0])
    for snap in holding_snaps[1:]:
        cur = _by_ticker(snap)
        for ticker, h in cur.items():
            q1 = h.get("quantity")
            p1 = h.get("price_eur")
            if q1 is None or p1 is None:
                continue
            old = prev.get(ticker)
            if old is None or old.get("quantity") is None or old.get("price_eur") is None:
                # New position this interval — full value is accumulation, not a price move.
                cum_qty += q1 * p1
                continue
            q0 = old["quantity"]
            p0 = old["price_eur"]
            cum_qty += (q1 - q0) * p1
            cum_price += q0 * (p1 - p0)
        series.append({
            "date": snap.date,
            "cum_price_effect": cum_price,
            "cum_quantity_effect": cum_qty,
        })
        prev = cur
    return series


def sold_positions_summary(snapshots) -> List[dict]:
    """Positions that appear in past holdings but are no longer currently held.

    "Currently held" = tickers in the most recent snapshot WITH holdings (self-contained).
    For every ticker seen in earlier holdings but absent from that set, summarise its held
    window from the stored points: {ticker, name, first_date, last_date, last_value_eur,
    first_price_eur, last_price_eur, price_change_pct}. price_change_pct is the per-share
    change from first→last recorded price while held (None if a price is missing).
    Returns [] when fewer than two holdings-bearing snapshots exist or none were sold.
    Sorted by last_date descending.
    """
    holding_snaps = [s for s in snapshots if getattr(s, "holdings", None)]
    if len(holding_snaps) < 2:
        return []

    current = {h.get("ticker") for h in (holding_snaps[-1].holdings or []) if h.get("ticker")}

    # Collect per-ticker points across all but the latest snapshot
    seen: Dict[str, dict] = {}
    for snap in holding_snaps:
        for h in snap.holdings or []:
            ticker = h.get("ticker")
            if not ticker or ticker in current:
                continue
            entry = seen.setdefault(ticker, {"name": h.get("name") or ticker, "points": []})
            entry["points"].append({
                "date": snap.date,
                "price_eur": h.get("price_eur"),
                "value_eur": h.get("value_eur"),
            })

    summary: List[dict] = []
    for ticker, data in seen.items():
        pts = data["points"]
        first, last = pts[0], pts[-1]
        first_price, last_price = first.get("price_eur"), last.get("price_eur")
        change_pct = None
        if first_price and last_price and first_price > 0:
            change_pct = (last_price / first_price - 1) * 100
        summary.append({
            "ticker": ticker,
            "name": data["name"],
            "first_date": first["date"],
            "last_date": last["date"],
            "last_value_eur": last.get("value_eur"),
            "first_price_eur": first_price,
            "last_price_eur": last_price,
            "price_change_pct": change_pct,
        })

    summary.sort(key=lambda r: r["last_date"], reverse=True)
    return summary


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
