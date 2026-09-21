#!/usr/bin/env python
"""Die Kachel auf der Startseite des Mac mini — als Datei, weil Streamlit keine API hat.

    python scripts/kachel.py                # nach ~/.dienste/www/kacheln/wealth.json
    python scripts/kachel.py --fetch        # vorher die Kurse holen (so läuft der Job)
    python scripts/kachel.py --stdout       # nur zeigen, nichts schreiben

Die gemeinsame Startseite (heimnetzwerk-Repo, `dienste`) zeigt je Dienst eine Kachel und
holt deren Inhalt als JSON. Diese hier gibt es nur auf dem Mac mini selbst: Caddy liefert
`/kacheln/wealth.json` und `/wealth/` nur an 127.0.0.1 aus (dort `zugang = "lokal"`), von
jedem anderen Gerät aus antwortet der Pfad mit 404. Trotzdem steht kein Betrag in Euro auf
der Kachel — nur die Tagesveränderung des Depots in Prozent, die Zahl der Positionen und
die größte Bewegung des Tages. Die Zahlen sind dieselben wie auf der Analyse-Seite: gleiche
Bewertung (`MarketDataAgent.get_portfolio_valuation`), gleiche Summenformel
(`aggregate_day_pnl`), keine zweite Rechnung.

ops-core lässt es stündlich laufen (`ops run wealth_management kachel`, Zeitplan in
`~/.ops-core/jobs.toml`), mit `--fetch`: erst die aktuellen Kurse (ohne Historie — die holt
die App selbst täglich um 18 Uhr), dann die Datei. Fehlt `~/.dienste/www/` (Startseite nicht
installiert), passiert nichts und der Lauf ist gut: Die App hängt nicht an der Startseite.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from core.symbol_aggregation import aggregate_day_pnl  # noqa: E402

MINUS = "−"   # das typografische Minus, wie auf der Startseite


def dienste_www() -> Path:
    return Path(os.environ.get("DIENSTE_HOME") or Path.home() / ".dienste") / "www"


def prozent(wert: float) -> str:
    """+0,42 % / −1,08 % / ±0,00 % — deutsch, mit Vorzeichen."""
    if round(wert, 2) == 0:
        return "±0,00 %"
    text = f"{wert:+.2f}".replace(".", ",").replace("-", MINUS)
    return f"{text} %"


def kachel(valuations: Iterable, stand: Optional[datetime] = None) -> dict:
    """Das Kachel-JSON aus den Bewertungen des Portfolios (keine Watchlist).
    Ohne Tageskurse gibt es keine Prozentzahl — dann steht das da, statt einer Null."""
    depot = [v for v in valuations if getattr(v, "in_portfolio", True)]
    mit_tag = [v for v in depot if v.day_pnl_eur is not None and v.current_value_eur is not None]
    vortag = sum(v.current_value_eur - v.day_pnl_eur for v in mit_tag)
    tag = sum(v.day_pnl_eur for v in mit_tag)

    zeilen: list = []
    if mit_tag and vortag > 0:
        pct = tag / vortag * 100
        zustand = "schlecht" if pct < 0 else "gut" if pct > 0 else ""
        zeilen.append({"text": f"{prozent(pct)} heute", "zustand": zustand})
    else:
        zeilen.append("keine Tageskurse")
    zeilen.append("1 Position" if len(depot) == 1 else f"{len(depot)} Positionen")
    ohne = len(depot) - len(mit_tag)
    if mit_tag and ohne:
        zeilen.append(f"{ohne} ohne Tageskurs")

    satz = None
    bewegungen = [b for b in aggregate_day_pnl(mit_tag) if b.day_pnl_pct is not None]
    if bewegungen:
        groesste = max(bewegungen, key=lambda b: abs(b.day_pnl_pct))
        name = next((v.name for v in mit_tag if v.symbol == groesste.symbol), groesste.symbol)
        satz = f"Größte Bewegung: {name} {prozent(groesste.day_pnl_pct)}"

    stand = stand or datetime.now(timezone.utc)
    if stand.tzinfo is None:
        stand = stand.replace(tzinfo=timezone.utc)   # fetched_at ist naives UTC
    return {"stand": stand.astimezone().isoformat(timespec="seconds"), "zeilen": zeilen, "satz": satz}


def _agent():
    """Der Marktdaten-Agent ohne Streamlit — wie `_scheduled_fetch` ihn baut."""
    from agents.market_data_agent import MarketDataAgent
    from agents.market_data_fetcher import MarketDataFetcher, RateLimiter
    from config import config
    from core.storage.base import build_encryption_service, get_connection, init_db, migrate_db
    from core.storage.market_data import MarketDataRepository
    from core.storage.positions import PositionsRepository

    conn = get_connection(config.DB_PATH)
    init_db(conn)
    migrate_db(conn)
    salt_path = os.path.join(os.path.dirname(os.path.abspath(config.DB_PATH)), "salt.bin")
    enc = build_encryption_service(config.ENCRYPTION_KEY, salt_path)
    market = MarketDataRepository(conn)
    agent = MarketDataAgent(
        positions_repo=PositionsRepository(conn, enc),
        market_repo=market,
        fetcher=MarketDataFetcher(rate_limiter=RateLimiter(calls_per_second=config.RATE_LIMIT_RPS)),
        db_path=config.DB_PATH,
        encryption_key=config.ENCRYPTION_KEY,
    )
    return agent, market


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Kachel-JSON für die Startseite des Mac mini schreiben")
    p.add_argument("--fetch", action="store_true", help="vorher die aktuellen Kurse holen (ohne Historie)")
    p.add_argument("--out", type=Path, default=None,
                   help="Zieldatei (Default: ~/.dienste/www/kacheln/wealth.json)")
    p.add_argument("--stdout", action="store_true", help="nur ausgeben, nichts schreiben")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    ziel = args.out or dienste_www() / "kacheln" / "wealth.json"
    if not args.stdout and args.out is None and not dienste_www().is_dir():
        print(f"Startseite nicht installiert ({dienste_www()} fehlt) — nichts zu tun.")
        return 0

    agent, market = _agent()
    if args.fetch:
        ergebnis = agent.fetch_all_now(fetch_history=False, include_watchlist=False)
        print(f"Kurse: {ergebnis.fetched} geholt"
              + (f", {len(ergebnis.failed)} fehlgeschlagen ({', '.join(ergebnis.failed[:5])})" if ergebnis.failed else ""))
    daten = kachel(agent.get_portfolio_valuation(include_watchlist=False), stand=market.get_latest_fetch_time())
    text = json.dumps(daten, ensure_ascii=False, indent=1)
    if args.stdout:
        print(text)
        return 0
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(text + "\n", encoding="utf-8")
    erste = daten["zeilen"][0]
    print(f"geschrieben: {ziel} — {erste['text'] if isinstance(erste, dict) else erste}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
