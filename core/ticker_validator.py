"""Lightweight yfinance ticker existence check."""
from __future__ import annotations

import logging

import yfinance as yf

logger = logging.getLogger(__name__)

# Most common exchange suffixes for internationally-listed stocks.
# Shown as suggestions when a ticker cannot be found without a suffix.
COMMON_SUFFIXES = [".AX", ".T", ".OL", ".L", ".DE", ".F", ".PA", ".SW", ".HK", ".TO", ".MC", ".SI"]


def validate_ticker(ticker: str) -> bool:
    """Return True if yfinance returns a price for *ticker*.

    Uses fast_info (single lightweight HTTP request). Returns False if the
    ticker is unknown, delisted, or any network/parse error occurs.
    """
    try:
        info = yf.Ticker(ticker).fast_info
        return getattr(info, "last_price", None) is not None
    except Exception as exc:
        logger.debug("Ticker validation failed for %r: %s", ticker, exc)
        return False
