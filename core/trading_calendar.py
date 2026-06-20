"""
Minimal trading-day helpers — pure, deterministic (no network, no dependency).

Used to suppress pointless market-data fetches on non-trading days: prices do not
change while exchanges are closed, so once the most recent session's close is captured
there is nothing new to pull until the next session.

Scope: weekend-aware only (Sat/Sun are non-trading worldwide). Exchange holidays are
NOT modelled — on a holiday the worst case is a single fetch that returns the prior
close (harmless). Weekends are the bulk of non-trading days (2 of 7). A future refinement
could add a holiday calendar here without touching callers.
"""

from __future__ import annotations

from datetime import date, timedelta


def is_trading_day(d: date) -> bool:
    """True on Mon–Fri, False on Sat/Sun."""
    return d.weekday() < 5


def last_trading_day(d: date) -> date:
    """Most recent trading day on or before ``d`` (skips back over Sat/Sun)."""
    cur = d
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur
