"""Je Titel eine Kachel: der eine Satz, der gerade zählt, und Kennzahlen für den ersten Blick.

Die Checker laufen, gelesen werden aber nur wenige ihrer Ergebnisse; die Kacheln der
Startseite und der Serien-Watchlist werden gelesen (Erik, 10.10.2026). Darum fasst diese
Ansicht je Position zusammen, was die Agenten schon abgelegt haben — sie rechnet nichts
Neues und startet keinen Check.

Welcher Satz oben steht, entscheidet ein fester Vorrang, nicht der Agent:

1. **gefährdet** — Storychecker "gefährdet" oder Devil's Advocate "kritisch"
2. **Bewegung** — heute mindestens ``BEWEGUNG_PROZENT`` in eine Richtung
3. **geprüft** — sonst der jüngste Satz irgendeines Checkers, mit Datum
4. **nie geprüft** — ohne jedes Urteil; Blindzeit ist eine Aussage, kein "alles gut"

Termine (Zahlen, Ex-Tag) und Zielkurse fehlen, weil die App für beides keine Quelle hat.
Nach demselben Vorrang wird sortiert: Was handeln lässt, steht oben.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

#: Ab dieser Tagesbewegung (in Prozent, beide Richtungen) rückt sie nach oben.
BEWEGUNG_PROZENT = 4.0

#: Die Agenten, deren Urteile auf einer Kachel stehen können, in Anzeigereihenfolge.
DEPOT_AGENTEN = ("storychecker", "fundamental_analyzer", "consensus_gap",
                 "capital_allocator", "devils_advocate")
WATCHLIST_AGENTEN = ("watchlist_checker", "devils_advocate", "fundamental_analyzer",
                     "capital_allocator", "consensus_gap", "storychecker")

# Urteile, die die These angreifen. Der Storychecker hat beide Schreibweisen abgelegt.
_GEFAEHRDET = {("storychecker", "gefährdet"), ("storychecker", "gefaehrdet"),
               ("devils_advocate", "kritisch")}

# Rang je Grund — kleiner steht weiter oben.
RANG = {"gefaehrdet": 0, "bewegung": 1, "geprueft": 2, "nie": 3}


@dataclass
class Urteil:
    agent: str
    verdict: Optional[str]
    summary: Optional[str]
    created_at: Optional[datetime]


@dataclass
class Kachel:
    position_id: int
    name: str
    klasse: str                         # Anlageart oder -klasse, steht im Kopf unter dem Namen
    anlageklasse: str                   # bestimmt die Farbe (asset_classes.yaml, ueberall dieselbe)
    grund: str                          # Schlüssel aus RANG
    satz: Optional[str]                 # der Satz oben; None bei "bewegung"/"nie" (Text macht die Seite)
    satz_agent: Optional[str]           # von wem der Satz stammt
    satz_datum: Optional[datetime]
    tag_prozent: Optional[float]
    seit_kauf_prozent: Optional[float]  # nur Depot
    seit_aufnahme_prozent: Optional[float]  # nur Watchlist: Kurs heute gegen Kurs am Aufnahmetag
    ticker: Optional[str]
    kurs_eur: Optional[float]
    dividende_prozent: Optional[float]
    urteile: list[Urteil] = field(default_factory=list)   # je Agent das juengste


def _utc(ts: Optional[datetime]) -> Optional[datetime]:
    if ts is None:
        return None
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts   # created_at ist naives UTC


def tagesprozent(day_pnl_pct: Optional[float], kurs: Optional[float],
                 vortag: Optional[float]) -> Optional[float]:
    """Die Tagesbewegung. Das Depot hat sie aus der Bewertung; der Watchlist fehlt sie dort,
    weil sie ohne Stückzahl gerechnet wird — dann aus Kurs und Vortagesschluss."""
    if day_pnl_pct is not None:
        return day_pnl_pct
    if kurs is not None and vortag:
        return (kurs / vortag - 1) * 100
    return None


def kachel(position, art: str, valuation=None, urteile: Optional[dict] = None,
           vortag: Optional[float] = None, aufnahme_kurs: Optional[float] = None) -> Kachel:
    """Eine Kachel aus Position, Bewertung (``PortfolioValuation`` oder None) und den
    jüngsten Urteilen je Agent (``{agent: PositionAnalysis}``). ``aufnahme_kurs``: der
    gespeicherte Schlusskurs am Tag, an dem der Titel auf die Watchlist kam."""
    agenten = DEPOT_AGENTEN if art == "depot" else WATCHLIST_AGENTEN
    vorhanden = [
        Urteil(a, u.verdict, u.summary, _utc(u.created_at))
        for a in agenten
        if (u := (urteile or {}).get(a)) is not None
    ]

    kurs = valuation.current_price_eur if valuation else None
    tag = tagesprozent(valuation.day_pnl_pct if valuation else None, kurs, vortag)

    grund, satz, quelle = "nie", None, None
    angriff = [u for u in vorhanden if (u.agent, u.verdict) in _GEFAEHRDET]
    mit_satz = sorted((u for u in vorhanden if u.summary),
                      key=lambda u: u.created_at or datetime.min.replace(tzinfo=timezone.utc),
                      reverse=True)
    if angriff:
        grund, quelle = "gefaehrdet", angriff[0]
    elif tag is not None and abs(tag) >= BEWEGUNG_PROZENT:
        grund = "bewegung"
    elif mit_satz:
        grund, quelle = "geprueft", mit_satz[0]
    elif vorhanden:
        # Ein Urteil ohne Satz ist trotzdem eine Prüfung.
        grund, quelle = "geprueft", max(vorhanden, key=lambda u: u.created_at or datetime.min.replace(tzinfo=timezone.utc))
    if quelle is not None:
        satz = quelle.summary

    return Kachel(
        position_id=position.id,
        name=position.name,
        klasse=position.anlageart or position.asset_class,
        anlageklasse=position.asset_class,
        grund=grund,
        satz=satz,
        satz_agent=quelle.agent if quelle else None,
        satz_datum=quelle.created_at if quelle else None,
        tag_prozent=tag,
        seit_kauf_prozent=valuation.pnl_pct if (valuation and art == "depot") else None,
        seit_aufnahme_prozent=((kurs / aufnahme_kurs - 1) * 100
                               if art == "watchlist" and kurs is not None and aufnahme_kurs else None),
        ticker=position.ticker,
        kurs_eur=kurs,
        dividende_prozent=(valuation.dividend_yield_pct * 100
                           if valuation and valuation.dividend_yield_pct else None),
        urteile=vorhanden,
    )


def sortiert(kacheln: Iterable[Kachel]) -> list[Kachel]:
    """Nach Vorrang; innerhalb von "Bewegung" die stärkste zuerst, sonst nach Name."""
    return sorted(kacheln, key=lambda k: (
        RANG[k.grund],
        -abs(k.tag_prozent or 0) if k.grund == "bewegung" else 0,
        k.name.lower(),
    ))
