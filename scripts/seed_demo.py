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
from datetime import date, datetime, timedelta, timezone
from typing import Optional

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yfinance as yf

from core.storage.base import init_db, migrate_db

# ---------------------------------------------------------------------------
# Demo analyses — frei erfunden, nur für Demonstrationszwecke
# Gekennzeichnet mit skill_name = "Demodaten"
# ---------------------------------------------------------------------------

_D = "[Demodaten] "  # prefix for all demo summaries

# storychecker: only for positions that have a story
DEMO_STORYCHECKER: dict[str, dict] = {
    "Microsoft": dict(
        verdict="intact",
        summary=_D + "Azure wächst weiter zweistellig, KI-Integration (Copilot) zeigt frühe Monetarisierung. These bestätigt.",
    ),
    "ASML": dict(
        verdict="intact",
        summary=_D + "EUV-Aufträge aus TSMC und Samsung für High-NA-Systeme. Monopolstellung vollständig intakt.",
    ),
    "Bitcoin": dict(
        verdict="gemischt",
        summary=_D + "ETF-Zuflüsse stützen den Kurs, regulatorisches Umfeld uneinheitlich. Wertspeicher-These intakt, kurzfristig volatil.",
    ),
}

# fundamental: for all positions with ticker
DEMO_FUNDAMENTAL: dict[str, dict] = {
    "Apple": dict(
        verdict="fair",
        summary=_D + "KGV 29x leicht über 5J-Schnitt (26x). Services-Marge stützt Bewertung. (Fair Value: 210 €, Upside: +3%)",
    ),
    "Microsoft": dict(
        verdict="unterbewertet",
        summary=_D + "KGV 32x bei 15% EPS-Wachstum → PEG 2,1. Cloud-Margen expandieren, KI-Umsatz nicht eingepreist. (Fair Value: 490 €, Upside: +18%)",
    ),
    "Amazon": dict(
        verdict="fair",
        summary=_D + "EV/EBITDA 18x, AWS-Marge auf Rekordniveau. Retail-Restrukturierung läuft. (Fair Value: 195 €, Upside: +8%)",
    ),
    "Nestlé": dict(
        verdict="unterbewertet",
        summary=_D + "KGV 17x — 10J-Tief. Organisches Wachstum schwach, aber Dividendenrendite 3,8% attraktiv. (Fair Value: 95 CHF, Upside: +22%)",
    ),
    "ASML": dict(
        verdict="unterbewertet",
        summary=_D + "EV/EBITDA 30x für Monopolisten mit Orderbuch bis 2028. High-NA-Zyklus nicht vollständig eingepreist. (Fair Value: 950 €, Upside: +28%)",
    ),
    "Siemens": dict(
        verdict="fair",
        summary=_D + "KGV 18x, Infrastruktur- und Automatisierungssparte solide. Digitalisierungsgeschäft wächst. (Fair Value: 185 €, Upside: +5%)",
    ),
    "Toyota": dict(
        verdict="unterbewertet",
        summary=_D + "KGV 8x — deutlich unter Sektor (15x). Hybrid-Führerschaft unterschätzt, freier Cashflow stark. (Fair Value: 200 USD, Upside: +31%)",
    ),
    "TSMC": dict(
        verdict="unterbewertet",
        summary=_D + "KGV 22x bei 20%+ EPS-Wachstum. Geopolitischer Risikoabschlag übertrieben. (Fair Value: 195 USD, Upside: +25%)",
    ),
    "Novo Nordisk": dict(
        verdict="überbewertet",
        summary=_D + "KGV 38x bereits mit vollem GLP-1-Wachstum diskontiert. Konkurrenz (Eli Lilly, Roche) unterschätzt. (Fair Value: 68 USD, Upside: -19%)",
    ),
    "Alibaba": dict(
        verdict="unterbewertet",
        summary=_D + "KGV 10x, Nettocash 50 Mrd. USD. Regulierungsdruck abklingend, Cloud profitabel. (Fair Value: 105 USD, Upside: +35%)",
    ),
    "iShares Core MSCI World": dict(
        verdict="unbekannt",
        summary=_D + "ETF — keine Einzelaktien-Bewertungsmetriken anwendbar.",
    ),
    "Vanguard FTSE All-World": dict(
        verdict="unbekannt",
        summary=_D + "ETF — keine Einzelaktien-Bewertungsmetriken anwendbar.",
    ),
    "iShares Global Aggregate Bond": dict(
        verdict="unbekannt",
        summary=_D + "Rentenfonds — Equity-Bewertung nicht zutreffend.",
    ),
    "iShares Global REIT ETF": dict(
        verdict="fair",
        summary=_D + "P/FFO 15x, leicht unter historischem Schnitt. Zinsrückgang stützt REITs. (Fair Value: 27 USD, Upside: +10%)",
    ),
    "Gold (Unzen)": dict(
        verdict="unbekannt",
        summary=_D + "Edelmetall — DCF nicht anwendbar. Preis nahe 10J-Allzeithoch, real-Zinsen entscheidend.",
    ),
    "Gold (Gramm)": dict(
        verdict="unbekannt",
        summary=_D + "Edelmetall — DCF nicht anwendbar. Zentralbankankäufe stützen strukturell.",
    ),
    "Silber (Gramm)": dict(
        verdict="unterbewertet",
        summary=_D + "Gold/Silber-Ratio 85x — historischer Schnitt 65x. Industrienachfrage (Solar) wächst. (Fair Value: ~32 USD/oz, Upside: +15%)",
    ),
    "Bitcoin": dict(
        verdict="unbekannt",
        summary=_D + "Kryptowährung — klassische Equity-Bewertung nicht anwendbar. Stock-to-Flow-Modell: fair bis unterbewertet.",
    ),
}

