"""Das Tagesbild des Depots: Tagesveränderung in Prozent und die größte Bewegung.

Eine Rechnung für zwei Anzeigen — die Kachel auf der Startseite des Mac mini
(scripts/kachel.py) und die Kopfzeile des Dashboards. Beide lesen die Bewertung
aus der Datenbank (``MarketDataAgent.get_portfolio_valuation``), keine holt
Kurse; die hält der stündliche Kachel-Job frisch. Die Summenformel ist die der
Analyse-Seite (``aggregate_day_pnl``), damit nirgends eine zweite Zahl entsteht.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from core.symbol_aggregation import aggregate_day_pnl

MINUS = "−"   # das typografische Minus, wie auf der Startseite


@dataclass
class Tagesbild:
    positionen: int                    # Depot-Positionen (keine Watchlist)
    ohne_tageskurs: int                # davon ohne Tages-G/V
    prozent: Optional[float]           # Tagesveränderung des Depots; None ohne Tageskurse
    groesste_name: Optional[str]       # Name der größten Bewegung (Symbol, wenn kein Name)
    groesste_prozent: Optional[float]


def tagesbild(valuations: Iterable) -> Tagesbild:
    """Aus den Bewertungen des Portfolios (Watchlist wird ausgelassen)."""
    depot = [v for v in valuations if getattr(v, "in_portfolio", True)]
    mit_tag = [v for v in depot if v.day_pnl_eur is not None and v.current_value_eur is not None]
    vortag = sum(v.current_value_eur - v.day_pnl_eur for v in mit_tag)
    tag = sum(v.day_pnl_eur for v in mit_tag)
    pct = tag / vortag * 100 if mit_tag and vortag > 0 else None

    name = groesste = None
    bewegungen = [b for b in aggregate_day_pnl(mit_tag) if b.day_pnl_pct is not None]
    if bewegungen:
        staerkste = max(bewegungen, key=lambda b: abs(b.day_pnl_pct))
        name = next((v.name for v in mit_tag if v.symbol == staerkste.symbol and v.name), staerkste.symbol)
        groesste = staerkste.day_pnl_pct

    return Tagesbild(
        positionen=len(depot),
        ohne_tageskurs=len(depot) - len(mit_tag),
        prozent=pct,
        groesste_name=name,
        groesste_prozent=groesste,
    )


def prozent(wert: float) -> str:
    """+0,42 % / −1,08 % / ±0,00 % — deutsch, mit Vorzeichen."""
    if round(wert, 2) == 0:
        return "±0,00 %"
    text = f"{wert:+.2f}".replace(".", ",").replace("-", MINUS)
    return f"{text} %"


def groesste_bewegung(bild: Tagesbild) -> Optional[str]:
    """Der Satz unter der Zahl, derselbe auf Kachel und Dashboard."""
    if bild.groesste_name is None or bild.groesste_prozent is None:
        return None
    return f"Größte Bewegung: {bild.groesste_name} {prozent(bild.groesste_prozent)}"
