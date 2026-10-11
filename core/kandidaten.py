"""Kandidaten der Suche: was ein Lauf vorschlaegt, bis Erik entscheidet (BACKLOG.md, "Suche").

Ein Lauf legt seine Vorschlaege in die stehende Liste "Offen"; nichts verfaellt, nichts wird
still zum Nein. Findet ein spaeterer Lauf denselben Titel, waechst seine Herkunft ("2x
gefunden"). Was schon im Depot oder auf der Watchlist steht, wird kein Kandidat.

Die Strategien bekommen die bekannten Ticker mit, damit sie sie nicht wieder vorschlagen --
aber **nie die des Depots**: Die Strategien rechnen in der Cloud, und was im Depot liegt,
verlaesst das Haus nicht (CLAUDE.md, "Privacy-Grenze"). Ein Depot-Titel, den eine Strategie
trotzdem vorschlaegt, faellt hier still heraus.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from core.storage.kandidaten import IGNORIERT_NACH_TAGEN, Kandidat, KandidatenRepository  # noqa: F401
from core.storage.models import Position

#: Wer einen Kandidaten vorgeschlagen hat -- wie bisher in ``recommendation_source``.
QUELLE = {
    "frei": "search_agent",
    "einzeltitel": "research_agent",
    "strukturwandel": "Claude Strukturwandel-Agent",
}


def _schluessel(ticker: Optional[str], name: Optional[str]) -> str:
    """Woran zwei Vorschlaege als derselbe Titel gelten: der Ticker, ohne ihn der Name."""
    if ticker and ticker.strip():
        return "t:" + ticker.strip().upper()
    return "n:" + (name or "").strip().casefold()


def _vorhandene(positions_repo, kandidaten_repo: KandidatenRepository) -> dict[str, tuple[Position, Optional[Kandidat]]]:
    """Je Schluessel die Position, die ihn traegt: Depot und Watchlist zuerst, dann Kandidaten."""
    kandidaten = {k.position_id: k for k in kandidaten_repo.alle()}
    je_schluessel: dict[str, tuple[Position, Optional[Kandidat]]] = {}
    for p in positions_repo.get_all():
        k = kandidaten.get(p.id)
        if not (p.in_portfolio or p.in_watchlist) and k is None:
            continue          # weder Liste noch Kandidat: nicht bekannt
        s = _schluessel(p.ticker, p.name)
        if s not in je_schluessel or p.in_portfolio or p.in_watchlist:
            je_schluessel[s] = (p, k)
    return je_schluessel


def _position(proposal: dict, strategie: str, skill: Optional[str]) -> Position:
    from core.asset_class_config import get_asset_class_registry

    registry = get_asset_class_registry()
    klasse = proposal.get("asset_class") or "Aktie"
    try:
        cfg = registry.require(klasse)
    except ValueError:
        klasse, cfg = "Aktie", registry.require("Aktie")
    ticker = (proposal.get("ticker") or "").strip()
    return Position(
        ticker=ticker or None,
        name=proposal.get("name") or ticker or "?",
        asset_class=klasse,
        investment_type=cfg.investment_type,
        unit=cfg.default_unit,
        notes=proposal.get("notes") or None,
        story=proposal.get("full_story") or proposal.get("story") or None,
        recommendation_source=QUELLE.get(strategie, strategie),
        strategy=skill,
        added_date=date.today(),
        in_portfolio=False,
        in_watchlist=False,
    )


@dataclass(frozen=True)
class Aufnahme:
    neu: int          # neue Kandidaten
    wieder: int       # schon offener Kandidat, Herkunft gewachsen
    verworfen: int    # schon verworfen -- bleibt es, die Herkunft waechst trotzdem
    bekannt: int      # stehen im Depot oder auf der Watchlist -- kein Kandidat


def aufnehmen(positions_repo, kandidaten_repo: KandidatenRepository, vorschlaege: list[dict],
              strategie: str, skill: Optional[str], lauf_id: Optional[int],
              jetzt: Optional[datetime] = None) -> Aufnahme:
    """Legt die Vorschlaege eines Laufs in die Liste. Idempotent je Titel: Ein zweiter Fund
    desselben Titels zaehlt hoch, statt einen zweiten Kandidaten anzulegen."""
    vorhanden = _vorhandene(positions_repo, kandidaten_repo)
    neu = wieder = verworfen = bekannt = 0
    for v in vorschlaege:
        s = _schluessel(v.get("ticker"), v.get("name"))
        if s in vorhanden:
            p, k = vorhanden[s]
            if p.in_portfolio or p.in_watchlist:
                bekannt += 1
                continue
            kandidaten_repo.wieder_gefunden(p.id, strategie, skill, lauf_id, jetzt)
            if k.zustand == "verworfen":
                verworfen += 1
            else:
                if k.zustand == "uebernommen":      # inzwischen von der Watchlist genommen
                    kandidaten_repo.setzen(p.id, "offen", jetzt)
                wieder += 1
            continue
        p = positions_repo.add(_position(v, strategie, skill))
        k = kandidaten_repo.anlegen(p.id, strategie, skill, lauf_id, jetzt)
        vorhanden[s] = (p, k)
        neu += 1
    return Aufnahme(neu, wieder, verworfen, bekannt)


def bekannte_ticker(positions_repo, kandidaten_repo: KandidatenRepository) -> list[str]:
    """Was die Strategien nicht wieder vorschlagen sollen: Watchlist, offene und verworfene
    Kandidaten. **Ohne das Depot** -- auch ein Titel, der zugleich auf der Watchlist steht,
    bleibt draussen, sonst verriete die Liste den Bestand."""
    kandidaten = {k.position_id for k in kandidaten_repo.alle() if k.zustand in ("offen", "verworfen")}
    ticker = set()
    for p in positions_repo.get_all():
        if p.in_portfolio or not p.ticker:
            continue
        if p.in_watchlist or p.id in kandidaten:
            ticker.add(p.ticker.strip().upper())
    return sorted(ticker)


def ausschluss(ticker: list[str]) -> str:
    """Der Absatz fuer den Systemprompt einer Strategie; leer, wenn nichts bekannt ist."""
    if not ticker:
        return ""
    return ("\n\n## Already known -- do not propose again\n"
            "These tickers are already on the watchlist, open candidates or were rejected. "
            "Do not propose them again; look for others.\n" + ", ".join(ticker))


def auf_die_watchlist(positions_repo, kandidaten_repo: KandidatenRepository, position_id: int) -> None:
    """Ja: Der Titel kommt auf die Watchlist; seine Urteile nimmt er mit (sie haengen an der ID).
    Das Aufnahmedatum wird heute -- ab da zaehlt "seit Aufnahme"."""
    p = positions_repo.get(position_id)
    if p is None:
        return
    positions_repo.update(p.model_copy(update={"in_watchlist": True, "added_date": date.today()}))
    kandidaten_repo.setzen(position_id, "uebernommen")


def verwerfen(kandidaten_repo: KandidatenRepository, position_id: int) -> None:
    """Nein, gemerkt: mit Datum, Strategie und These; nie geloescht."""
    kandidaten_repo.setzen(position_id, "verworfen")


def wieder_aufnehmen(kandidaten_repo: KandidatenRepository, position_id: int) -> None:
    """Aus "Verworfen" oder "Ignoriert" zurueck nach "Offen"; die 60 Tage beginnen neu."""
    kandidaten_repo.setzen(position_id, "offen")


@dataclass(frozen=True)
class Listen:
    offen: list[tuple[Position, Kandidat]]
    ignoriert: list[tuple[Position, Kandidat]]
    verworfen: list[tuple[Position, Kandidat]]


def listen(positions_repo, kandidaten_repo: KandidatenRepository,
           jetzt: Optional[datetime] = None) -> Listen:
    """Die drei Teile der Seite, je juengste Beruehrung zuerst. Ein Kandidat, dessen Position
    inzwischen auf einer Liste steht oder geloescht ist, faellt heraus."""
    offen, ignoriert, verworfen = [], [], []
    for k in kandidaten_repo.alle():
        if k.zustand == "uebernommen":
            continue
        p = positions_repo.get(k.position_id)
        if p is None or p.in_portfolio or p.in_watchlist:
            continue
        if k.zustand == "verworfen":
            verworfen.append((p, k))
        elif k.ignoriert(jetzt):
            ignoriert.append((p, k))
        else:
            offen.append((p, k))
    return Listen(offen, ignoriert, verworfen)
