"""
Macro context — fetches VIX, EUR/USD, Gold, and DAX indicator via yfinance.

Cached in app_config under key "macro_context" with a configurable TTL.
No LLM required: all data is public market data from yfinance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_APP_CONFIG_KEY = "macro_context"

# yfinance tickers for macro indicators
_VIX_TICKER = "^VIX"
_USD_EUR_TICKER = "USDEUR=X"   # USD → EUR rate (same format as existing market_data_fetcher)
_GOLD_TICKER = "GC=F"         # Gold futures (front month) in USD per troy oz
_DAX_TICKER = "^GDAXI"


@dataclass
class MacroIndicators:
    vix: Optional[float]
    eur_usd: Optional[float]       # display value (EUR per USD ≈ 0.925) — store as-is from USDEUR=X
    gold_eur: Optional[float]      # gold spot price in EUR per troy oz
    dax_change_pct: Optional[float]
    fetched_at: str     # ISO string for JSON serialisation


def fetch_macro_indicators() -> MacroIndicators:
    """Fetch live macro indicators via yfinance. Returns MacroIndicators with best-effort values."""
    import yfinance as yf

    vix = _fetch_last_price(yf, _VIX_TICKER)
    # USDEUR=X: price of 1 USD in EUR (e.g. 0.925) — same format as existing market_data_fetcher
    usd_eur = _fetch_last_price(yf, _USD_EUR_TICKER)
    gold_usd = _fetch_last_price(yf, _GOLD_TICKER)
    dax_change = _fetch_day_change_pct(yf, _DAX_TICKER)

    # EUR/USD display value (inverted): how many USD per 1 EUR ≈ 1.082
    eur_usd_display: Optional[float] = (1.0 / usd_eur) if (usd_eur and usd_eur > 0) else None

    # Gold: multiply USD/oz by USD→EUR rate (same approach as market_data_fetcher._get_eur_rate)
    gold_eur: Optional[float] = None
    if gold_usd is not None and usd_eur is not None and usd_eur > 0:
        gold_eur = gold_usd * usd_eur

    return MacroIndicators(
        vix=vix,
        eur_usd=eur_usd_display,
        gold_eur=gold_eur,
        dax_change_pct=dax_change,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def load_or_refresh_macro(app_config_repo, max_age_hours: float = 4.0) -> Optional[MacroIndicators]:
    """
    Load macro indicators from app_config cache, refreshing if stale or missing.

    Returns None only if fetch fails and no cached data exists.
    """
    cached = app_config_repo.get_json(_APP_CONFIG_KEY)
    if cached:
        try:
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            age_hours = (datetime.now(timezone.utc) - fetched_at).total_seconds() / 3600
            if age_hours < max_age_hours:
                return _from_dict(cached)
        except (KeyError, ValueError):
            pass

    try:
        indicators = fetch_macro_indicators()
        app_config_repo.set_json(_APP_CONFIG_KEY, asdict(indicators))
        return indicators
    except Exception as e:
        logger.warning("Macro context fetch failed: %s", e)
        if cached:
            try:
                return _from_dict(cached)
            except Exception:
                pass
        return None


def _fetch_last_price(yf, symbol: str) -> Optional[float]:
    try:
        ticker = yf.Ticker(symbol)
        price = getattr(ticker.fast_info, "last_price", None)
        if price and price > 0:
            return float(price)
    except Exception as e:
        logger.debug("Failed to fetch %s: %s", symbol, e)
    return None


def _fetch_day_change_pct(yf, symbol: str) -> Optional[float]:
    """Return today's price change in percent vs. previous close."""
    try:
        ticker = yf.Ticker(symbol)
        current = getattr(ticker.fast_info, "last_price", None)
        prev_close = getattr(ticker.fast_info, "previous_close", None)
        if current and prev_close and prev_close > 0:
            return (current - prev_close) / prev_close * 100
    except Exception as e:
        logger.debug("Failed to fetch day change for %s: %s", symbol, e)
    return None


def _from_dict(d: dict) -> MacroIndicators:
    return MacroIndicators(
        vix=d.get("vix"),
        eur_usd=d.get("eur_usd"),
        gold_eur=d.get("gold_eur"),
        dax_change_pct=d.get("dax_change_pct"),
        fetched_at=d["fetched_at"],
    )
