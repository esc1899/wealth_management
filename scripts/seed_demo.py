"""
Demo database seeder.

Usage:
    python scripts/seed_demo.py

Creates data/demo.db fresh with 17 realistic positions (~€10k each at purchase date).
Uses plain SQLite (no encryption) — values stored as plain strings/floats.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date, datetime, timedelta
from typing import Optional

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yfinance as yf

# ---------------------------------------------------------------------------
# Demo position definitions
# ---------------------------------------------------------------------------

DEMO_POSITIONS = [
    # Stocks — asset_class="Aktie", investment_type="Wertpapiere", unit="Stück"
    dict(name="Apple",         ticker="AAPL",    asset_class="Aktie",        investment_type="Wertpapiere", unit="Stück",    purchase_date="2020-03-16", empfehlung="Halten"),
    dict(name="Microsoft",     ticker="MSFT",    asset_class="Aktie",        investment_type="Wertpapiere", unit="Stück",    purchase_date="2019-08-12", empfehlung="Kaufen",  story="Cloud-Dominanz mit Azure, starkes Wachstum im KI-Bereich."),
    dict(name="Amazon",        ticker="AMZN",    asset_class="Aktie",        investment_type="Wertpapiere", unit="Stück",    purchase_date="2021-04-01"),
    dict(name="Nestlé",        ticker="NESN.SW", asset_class="Aktie",        investment_type="Wertpapiere", unit="Stück",    purchase_date="2020-06-15"),
    dict(name="ASML",          ticker="ASML",    asset_class="Aktie",        investment_type="Wertpapiere", unit="Stück",    purchase_date="2021-09-01", empfehlung="Kaufen",  story="Monopolstellung bei EUV-Lithographie — unverzichtbar für die globale Chipproduktion."),
    dict(name="Siemens",       ticker="SIE.DE",  asset_class="Aktie",        investment_type="Wertpapiere", unit="Stück",    purchase_date="2022-01-10"),
    dict(name="Toyota",        ticker="TM",      asset_class="Aktie",        investment_type="Wertpapiere", unit="Stück",    purchase_date="2020-11-02"),
    dict(name="TSMC",          ticker="TSM",     asset_class="Aktie",        investment_type="Wertpapiere", unit="Stück",    purchase_date="2021-07-15", empfehlung="Halten"),
    dict(name="Novo Nordisk",  ticker="NVO",     asset_class="Aktie",        investment_type="Wertpapiere", unit="Stück",    purchase_date="2022-05-02"),
    dict(name="Alibaba",       ticker="BABA",    asset_class="Aktie",        investment_type="Wertpapiere", unit="Stück",    purchase_date="2020-09-01", empfehlung="Beobachten"),
    # ETFs / Funds
    dict(name="iShares Core MSCI World",        ticker="IWDA.AS", asset_class="Aktienfonds",    investment_type="Wertpapiere", unit="Stück", purchase_date="2020-05-04"),
    dict(name="Vanguard FTSE All-World",        ticker="VWRL.AS", asset_class="Aktienfonds",    investment_type="Wertpapiere", unit="Stück", purchase_date="2021-03-15"),
    dict(name="iShares Global Aggregate Bond",  ticker="AGGG.L",  asset_class="Rentenfonds",    investment_type="Renten",      unit="Stück", purchase_date="2019-10-07"),
    dict(name="iShares Global REIT ETF",        ticker="REET",    asset_class="Immobilienfonds", investment_type="Immobilien",  unit="Stück", purchase_date="2020-08-03"),
    # Precious metals — asset_class="Edelmetall", investment_type="Edelmetalle"
    dict(name="Gold (Unzen)",  ticker="GC=F", asset_class="Edelmetall", investment_type="Edelmetalle", unit="Troy Oz", purchase_date="2021-01-04"),
    dict(name="Gold (Gramm)",  ticker="GC=F", asset_class="Edelmetall", investment_type="Edelmetalle", unit="g",       purchase_date="2020-07-20"),
    dict(name="Silber (Gramm)",ticker="SI=F", asset_class="Edelmetall", investment_type="Edelmetalle", unit="g",       purchase_date="2022-02-14"),
    # Crypto
    dict(name="Bitcoin",       ticker="BTC-USD", asset_class="Kryptowährung", investment_type="Krypto", unit="Stück", purchase_date="2021-01-04", empfehlung="Halten", story="Digitales Gold — langfristiger Wertspeicher als Beimischung."),
    # Fixed deposit (no ticker, no yfinance)
    dict(name="Festgeld DKB 3J", ticker=None, asset_class="Festgeld", investment_type="Geld", unit="Stück",
         purchase_date="2023-03-01", quantity=10000.0, purchase_price=10000.0,
         extra_data={"interest_rate": 3.5, "maturity_date": "2026-03-01", "bank": "DKB"},
         notes="3 Jahre Laufzeit, 3,5 % p.a."),
    # Real estate (no ticker, manual valuation)
    dict(name="Eigentumswohnung München", ticker=None, asset_class="Immobilie", investment_type="Immobilien", unit="Stück",
         purchase_date="2018-06-15", quantity=1.0, purchase_price=320000.0,
         extra_data={"estimated_value": 410000.0, "valuation_date": "2024-11-01"},
         notes="3-Zimmer-Wohnung, 75 qm, Maxvorstadt"),
]

# Fallback prices in USD if yfinance fails (approximate historical prices)
FALLBACK_PRICES_USD: dict[str, float] = {
    "AAPL":    60.0,
    "MSFT":   130.0,
    "AMZN":  3200.0,
    "NESN.SW": 100.0,
    "ASML":   600.0,
    "SIE.DE":  120.0,
    "TM":      140.0,
    "TSM":     100.0,
    "NVO":      80.0,
    "BABA":    220.0,
    "IWDA.AS": 58.0,
    "VWRL.AS": 88.0,
    "AGGG.L":   5.0,
    "REET":    25.0,
    "GC=F":  1850.0,
    "SI=F":    24.0,
    "BTC-USD": 35000.0,
}

TROY_OZ_TO_GRAM = 31.1035
TARGET_EUR = 10_000.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_price_on_date(ticker: str, purchase_date: str) -> Optional[float]:
    """
    Fetch the closing price (in original currency) on or nearest to purchase_date.
    Looks in a ±10-day window to handle weekends/holidays.
    Returns None on failure.
    """
    try:
        d = date.fromisoformat(purchase_date)
        start = (d - timedelta(days=5)).isoformat()
        end   = (d + timedelta(days=10)).isoformat()
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if df is None or df.empty:
            return None
        # Use "Close" column; handle MultiIndex from yfinance ≥0.2
        close = df["Close"]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        # Find the row closest to purchase_date
        target = pd.Timestamp(d)
        idx = close.index.searchsorted(target)
        idx = min(idx, len(close) - 1)
        price = float(close.iloc[idx])
        return price if price > 0 else None
    except Exception:
        return None


def _fetch_eurusd_rate_on_date(purchase_date: str) -> float:
    """Fetch EUR/USD rate on purchase_date (i.e., how many USD per 1 EUR)."""
    try:
        d = date.fromisoformat(purchase_date)
        start = (d - timedelta(days=5)).isoformat()
        end   = (d + timedelta(days=10)).isoformat()
        df = yf.download("EURUSD=X", start=start, end=end, progress=False, auto_adjust=True)
        if df is None or df.empty:
            return 1.10
        close = df["Close"]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        target = pd.Timestamp(d)
        idx = close.index.searchsorted(target)
        idx = min(idx, len(close) - 1)
        rate = float(close.iloc[idx])
        return rate if rate > 0 else 1.10
    except Exception:
        return 1.10


def _fetch_gbpusd_rate_on_date(purchase_date: str) -> float:
    """Fetch GBP/USD rate on purchase_date."""
    try:
        d = date.fromisoformat(purchase_date)
        start = (d - timedelta(days=5)).isoformat()
        end   = (d + timedelta(days=10)).isoformat()
        df = yf.download("GBPUSD=X", start=start, end=end, progress=False, auto_adjust=True)
        if df is None or df.empty:
            return 1.28
        close = df["Close"]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        target = pd.Timestamp(d)
        idx = close.index.searchsorted(target)
        idx = min(idx, len(close) - 1)
        rate = float(close.iloc[idx])
        return rate if rate > 0 else 1.28
    except Exception:
        return 1.28


def _fetch_chfusd_rate_on_date(purchase_date: str) -> float:
    """Fetch CHF/USD rate on purchase_date."""
    try:
        d = date.fromisoformat(purchase_date)
        start = (d - timedelta(days=5)).isoformat()
        end   = (d + timedelta(days=10)).isoformat()
        df = yf.download("CHFUSD=X", start=start, end=end, progress=False, auto_adjust=True)
        if df is None or df.empty:
            return 1.05
        close = df["Close"]
        if hasattr(close, "columns"):
            close = close.iloc[:, 0]
        target = pd.Timestamp(d)
        idx = close.index.searchsorted(target)
        idx = min(idx, len(close) - 1)
        rate = float(close.iloc[idx])
        return rate if rate > 0 else 1.05
    except Exception:
        return 1.05


def _detect_currency(ticker: str) -> str:
    """Heuristic: detect native currency from ticker suffix / known symbols."""
    t = ticker.upper()
    if t.endswith(".DE") or t.endswith(".AS"):
        return "EUR"
    if t.endswith(".SW"):
        return "CHF"
    if t.endswith(".L"):
        return "GBP"
    # Commodities and US stocks default to USD
    return "USD"


def _price_to_eur(price_native: float, currency: str, purchase_date: str) -> float:
    """Convert native price to EUR."""
    if currency == "EUR":
        return price_native
    if currency == "USD":
        eurusd = _fetch_eurusd_rate_on_date(purchase_date)
        return price_native / eurusd
    if currency == "GBP":
        # GBP -> USD -> EUR
        gbpusd = _fetch_gbpusd_rate_on_date(purchase_date)
        eurusd = _fetch_eurusd_rate_on_date(purchase_date)
        usd = price_native * gbpusd
        return usd / eurusd
    if currency == "CHF":
        # CHF -> USD -> EUR
        chfusd = _fetch_chfusd_rate_on_date(purchase_date)
        eurusd = _fetch_eurusd_rate_on_date(purchase_date)
        usd = price_native * chfusd
        return usd / eurusd
    # Unknown: assume EUR
    return price_native


def _compute_quantity(price_eur: float, unit: str, ticker: str) -> float:
    """
    Calculate quantity so that total purchase value ≈ €10,000.
    For precious metals in grams: price_eur is per troy oz, convert to per gram.
    """
    if unit == "g":
        # price_eur is per troy oz; 1 troy oz = 31.1035 g
        price_per_gram = price_eur / TROY_OZ_TO_GRAM
        qty = TARGET_EUR / price_per_gram
        step = 500 if qty > 1000 else 100
        return float(round(qty / step) * step)  # round to nearest 500g (large) or 100g (small)
    elif unit == "Troy Oz":
        qty = TARGET_EUR / price_eur
        return float(round(qty))  # whole oz
    else:
        # Stück (stocks, ETFs) — whole numbers
        qty = TARGET_EUR / price_eur
        return float(round(qty))


def _purchase_price_per_unit(price_eur: float, unit: str) -> float:
    """Return price per unit in EUR."""
    if unit == "g":
        return round(price_eur / TROY_OZ_TO_GRAM, 4)
    return round(price_eur, 4)


# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

def _init_db(conn: sqlite3.Connection) -> None:
    """Create tables (copied from core/storage/base.py)."""
    statements = [
        """CREATE TABLE IF NOT EXISTS positions (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_class           TEXT NOT NULL,
            investment_type       TEXT NOT NULL,
            name                  TEXT NOT NULL,
            isin                  TEXT,
            wkn                   TEXT,
            ticker                TEXT,
            quantity              TEXT,
            unit                  TEXT NOT NULL,
            purchase_price        TEXT,
            purchase_date         TEXT,
            notes                 TEXT,
            extra_data            TEXT,
            recommendation_source TEXT,
            strategy              TEXT,
            added_date            TEXT NOT NULL,
            in_portfolio          INTEGER NOT NULL DEFAULT 0,
            empfehlung            TEXT,
            story                 TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS app_config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker)",
        "CREATE INDEX IF NOT EXISTS idx_positions_in_portfolio ON positions(in_portfolio)",
        """CREATE TABLE IF NOT EXISTS current_prices (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol            TEXT NOT NULL UNIQUE,
            price_eur         REAL NOT NULL,
            currency_original TEXT NOT NULL,
            price_original    REAL NOT NULL,
            exchange_rate     REAL NOT NULL,
            fetched_at        TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS historical_prices (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol    TEXT NOT NULL,
            date      TEXT NOT NULL,
            close_eur REAL NOT NULL,
            volume    INTEGER,
            UNIQUE(symbol, date)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_hist_prices_symbol_date ON historical_prices(symbol, date)",
    ]
    for stmt in statements:
        conn.execute(stmt)
    conn.commit()


# ---------------------------------------------------------------------------
# Market data helpers (current prices for price_history)
# ---------------------------------------------------------------------------

def _fetch_current_price(ticker: str) -> Optional[tuple[float, str, float, float]]:
    """
    Returns (price_eur, currency, price_original, exchange_rate) or None.
    """
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price_original = float(info.last_price)
        currency = (info.currency or "USD").upper()
        if currency == "EUR":
            return price_original, currency, price_original, 1.0
        today = date.today().isoformat()
        if currency == "USD":
            eurusd = _fetch_eurusd_rate_on_date(today)
            return price_original / eurusd, currency, price_original, eurusd
        if currency == "GBP":
            gbpusd = _fetch_gbpusd_rate_on_date(today)
            eurusd = _fetch_eurusd_rate_on_date(today)
            usd = price_original * gbpusd
            return usd / eurusd, currency, price_original, gbpusd / eurusd
        if currency == "CHF":
            chfusd = _fetch_chfusd_rate_on_date(today)
            eurusd = _fetch_eurusd_rate_on_date(today)
            usd = price_original * chfusd
            return usd / eurusd, currency, price_original, chfusd / eurusd
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main seeder
# ---------------------------------------------------------------------------

def seed(db_path: str = "data/demo.db", conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    """
    Seed the demo database.

    Parameters
    ----------
    db_path:
        Path to the SQLite file to create. Ignored when ``conn`` is provided.
    conn:
        Existing SQLite connection to use (e.g. for in-memory testing).
        When provided ``db_path`` is not touched.

    Returns
    -------
    List of dicts with seeded position data (useful for tests).
    """
    import pandas as pd  # local import so the module is importable without pandas at top level

    own_conn = conn is None
    if own_conn:
        # Delete and recreate the file
        if db_path != ":memory:" and os.path.exists(db_path):
            os.remove(db_path)
            print(f"Deleted existing {db_path}")
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

    _init_db(conn)

    inserted: list[dict] = []
    today = date.today().isoformat()

    import json as _json

    for pos in DEMO_POSITIONS:
        ticker = pos.get("ticker")
        name   = pos["name"]
        unit   = pos["unit"]
        purchase_date = pos["purchase_date"]
        empfehlung = pos.get("empfehlung")
        story = pos.get("story")
        extra_data_raw = pos.get("extra_data")

        print(f"  Seeding {name} ({ticker or 'no-ticker'}, {purchase_date}) ...", end=" ", flush=True)

        # Manual positions: quantity and price provided directly
        if ticker is None or pos.get("quantity") is not None:
            quantity = pos.get("quantity", 1.0)
            purchase_price = pos.get("purchase_price", 0.0)
            price_eur = purchase_price
            used_fallback = False
            print(f"manual qty={quantity} @ €{purchase_price:.2f}")
        else:
            # --- fetch historical price ---
            price_native = _fetch_price_on_date(ticker, purchase_date)
            used_fallback = False
            if price_native is None:
                price_native = FALLBACK_PRICES_USD.get(ticker, 100.0)
                used_fallback = True
                print(f"[fallback {price_native}]", end=" ", flush=True)

            currency = _detect_currency(ticker)
            price_eur = _price_to_eur(price_native, currency, purchase_date)

            quantity = _compute_quantity(price_eur, unit, ticker)
            purchase_price = _purchase_price_per_unit(price_eur, unit)
            approx_value = quantity * purchase_price
            print(f"qty={quantity} @ €{purchase_price:.4f} ≈ €{approx_value:,.0f}")

        extra_data_str = _json.dumps(extra_data_raw) if extra_data_raw else None
        notes = pos.get("notes")

        # Store values as plain strings (no encryption in demo mode)
        conn.execute(
            """
            INSERT INTO positions (
                asset_class, investment_type,
                name, isin, wkn, ticker,
                quantity, unit, purchase_price, purchase_date,
                notes, extra_data,
                recommendation_source, strategy,
                added_date, in_portfolio,
                empfehlung, story
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pos["asset_class"],
                pos["investment_type"],
                name,
                None,         # isin
                None,         # wkn
                ticker,
                str(quantity),
                unit,
                str(purchase_price),
                purchase_date,
                notes,
                extra_data_str,
                None,         # recommendation_source
                None,         # strategy
                today,
                1,            # in_portfolio
                empfehlung,
                story,
            ),
        )
        conn.commit()

        inserted.append({
            "name": name,
            "ticker": ticker,
            "unit": unit,
            "purchase_date": purchase_date,
            "quantity": quantity,
            "purchase_price": purchase_price,
            "price_eur_at_purchase": price_eur,
            "used_fallback": used_fallback,
        })

    # --- fetch current prices and store in current_prices ---
    print("\nFetching current market prices ...")
    seen_tickers: set[str] = set()
    for pos in DEMO_POSITIONS:
        if not pos.get("ticker"):
            continue
        ticker = pos["ticker"].upper()
        if ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)

        result = _fetch_current_price(ticker)
        if result is None:
            print(f"  {ticker}: current price fetch failed — skipping")
            continue
        price_eur, currency, price_original, exchange_rate = result
        conn.execute(
            """
            INSERT OR REPLACE INTO current_prices
                (symbol, price_eur, currency_original, price_original, exchange_rate, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (ticker, price_eur, currency, price_original, exchange_rate, datetime.utcnow().isoformat()),
        )
        conn.commit()
        print(f"  {ticker}: €{price_eur:.4f} ({currency} {price_original:.4f})")

    # --- fetch historical prices (1y) ---
    print("\nFetching historical prices (1y) ...")
    from agents.market_data_fetcher import MarketDataFetcher
    from core.storage.market_data import MarketDataRepository

    market_repo = MarketDataRepository(conn)
    fetcher = MarketDataFetcher()
    for ticker in seen_tickers:
        history = fetcher.fetch_historical(ticker, period="1y")
        for h in history:
            market_repo.upsert_historical(h)
        print(f"  {ticker}: {len(history)} Datenpunkte")

    if own_conn:
        conn.close()
        print(f"\nDemo database seeded at {os.path.abspath(db_path)}")
        print(f"Total positions: {len(inserted)}")

    return inserted


if __name__ == "__main__":
    import pandas as pd  # noqa: F401 — ensure available before seed()
    db_path = os.getenv("DEMO_DB_PATH", "data/demo.db")
    print(f"Seeding demo database: {db_path}\n")
    seed(db_path)
