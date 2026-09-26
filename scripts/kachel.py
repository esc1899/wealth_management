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
Bewertung (`MarketDataAgent.get_portfolio_valuation`), gleiche Rechnung (`core/tagesbild.py`,
seit 22.09.2026 auch die Kopfzeile des Dashboards), keine zweite Zahl.

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

from core.tagesbild import groesste_bewegung, prozent, tagesbild  # noqa: E402


def dienste_www() -> Path:
    return Path(os.environ.get("DIENSTE_HOME") or Path.home() / ".dienste") / "www"


def kachel(valuations: Iterable, stand: Optional[datetime] = None,
           meldungen: Optional[list] = None) -> dict:
    """Das Kachel-JSON aus den Bewertungen des Portfolios (keine Watchlist).
    Ohne Tageskurse gibt es keine Prozentzahl — dann steht das da, statt einer Null."""
    bild = tagesbild(valuations)

    zeilen: list = []
    if bild.prozent is not None:
        zustand = "schlecht" if bild.prozent < 0 else "gut" if bild.prozent > 0 else ""
        zeilen.append({"text": f"{prozent(bild.prozent)} heute", "zustand": zustand})
    else:
        zeilen.append("keine Tageskurse")
    zeilen.append("1 Position" if bild.positionen == 1 else f"{bild.positionen} Positionen")
    if bild.prozent is not None and bild.ohne_tageskurs:
        zeilen.append(f"{bild.ohne_tageskurs} ohne Tageskurs")

    stand = stand or datetime.now(timezone.utc)
    if stand.tzinfo is None:
        stand = stand.replace(tzinfo=timezone.utc)   # fetched_at ist naives UTC
    daten = {"stand": stand.astimezone().isoformat(timespec="seconds"),
             "zeilen": zeilen, "satz": groesste_bewegung(bild)}
    if meldungen:
        daten["meldungen"] = meldungen
    return daten


def story(conn, positions_repo) -> Optional[dict]:
    """Die Meldung des Story-Checks (core/story_meldung.py): dieselben Positionen wie der
    eingeplante Lauf — im Depot, mit Story, nicht von der Analyse ausgenommen."""
    from core.storage.analyses import PositionAnalysesRepository
    from core.storage.app_config import AppConfigRepository
    from core.story_meldung import VERWORFEN_KEY, story_meldung

    ids = [p.id for p in positions_repo.get_portfolio()
           if p.id and p.story and not p.analysis_excluded]
    latest = PositionAnalysesRepository(conn).get_latest_bulk(ids, "storychecker")
    urteile = {i: (a.verdict or "unknown", a.created_at) for i, a in latest.items()}
    return story_meldung(urteile, ids, AppConfigRepository(conn).get(VERWORFEN_KEY))


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
    positions_repo = PositionsRepository(conn, enc)
    agent = MarketDataAgent(
        positions_repo=positions_repo,
        market_repo=market,
        fetcher=MarketDataFetcher(rate_limiter=RateLimiter(calls_per_second=config.RATE_LIMIT_RPS)),
        db_path=config.DB_PATH,
        encryption_key=config.ENCRYPTION_KEY,
    )
    return agent, market, conn, positions_repo


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

    agent, market, conn, positions_repo = _agent()
    if args.fetch:
        ergebnis = agent.fetch_all_now(fetch_history=False, include_watchlist=False)
        print(f"Kurse: {ergebnis.fetched} geholt"
              + (f", {len(ergebnis.failed)} fehlgeschlagen ({', '.join(ergebnis.failed[:5])})" if ergebnis.failed else ""))
    try:
        meldung = story(conn, positions_repo)
    except Exception as exc:   # die Meldung ist Zutat — die Kachel steht auch ohne sie
        print(f"Story-Meldung nicht bestimmt: {exc}", file=sys.stderr)
        meldung = None
    daten = kachel(agent.get_portfolio_valuation(include_watchlist=False),
                   stand=market.get_latest_fetch_time(), meldungen=[meldung] if meldung else None)
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
