"""Buyback yield from yfinance shares-outstanding history (FEAT-71).

Net buyback yield over a trailing ~1-year window: how much the share count shrank
(positive = net buybacks accreting each holder's ownership, negative = dilution).
Combined with the dividend yield it forms the Total Shareholder Yield that feeds the
accumulation indicator's income engine — so buyback-driven compounders (Amazon and
many US-tech names that pay no dividend) become measurable instead of "not applicable".

yfinance fundamentals are patchy: every function returns ``None`` on missing data or
any network/parse error, so the indicator degrades gracefully to dividend-only.
"""
from __future__ import annotations

import datetime as dt
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Tuple

import yfinance as yf

logger = logging.getLogger(__name__)

# Trailing window for the share-count delta. ~14 months so a position with only a
# couple of yearly data points still spans roughly one year.
_WINDOW_DAYS = 420


def buyback_yield(ticker: str) -> Optional[float]:
    """Return the net buyback yield as a decimal (0.022 = 2.2 %), or ``None``.

    ``(shares_old - shares_new) / shares_old`` over the trailing window. Positive means
    the share count shrank (net buybacks); negative means dilution. Returns ``None`` if
    the ticker is unknown, the history is empty/single-point, or any error occurs.
    """
    if not ticker:
        return None
    try:
        start = (dt.date.today() - dt.timedelta(days=_WINDOW_DAYS)).isoformat()
        series = yf.Ticker(ticker).get_shares_full(start=start)
        if series is None or len(series) < 2:
            return None
        # Collapse duplicate timestamps, sort chronologically, take first vs. last.
        series = series[~series.index.duplicated(keep="last")].sort_index()
        old = float(series.iloc[0])
        new = float(series.iloc[-1])
        if old <= 0:
            return None
        return (old - new) / old
    except Exception as exc:  # pragma: no cover - network/parse guard
        logger.debug("Buyback yield fetch failed for %r: %s", ticker, exc)
        return None


def buyback_yield_map(tickers: Tuple[str, ...]) -> Dict[str, Optional[float]]:
    """Fetch buyback yields for several tickers concurrently → {TICKER(upper): yield|None}.

    Pages should wrap this in ``@st.cache_data`` (the values barely move day to day).
    """
    uniq = sorted({t.upper() for t in tickers if t})
    if not uniq:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(uniq))) as pool:
        results = pool.map(buyback_yield, uniq)
    return dict(zip(uniq, results))


try:  # Streamlit-cached wrapper for page use — buyback ratios barely move day to day.
    import streamlit as st

    @st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
    def cached_buyback_yield_map(tickers: Tuple[str, ...]) -> Dict[str, Optional[float]]:
        """Cached (1 day) variant of :func:`buyback_yield_map` for page render loops."""
        return buyback_yield_map(tickers)
except ImportError:  # pragma: no cover - streamlit always present in the app
    cached_buyback_yield_map = buyback_yield_map  # type: ignore[assignment]