# consensus_gap: only for positions with a story
DEMO_CONSENSUS_GAP: dict[str, dict] = {
    "Microsoft": dict(
        verdict="stabil",
        summary=_D + "Analystenkonsens 'Buy' mit Kursziel 450 USD — deckt sich mit These. KI-Monetarisierung beginnt, Lücke bleibt moderat.",
    ),
    "ASML": dict(
        verdict="wächst",
        summary=_D + "Konsens unterschätzt High-NA-Volumen ab 2026. Sell-Side rechnet mit 40 Systemen p.a., Managementguidance deutet auf 60+. Lücke wächst.",
    ),
    "Bitcoin": dict(
        verdict="stabil",
        summary=_D + "ETF-Zulassung hat Mainstream-Akzeptanz erhöht, Lücke zum Konsens kleiner geworden. These als Wertspeicher weiter akzeptiert.",
    ),
}

# capital_allocator: watchlist positions only (quality of capital allocation)
DEMO_CAPITAL_ALLOCATOR: dict[str, dict] = {
    "NVIDIA": dict(
        verdict="exzellent",
        summary=_D + "ROIC > 60%, F&E-Quote diszipliniert, Aktienrückkäufe wertschaffend. Kapitalallokation erstklassig.",
    ),
    "Eli Lilly": dict(
        verdict="solide",
        summary=_D + "Hohe Reinvestition in Pipeline, Dividende stabil. CapEx-Zyklus belastet kurzfristig FCF, langfristig sinnvoll.",
    ),
    "Berkshire Hathaway": dict(
        verdict="exzellent",
        summary=_D + "Kapitalallokation ist das Geschäftsmodell — opportunistische Rückkäufe, riesiges Cash-Polster, kein Dividenden-Dogma.",
    ),
    "Adobe": dict(
        verdict="fragwürdig",
        summary=_D + "Figma-Deal geplatzt, Rückkäufe auf Bewertungshöhepunkt. Kapitaldisziplin zuletzt fragwürdig.",
    ),
}

