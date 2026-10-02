#!/usr/bin/env python
"""Die eingeplanten Läufe der App, als Jobs von ops-core.

    python scripts/job.py agenten   # die fälligen Jobs der Seite "Scheduler"
    python scripts/job.py kurse     # der Tagesabruf: Kurse mit Historie, danach die Snapshots
    python scripts/job.py kosten    # echte Kosten der OpenRouter-Aufrufe nachtragen

ops-core ruft sie über `ops run wealth_management <job>` auf, Zeitplan in
`~/.ops-core/jobs.toml`: `agenten` stündlich und beim Login, `kurse` beim Login und
um 18:05, `kosten` stündlich. Was gelaufen ist, steht damit im Run-Log, in
`ops status` und auf der Jobs-Kachel der Startseite — wie bei jedem anderen Job im Haus.

Bis zum 01.10.2026 liefen alle drei in einem APScheduler im Streamlit-Prozess, und
Streamlit führt `app.py` erst aus, wenn ein Browser die Seite öffnet: Ein Tag ohne
Besuch war ein Tag ohne Läufe, und niemand sah es. Danach einen Tag lang als eigener
Dienst (`planer_dienst.py`) — der lief zuverlässig, aber am Run-Log vorbei.

Fällig entscheidet das Skript, nicht der Zeitplan (Hausregel: "die Fälligkeit ins Skript
des Projekts"). Ein Job der Seite ist fällig, wenn sein letzter Termin vorbei ist und er
seitdem nicht lief (`core.scheduler.ist_faellig`); Takt und Uhrzeit stellt man weiter auf
der Seite ein. Ein Lauf ohne Fälliges endet mit 0 und sagt das — doppelt laufen kostet
nichts, ein ausgefallener Lauf wird vom nächsten nachgeholt.

Exit 1, wenn ein Job fehlschlug; die anderen fälligen laufen trotzdem. Nach drei
Fehlversuchen seit seinem letzten Termin wartet ein Job auf den nächsten Termin —
der Lauf bleibt rot, bis er wieder gelingt (Jetzt ausführen auf der Seite geht immer).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def _agenten_dienst():
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


def _marktdaten_agent():
    """Der Marktdaten-Agent ohne Streamlit — wie `scripts/kachel.py` ihn baut, dazu
    app_config für den Benchmark und den Wasserstand des Tagesabrufs."""
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


def agenten(dienst, batch_api: bool) -> int:
    gelaufen, fehlgeschlagen, gebremst = dienst.laufen_lassen()
    if batch_api:
        for zeile in dienst.batches_abholen():
            print(zeile)
        # Fuer die ops-core-Kachel: worauf noch gewartet wird (auch "nichts").
        from core import ops_events
        stand = dienst.wartet()
        ops_events.report_waiting(**stand)
        if stand["anzahl"]:
            print(f"Wartet auf {', '.join(stand['was'])} seit {stand['seit'][11:16]}.")
    if gebremst:
        # Rot, obwohl nichts lief: Sonst wäre die Kachel nach dem dritten Fehlversuch
        # wieder grün, und der Job stünde still, ohne dass es jemand sieht.
        from core.scheduler import FEHLVERSUCHE_JE_TERMIN
        print(f"Gebremst nach {FEHLVERSUCHE_JE_TERMIN} Fehlversuchen, warten auf den nächsten Termin: "
              f"{', '.join(gebremst)}")
    if fehlgeschlagen:
        print(f"{len(fehlgeschlagen)} von {gelaufen} fehlgeschlagen: {', '.join(fehlgeschlagen)}")
    elif gelaufen:
        print(f"{gelaufen} Job{'s' if gelaufen != 1 else ''} gelaufen.")
    elif not gebremst:
        print("Nichts fällig.")
    return 1 if fehlgeschlagen or gebremst else 0


def kurse(markt, fetch_hour: int) -> int:
    if markt.tagesabruf_wenn_faellig(fetch_hour=fetch_hour):
        print("Tagesabruf gelaufen: Kurse mit Historie, Snapshots.")
    else:
        print(f"Nicht fällig: {fetch_hour:02d}:00 ist heute noch nicht erreicht, "
              f"oder der Tagesabruf lief seitdem schon.")
    return 0


def kosten(dienst) -> int:
    nachgetragen, offen = dienst.kosten_abgleichen()
    print(f"OpenRouter: {nachgetragen} von {offen} offenen Aufrufen nachgetragen."
          if offen else "OpenRouter: nichts offen.")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Eingeplante Läufe der App (ops-core-Jobs)")
    p.add_argument("job", choices=["agenten", "kurse", "kosten"])
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )
    from config import config

    if args.job == "agenten":
        # Immer abholen: Auch nach dem Ausschalten im Maschinenraum darf kein
        # eingereichter Batch liegen bleiben. Ohne offene Batches kein Netz.
        return agenten(_agenten_dienst(), True)
    if args.job == "kurse":
        return kurse(_marktdaten_agent(), config.MARKET_DATA_FETCH_HOUR)
    return kosten(_agenten_dienst())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
