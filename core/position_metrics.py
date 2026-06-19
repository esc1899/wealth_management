"""
Deterministic price-return metrics from our own stored history — pure, no LLM / no network.

Search-capable LLMs (esp. OpenAI-compatible ones) confabulate performance figures or misread
"N/A" as "0.00 %". Instead of letting an agent web-search returns, we compute them from
``historical_prices`` and hand them over as a verified block. Windows the history can't cover
(e.g. 3y/5y with ~14 months of data) are reported as "not available" — never faked.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

# Trailing windows in days. YTD is handled separately.
_WINDOWS = [
    ("r1m", 30),
    ("r3m", 91),
    ("r6m", 182),
    ("r1y", 365),
    ("r3y", 1095),
    ("r5y", 1825),
]
_TOLERANCE_DAYS = 7


def _close_near(points: List[tuple], target: date) -> Optional[float]:
    """Closest close to ``target`` within ±_TOLERANCE_DAYS, else None.

    ``points`` is a list of (date, close) sorted ascending.
    """
    best = None
    best_dist = None
    for d, close in points:
        dist = abs((d - target).days)
        if dist <= _TOLERANCE_DAYS and (best_dist is None or dist < best_dist):
            best, best_dist = close, dist
    return best


def compute_return_metrics(historical, asof: Optional[date] = None) -> dict:
    """Return {current_price, ytd, r1m, r3m, r6m, r1y, r3y, r5y} (percent floats or None).

    ``historical`` is a list of objects with ``.date`` (date) and ``.close_eur`` (float).
    Returns all-None (current_price=None) when there is no usable history.
    """
    points = sorted(
        ((h.date, h.close_eur) for h in historical if h.close_eur and h.close_eur > 0),
        key=lambda p: p[0],
    )
    out = {"current_price": None, "ytd": None, "r1m": None, "r3m": None,
           "r6m": None, "r1y": None, "r3y": None, "r5y": None}
    if not points:
        return out

    last_date, last_close = points[-1]
    out["current_price"] = last_close
    asof = asof or last_date

    def _pct(base: Optional[float]) -> Optional[float]:
        if base and base > 0:
            return (last_close / base - 1) * 100
        return None

    # YTD: prefer the previous year's last close; fall back to the first close of this year.
    year_start = date(asof.year, 1, 1)
    prior = [(d, c) for d, c in points if d < year_start]
    if prior:
        out["ytd"] = _pct(prior[-1][1])
    else:
        this_year = [(d, c) for d, c in points if d >= year_start]
        if this_year:
            out["ytd"] = _pct(this_year[0][1])

    for key, days in _WINDOWS:
        out[key] = _pct(_close_near(points, asof - timedelta(days=days)))
    return out


def _fmt(pct: Optional[float], unavailable: str) -> str:
    return f"{pct:+.1f} %" if pct is not None else unavailable


def build_metrics_block(historical, asof: Optional[date] = None, language: str = "de") -> str:
    """Render the verified-metrics block for the agent prompt, or "" when no history.

    The explicit "not available" rows (incl. 3y/5y) are the point: they stop the model from
    inventing a long-run figure (e.g. the bogus "5-year 0.00 %").
    """
    m = compute_return_metrics(historical, asof)
    if m["current_price"] is None:
        return ""
    asof = asof or max(h.date for h in historical)
    de = language == "de"
    na = "nicht verfügbar" if de else "not available"

    rows = [
        ("YTD", m["ytd"]),
        ("1M", m["r1m"]),
        ("3M", m["r3m"]),
        ("6M", m["r6m"]),
        ("1J" if de else "1Y", m["r1y"]),
        ("3J" if de else "3Y", m["r3y"]),
        ("5J" if de else "5Y", m["r5y"]),
    ]
    if de:
        header = f"**Verifizierte Kennzahlen (eigene Kursdaten, Stand {asof.strftime('%d.%m.%Y')}):**"
        price_line = f"- Aktueller Kurs: {m['current_price']:.2f} EUR"
        note = ("Nutze für Performance-/Kurszahlen AUSSCHLIESSLICH diese verifizierten Werte. "
                "Erfinde keine eigenen Zahlen; behandle 'nicht verfügbar' als fehlend (nicht als 0 %).")
    else:
        header = f"**Verified metrics (own price data, as of {asof.strftime('%Y-%m-%d')}):**"
        price_line = f"- Current price: {m['current_price']:.2f} EUR"
        note = ("Use ONLY these verified values for performance/price figures. "
                "Do not invent numbers; treat \"not available\" as missing (not as 0 %).")

    lines = [header, price_line]
    lines += [f"- {label}: {_fmt(val, na)}" for label, val in rows]
    lines.append(note)
    return "\n".join(lines)
