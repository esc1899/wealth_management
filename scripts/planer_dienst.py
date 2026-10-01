#!/usr/bin/env python
"""Der Planer: die eingeplanten Läufe der App, als eigener Prozess.

    python scripts/planer_dienst.py

Bis zum 01.10.2026 liefen beide Zeitpläne der App — der tägliche Kursabruf um 18 Uhr
(`MarketDataAgent`) und die Agenten-Jobs der Seite "Scheduler" (`AgentSchedulerService`)
— im Streamlit-Prozess. Streamlit führt `app.py` aber erst aus, wenn ein Browser die Seite
öffnet: Der Dienst lief seit dem Login, die Zeitpläne erst ab dem ersten Besuch. Ein Tag
ohne Besuch hatte keinen Lauf, die Monatsjobs vom 1. starteten abends beim Öffnen.

Hier laufen beide ab dem Login (ops-core startet den Prozess als Dienst, `jobs.toml`,
services.planer, mit KeepAlive). Beim Start wird nachgeholt, was verpasst ist — der
Kursabruf, wenn 18 Uhr heute vorbei ist und kein Abruf danach kam, die Agenten-Jobs nach
ihren eigenen Regeln (`_catchup_missed_jobs`). Änderungen auf der Seite "Scheduler" holt
der Planer jede Minute selbst aus der Datenbank (`sync_jobs`); "Jetzt ausführen" läuft
weiter in der App, auf Knopfdruck.

Die App startet keinen der beiden Zeitpläne mehr. Liefen beide Prozesse, liefe jeder Job
doppelt — und der Start des einen würde die laufenden Läufe des anderen als verwaist
schließen.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger("planer")

PRUEFEN_ALLE_SEKUNDEN = 60


def _marktdaten_agent():
    """Der Marktdaten-Agent ohne Streamlit — wie `scripts/kachel.py` ihn baut."""
    from agents.market_data_agent import MarketDataAgent
    from agents.market_data_fetcher import MarketDataFetcher, RateLimiter
    from config import config
    from core.storage.app_config import AppConfigRepository
    from core.storage.base import build_encryption_service, get_connection, init_db, migrate_db
    from core.storage.market_data import MarketDataRepository
    from core.storage.positions import PositionsRepository

    conn = get_connection(config.DB_PATH)
    init_db(conn)
    migrate_db(conn)
    salt_path = os.path.join(os.path.dirname(os.path.abspath(config.DB_PATH)), "salt.bin")
    enc = build_encryption_service(config.ENCRYPTION_KEY, salt_path)
    return MarketDataAgent(
        positions_repo=PositionsRepository(conn, enc),
        market_repo=MarketDataRepository(conn),
        fetcher=MarketDataFetcher(rate_limiter=RateLimiter(calls_per_second=config.RATE_LIMIT_RPS)),
        db_path=config.DB_PATH,
        encryption_key=config.ENCRYPTION_KEY,
        app_config_repo=AppConfigRepository(conn),
    )


def _agenten_planer():
    from config import config
    from core.constants import CLAUDE_HAIKU
    from core.scheduler import AgentSchedulerService

    # Dieselben Argumente wie get_agent_scheduler() in state_agents.py
    return AgentSchedulerService(
        db_path=config.DB_PATH,
        encryption_key=config.ENCRYPTION_KEY,
        anthropic_api_key=config.LLM_API_KEY,
        default_claude_model=CLAUDE_HAIKU,
        llm_base_url=config.LLM_BASE_URL,
        openai_api_key=config.OPENAI_API_KEY,
        openai_base_url=config.OPENAI_BASE_URL,
    )


def laufen(agenten, markt, fetch_hour: int, ende: threading.Event,
           pruefen_alle: float = PRUEFEN_ALLE_SEKUNDEN) -> None:
    """Beide Zeitpläne starten, Verpasstes nachholen, bis `ende` gesetzt ist jede Minute
    die Jobs der Seite abgleichen. Fehler beim Abgleich beenden den Planer nicht."""
    kurse = markt.setup_scheduler(fetch_hour=fetch_hour)
    kurse.start()
    markt.catchup_fetch_if_missed(fetch_hour=fetch_hour)
    agenten.start()
    logger.info("Planer läuft: Kursabruf täglich %02d:00, Agenten-Jobs aus der Datenbank", fetch_hour)
    try:
        while not ende.wait(pruefen_alle):
            try:
                agenten.sync_jobs()
            except Exception:
                logger.exception("Abgleich der Jobs fehlgeschlagen")
    finally:
        kurse.shutdown(wait=False)
        agenten.shutdown()
        logger.info("Planer beendet")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    from config import config

    ende = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: ende.set())
    signal.signal(signal.SIGINT, lambda *_: ende.set())
    laufen(_agenten_planer(), _marktdaten_agent(), config.MARKET_DATA_FETCH_HOUR, ende)
    return 0


if __name__ == "__main__":
    sys.exit(main())