# devils_advocate: watchlist positions only (bear case)
DEMO_DEVILS_ADVOCATE: dict[str, dict] = {
    "NVIDIA": dict(
        verdict="angreifbar",
        summary=_D + "Bear-Case: Hyperscaler-CapEx zyklisch, Custom-Silicon (TPU, Trainium) erodiert Marge, China-Exportbann. Bewertung preist Perfektion ein.",
    ),
    "Eli Lilly": dict(
        verdict="robust",
        summary=_D + "Bear-Case schwach: GLP-1-Nachfrage strukturell, Kapazität ausgebaut. Hauptrisiko Bewertung, nicht Geschäft.",
    ),
    "Berkshire Hathaway": dict(
        verdict="robust",
        summary=_D + "Bear-Case: Key-Person-Risiko (Nachfolge), Cash-Drag. Operativ aber extrem diversifiziert und robust.",
    ),
    "Adobe": dict(
        verdict="fragil",
        summary=_D + "Bear-Case stark: GenAI (Midjourney, Sora) bedroht Kernprodukt, Preissetzungsmacht schwindet, Wachstum verlangsamt sich.",
    ),
}

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
    # --- Watchlist-only positions (in_portfolio=0, in_watchlist=1) ---
    # Needed so watchlist-only agents (CapitalAllocator, DevilsAdvocate, WatchlistChecker) have something to act on.
    dict(name="NVIDIA",            ticker="NVDA",  asset_class="Aktie", investment_type="Wertpapiere", unit="Stück", purchase_date="2024-01-15", in_portfolio=0, in_watchlist=1, empfehlung="Beobachten", story="KI-Infrastruktur-Monopol — CUDA-Ökosystem als Burggraben."),
    dict(name="Eli Lilly",         ticker="LLY",   asset_class="Aktie", investment_type="Wertpapiere", unit="Stück", purchase_date="2024-01-15", in_portfolio=0, in_watchlist=1, empfehlung="Beobachten"),
    dict(name="Berkshire Hathaway",ticker="BRK-B", asset_class="Aktie", investment_type="Wertpapiere", unit="Stück", purchase_date="2024-01-15", in_portfolio=0, in_watchlist=1),
    dict(name="Adobe",             ticker="ADBE",  asset_class="Aktie", investment_type="Wertpapiere", unit="Stück", purchase_date="2024-01-15", in_portfolio=0, in_watchlist=1, empfehlung="Beobachten"),
    # Fixed deposit (no ticker, no yfinance)
    dict(name="Festgeld DKB 3J", ticker=None, asset_class="Festgeld", investment_type="Geld", unit="Stück",
         purchase_date="2023-03-01", quantity=10.0, purchase_price=10000.0,
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
    "NVDA":    480.0,
    "LLY":     580.0,
    "BRK-B":   360.0,
    "ADBE":    560.0,
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
        # Stück (stocks, ETFs, crypto) — whole numbers; fractional if price too high
        qty = TARGET_EUR / price_eur
        rounded = round(qty)
        if rounded == 0:
            return round(qty, 4)  # e.g. Bitcoin: 0.314 BTC
        return float(rounded)


def _purchase_price_per_unit(price_eur: float, unit: str) -> float:
    """Return price per unit in EUR."""
    if unit == "g":
        return round(price_eur / TROY_OZ_TO_GRAM, 4)
    return round(price_eur, 4)


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

    init_db(conn)
    migrate_db(conn)

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
                added_date, in_portfolio, in_watchlist,
                empfehlung, story
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                pos.get("in_portfolio", 1),   # default: portfolio position
                pos.get("in_watchlist", 0),    # default: not on watchlist
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
            (ticker, price_eur, currency, price_original, exchange_rate, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        print(f"  {ticker}: €{price_eur:.4f} ({currency} {price_original:.4f})")

    # --- fetch historical prices (1y) ---
    print("\nFetching historical prices (1y) ...")
    from agents.market_data_fetcher import MarketDataFetcher
    from core.storage.market_data import MarketDataRepository

    import math

    market_repo = MarketDataRepository(conn)
    fetcher = MarketDataFetcher()
    for ticker in seen_tickers:
        history = fetcher.fetch_historical(ticker, period="1y")
        n_ok = 0
        for h in history:
            # A missing FX rate can yield a NaN close, which SQLite stores as NULL
            # (NOT NULL constraint violation). Skip those points.
            if h.close_eur is None or math.isnan(h.close_eur):
                continue
            market_repo.upsert_historical(h)
            n_ok += 1
        print(f"  {ticker}: {n_ok} Datenpunkte")

    # --- seed demo analyses (storychecker, fundamental, consensus_gap) ---
    print("\nSeeding demo analyses ...")
    _demo_agents = [
        ("storychecker",     DEMO_STORYCHECKER),
        ("fundamental_analyzer", DEMO_FUNDAMENTAL),
        ("consensus_gap",    DEMO_CONSENSUS_GAP),
        ("capital_allocator", DEMO_CAPITAL_ALLOCATOR),
        ("devils_advocate",   DEMO_DEVILS_ADVOCATE),
    ]
    for agent_name, demo_map in _demo_agents:
        for pos_name, data in demo_map.items():
            row = conn.execute(
                "SELECT id FROM positions WHERE name = ? LIMIT 1", (pos_name,)
            ).fetchone()
            if row is None:
                print(f"  [{agent_name}] Position '{pos_name}' not found — skipping")
                continue
            conn.execute(
                """
                INSERT INTO position_analyses
                    (position_id, agent, skill_name, verdict, summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (row[0], agent_name, "Demodaten", data["verdict"], data["summary"],
                 datetime.now(timezone.utc).isoformat()),
            )
            print(f"  [{agent_name}] {pos_name}: {data['verdict']}")
        conn.commit()

    # --- seed everything else (portfolio story, news, sector rotation,
    #     structural change, dividends, wealth snapshots, cowork) ---
    _seed_extras(conn)

    if own_conn:
        conn.close()
        print(f"\nDemo database seeded at {os.path.abspath(db_path)}")
        print(f"Total positions: {len(inserted)}")

    return inserted


# ---------------------------------------------------------------------------
# Extra fixtures — every other persisted analysis surface
# All marked [Demodaten] / skill_name "Demodaten", written as plaintext (demo).
# ---------------------------------------------------------------------------

# Forward annual dividend per share (EUR) + yield (decimal) for the payers.
DEMO_DIVIDENDS: dict[str, tuple[float, float]] = {
    "AAPL":    (1.00, 0.005),
    "MSFT":    (2.80, 0.008),
    "NESN.SW": (3.00, 0.030),
    "SIE.DE":  (5.20, 0.026),
    "TM":      (2.50, 0.018),
    "TSM":     (2.20, 0.015),
    "VWRL.AS": (1.40, 0.018),
    "AGGG.L":  (0.12, 0.030),
    "REET":    (0.60, 0.025),
}

# Asset classes whose value fluctuates with the market (used for the snapshot
# time-series). Immobilie / Festgeld are held flat across months.
_MARKET_CLASSES = {"Aktie", "Aktienfonds", "Rentenfonds", "Immobilienfonds",
                   "Edelmetall", "Kryptowährung"}


def _months_back(d: date, n: int) -> date:
    """Return the 1st of the month n months before d's month."""
    month0 = d.year * 12 + (d.month - 1) - n
    return date(month0 // 12, month0 % 12 + 1, 1)


def _portfolio_value_by_class(conn: sqlite3.Connection) -> dict[str, float]:
    """Current EUR value of all in_portfolio positions, grouped by asset_class.

    Uses current_prices (price_eur is per native unit; per troy oz for metals).
    Falls back to cost basis (quantity × purchase_price) when no price is known.
    """
    import json as _json

    prices = {
        r["symbol"].upper(): r["price_eur"]
        for r in conn.execute("SELECT symbol, price_eur FROM current_prices").fetchall()
    }
    breakdown: dict[str, float] = {}
    rows = conn.execute(
        "SELECT name, ticker, quantity, unit, purchase_price, asset_class, extra_data "
        "FROM positions WHERE in_portfolio = 1"
    ).fetchall()
    for r in rows:
        qty = float(r["quantity"] or 0)
        cost = float(r["purchase_price"] or 0)
        ticker = (r["ticker"] or "").upper()
        unit = r["unit"]
        value = qty * cost  # default: cost basis

        if ticker and ticker in prices:
            px = prices[ticker]
            if unit == "g":
                value = qty * (px / TROY_OZ_TO_GRAM)
            else:  # "Stück" / "Troy Oz"
                value = qty * px
        elif not ticker and r["extra_data"]:
            try:
                est = _json.loads(r["extra_data"]).get("estimated_value")
                if est:
                    value = float(est)
            except (ValueError, TypeError):
                pass

        breakdown[r["asset_class"]] = breakdown.get(r["asset_class"], 0.0) + value
    return breakdown


def _seed_wealth_snapshots(conn: sqlite3.Connection) -> None:
    """Generate ~13 monthly wealth snapshots (deterministic gentle uptrend)."""
    import math
    from core.storage.wealth_snapshots import WealthSnapshotRepository

    base = _portfolio_value_by_class(conn)
    if not base:
        print("  [wealth_snapshots] no portfolio value — skipping")
        return

    repo = WealthSnapshotRepository(conn)
    today = date.today()
    n = 0
    # i = 0 → today (full value); i = 1..12 → 1st of each prior month, scaled down
    for i in range(12, -1, -1):
        snap_date = today if i == 0 else _months_back(today, i)
        # Gentle uptrend: market classes ~1.8 %/month lower the further back,
        # plus a small deterministic wave; non-market classes held flat.
        factor = (1 - 0.018 * i) * (1 + 0.012 * math.sin(i))
        bd: dict[str, float] = {}
        for cls, val in base.items():
            bd[cls] = round(val * (factor if cls in _MARKET_CLASSES else 1.0), 2)
        total = round(sum(bd.values()), 2)
        try:
            repo.create(snap_date.isoformat(), total, bd, note=_D.strip())
            n += 1
        except ValueError:
            pass  # duplicate date — skip
    print(f"  [wealth_snapshots] {n} monthly snapshots")


def _seed_dividends(conn: sqlite3.Connection) -> None:
    from core.storage.market_data import MarketDataRepository
    from core.storage.models import DividendRecord

    repo = MarketDataRepository(conn)
    now = datetime.now(timezone.utc)
    for symbol, (rate_eur, yield_pct) in DEMO_DIVIDENDS.items():
        repo.upsert_dividend(DividendRecord(
            symbol=symbol, rate_eur=rate_eur, yield_pct=yield_pct,
            currency="EUR", fetched_at=now,
        ))
    print(f"  [dividends] {len(DEMO_DIVIDENDS)} symbols")


def _seed_portfolio_story(conn: sqlite3.Connection) -> None:
    """Seed the narrative + one analysis + per-position fit roles (plaintext, demo)."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO portfolio_story
               (story, target_year, liquidity_need, priority, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            _D + "Langfristiger Vermögensaufbau mit Fokus auf Qualitätsunternehmen, "
                 "ergänzt um breite ETFs, Edelmetalle als Absicherung und eine kleine "
                 "Krypto-Beimischung. Ziel: finanzielle Unabhängigkeit bis 2040.",
            2040, "2030: Modernisierung Immobilie ~80k", "Gemischt", now, now,
        ),
    )
    conn.execute(
        """INSERT INTO portfolio_story_analyses
               (verdict, summary, perf_verdict, perf_summary,
                stability_verdict, stability_summary, full_text, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "intact", _D + "Portfolio deckt die Wachstums- und Sicherheitsziele konsistent ab.",
            "on_track", _D + "Breite Diversifikation, Performance im Plan.",
            "stabil", _D + "Edelmetall- und Anleihen-Anteil federt Drawdowns gut ab.",
            _D + "## Portfolio Story-Check\n\nDie Allokation passt zur formulierten Strategie: "
                 "Qualitätsaktien als Wachstumsmotor, ETFs als Basis, Gold/Anleihen als Stabilitätsanker.\n\n"
                 "## Positions-Analyse\n\nKeine Fehlplatzierungen erkennbar.\n\n"
                 "## Stabilität\n\nDefensiver Anteil ausreichend für den Anlagehorizont bis 2040.",
            now,
        ),
    )
    # Per-position fit roles for a handful of core holdings
    fits = {
        "Microsoft": ("Wachstumsmotor", "Cloud/KI treibt langfristiges Gewinnwachstum."),
        "ASML": ("Wachstumsmotor", "Strukturelles Halbleiter-Wachstum, Monopolstellung."),
        "Nestlé": ("Stabilitätsanker", "Defensiver Konsumwert mit verlässlicher Dividende."),
        "iShares Global Aggregate Bond": ("Stabilitätsanker", "Anleihen dämpfen die Portfolio-Volatilität."),
        "Gold (Unzen)": ("Diversifikationselement", "Unkorrelierte Absicherung gegen Marktstress."),
        "Bitcoin": ("Diversifikationselement", "Asymmetrische Beimischung, kleine Positionsgröße."),
    }
    for name, (role, summary) in fits.items():
        row = conn.execute("SELECT id FROM positions WHERE name = ? LIMIT 1", (name,)).fetchone()
        if row is None:
            continue
        conn.execute(
            """INSERT INTO portfolio_story_position_fits
                   (position_id, fit_role, fit_summary, created_at)
               VALUES (?, ?, ?, ?)""",
            (row[0], role, _D + summary, now),
        )
    conn.commit()
    print("  [portfolio_story] narrative + analysis + position fits")


def _seed_news(conn: sqlite3.Connection) -> None:
    from core.storage.news import NewsRepository

    repo = NewsRepository(conn)
    repo.save_run(
        "Demodaten", ["AAPL", "MSFT", "NVDA"],
        _D + "## Tech-News\n\n"
             "- **Microsoft**: Copilot-Umsätze übertreffen Analystenerwartungen; Azure +29 % YoY.\n"
             "- **Apple**: Neue Service-Rekorde, iPhone-Absatz in China stabilisiert sich.\n"
             "- **NVIDIA**: Nächste GPU-Generation angekündigt, Lieferzeiten weiter lang.",
    )
    repo.save_run(
        "Demodaten", ["NESN.SW", "NVO"],
        _D + "## Health & Consumer\n\n"
             "- **Nestlé**: Organisches Wachstum schwach, Preiserhöhungen greifen verzögert.\n"
             "- **Novo Nordisk**: GLP-1-Kapazität ausgebaut, Konkurrenzdruck durch Eli Lilly steigt.",
    )
    print("  [news] 2 runs")


def _seed_sector_rotation(conn: sqlite3.Connection) -> None:
    from core.storage.sector_rotation import SectorRotationRepository

    repo = SectorRotationRepository(conn)
    run = repo.save_run(
        "Demodaten",
        _D + "## Sector Rotation Scan\n\nKapital fließt aktuell in Technologie und Healthcare, "
             "raus aus defensiven Versorgern. Das Portfolio ist in Tech gut positioniert, "
             "aber in Industrie leicht unterexponiert.",
    )
    verdicts = [
        ("Technologie",          "aligned",       "inflow",  "Starke Zuflüsse — Portfolio gut positioniert."),
        ("Healthcare",           "lagging",        "inflow",  "Sektor zieht an, Portfolio-Gewicht zu gering."),
        ("Basiskonsum",          "overexposed",    "outflow", "Defensive Werte verlieren Momentum."),
        ("Industrie",            "rotation_risk",  "neutral", "Rotationskandidat — Flows drehen uneinheitlich."),
    ]
    for sector, verdict, momentum, summary in verdicts:
        repo.save_verdict(run.id, sector, verdict, momentum, _D + summary)
    print("  [sector_rotation] 1 run + 4 verdicts")


def _seed_structural_scan(conn: sqlite3.Connection) -> None:
    now = datetime.now().isoformat()
    cur = conn.execute(
        "INSERT INTO structural_scan_runs (skill_name, user_focus, result, created_at) "
        "VALUES (?, ?, ?, ?)",
        (
            "Demodaten", "KI-Disruption im Software-Sektor",
            _D + "## Strukturelle Veränderungen\n\nGenerative KI verändert die Software-Wertschöpfung: "
                 "SaaS-Anbieter ohne eigenes Modell geraten unter Margendruck, während "
                 "Infrastruktur-Anbieter (Cloud, GPU) profitieren. Relevanz fürs Portfolio: "
                 "Microsoft (positiv), Adobe (Watchlist, gefährdet).",
            now,
        ),
    )
    conn.execute(
        "INSERT INTO structural_scan_messages (run_id, role, content, created_at) "
        "VALUES (?, ?, ?, ?)",
        (cur.lastrowid, "assistant",
         _D + "Zusammenfassung: KI ist Rückenwind für Plattform-/Infrastruktur-Player, "
              "Gegenwind für reine Applikations-SaaS.", now),
    )
    conn.commit()
    print("  [structural_scan] 1 run + 1 message")


def _seed_cowork(conn: sqlite3.Connection) -> None:
    from core.storage.research_queue import ResearchQueueRepository

    repo = ResearchQueueRepository(conn)
    # One open request
    repo.create_request(
        _D + "Wie robust ist die Wettbewerbsposition von ASML gegenüber Canon/Nikon?",
        request_type="research_question", ticker="ASML", source="manual",
    )
    # One answered request (linked answer)
    req = repo.create_request(
        _D + "Bear-Case für NVIDIA recherchieren.",
        request_type="watchlist_candidate", ticker="NVDA", source="manual",
    )
    repo.submit_answer(
        _D + "## NVIDIA — Bear-Case\n\nHauptrisiken: zyklische Hyperscaler-CapEx, "
             "Custom-Silicon der Cloud-Anbieter, China-Exportbeschränkungen. "
             "Bewertung preist anhaltend hohe Wachstumsraten ein.",
        request_id=req.id, ticker="NVDA",
    )
    repo.complete_request(req.id)
    print("  [cowork] 2 requests (1 open, 1 answered)")


def _seed_extras(conn: sqlite3.Connection) -> None:
    """Seed all remaining demo surfaces. Each helper is independent/idempotent-safe."""
    print("\nSeeding extra demo data ...")
    _seed_dividends(conn)
    _seed_wealth_snapshots(conn)
    _seed_portfolio_story(conn)
    _seed_news(conn)
    _seed_sector_rotation(conn)
    _seed_structural_scan(conn)
    _seed_cowork(conn)


if __name__ == "__main__":
    import pandas as pd  # noqa: F401 — ensure available before seed()
    db_path = os.getenv("DEMO_DB_PATH", "data/demo.db")
    # Safety guard: never seed over the real production DB.
    if os.path.basename(os.path.abspath(db_path)) == "portfolio.db":
        raise SystemExit("Refusing to seed: target resolves to portfolio.db (the real DB).")
    print(f"Seeding demo database: {db_path}\n")
    seed(db_path)
