"""Starke Kursbewegung: ab welcher Tagesbewegung ein Titel auffällt, und der Grund dazu.

Die Kachel rückt einen Titel nach oben, wenn er sich heute stark bewegt; bis 11.10.2026 stand
dort nur die Zahl. Seitdem sucht der Job ``kurse`` für die stärksten Bewegungen des Tages
Nachrichten nur zu diesem Titel (``core/scheduler.py::bewegungen_nachrichten``), und Kachel und
Titelseite nennen den Grund. Anlass: Schneider Electric, Übernahme angekündigt, Kurs stark
bewegt -- der monatliche Digest wusste nichts davon.

Seit 17.10.2026 mit eigenem Modell (Bereich "Kursbewegung" in den Einstellungen) und als Batch,
wo das Modell es erlaubt: Der Grund steht dann eine bis zwei Stunden nach dem Lauf da.

Die Schwelle ist eine Einstellung (Erik: ein Titel springt ständig über 4 %); Kachel und Job
lesen dieselbe. Höchstens ``DECKEL`` Titel je Tag, jeder einmal. An das Cloud-Modell gehen nur
Ticker und Name.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable, Optional

#: Ab dieser Tagesbewegung (Prozent, beide Richtungen), solange keine Einstellung gilt.
STANDARD_PROZENT = 4.0
#: So viele Titel sucht der Job höchstens je Tag (Erik, 11.10.2026).
DECKEL = 3
#: So viele Websuchen hat eine Suche nach dem Grund höchstens (Erik, 17.10.2026). Der Digest
#: erlaubt mindestens vier; jede bringt ihre Treffer als Eingabe mit, bei Sonnet 20 bis 67 k
#: Token je Titel -- für einen Titel und einen Tag reichen zwei.
SUCHEN = 2
#: So heißen die Läufe in ``news_runs``; daran erkennt der Job, was heute schon gesucht ist.
LAUF = "Bewegung"
#: Unter diesem Namen bucht die Suche ihre Kosten, steht ihr Batch in ``pending_batches`` und
#: hat sie ihr Modell (``core/pruefung.py::BEREICHE``). Bis 17.10.2026 lief sie als News-Digest.
AGENT = "bewegung"

_SCHLUESSEL = "bewegung_prozent"


def schwelle(app_cfg) -> float:
    try:
        wert = float(app_cfg.get(_SCHLUESSEL)) if app_cfg is not None and app_cfg.get(_SCHLUESSEL) else None
    except (TypeError, ValueError):
        wert = None
    return wert if wert and wert > 0 else STANDARD_PROZENT


def schwelle_setzen(app_cfg, prozent: float) -> None:
    app_cfg.set(_SCHLUESSEL, str(float(prozent)))


def tagesbewegung(kurs: Optional[float], vortag: Optional[float]) -> Optional[float]:
    if kurs is None or not vortag:
        return None
    return (kurs / vortag - 1) * 100


def _tag(ts: datetime) -> date:
    return (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)).astimezone().date()


def heute_gesucht(laeufe: Iterable, heute: date) -> dict[str, object]:
    """``{ticker: lauf}`` der Bewegungs-Läufe von heute (Ortszeit)."""
    gesucht = {}
    for lauf in laeufe:
        if lauf.skill_name == LAUF and lauf.created_at and _tag(lauf.created_at) == heute:
            for t in (lauf.tickers or "").split(","):
                if t.strip():
                    gesucht.setdefault(t.strip().upper(), lauf)
    return gesucht


def staerkste(bewegungen: dict[str, float], grenze: float, schon: Iterable[str],
              deckel: int = DECKEL) -> list[tuple[str, float]]:
    """Die stärksten Bewegungen ab ``grenze``, ohne die schon gesuchten; heute höchstens
    ``deckel`` insgesamt (die schon gesuchten zählen mit)."""
    schon = {t.upper() for t in schon}
    frei = max(0, deckel - len(schon))
    kandidaten = sorted(((t, p) for t, p in bewegungen.items()
                         if p is not None and abs(p) >= grenze and t.upper() not in schon),
                        key=lambda tp: -abs(tp[1]))
    return kandidaten[:frei]


def grund(digest: Optional[str], ticker: Optional[str]) -> Optional[str]:
    """Der erste Punkt des Abschnitts ``## TICKER`` -- der Satz für die Kachel."""
    from core.titelseite import news_abschnitt

    abschnitt = news_abschnitt(digest, ticker)
    if not abschnitt:
        return None
    for zeile in abschnitt.split("\n")[1:]:
        z = zeile.strip()
        if z.startswith("-") and not z.lstrip("- ").startswith("**"):
            return z.lstrip("- ").strip() or None
    return None


def auftrag(name: str, ticker: str, prozent: float) -> str:
    """Der Filter für den Digest: nur dieser Titel, nur der Grund der Bewegung."""
    richtung = "gestiegen" if prozent > 0 else "gefallen"
    return (f"Der Kurs von {name} ({ticker}) ist heute um {abs(prozent):.1f} % {richtung}. "
            "Finde den Grund in Nachrichten der letzten drei Tage. Der erste Punkt nennt den Grund "
            "in einem Satz; danach höchstens zwei weitere Punkte. Findest du keinen Grund, schreibe "
            "das als ersten Punkt, statt zu raten. Antworte auf Deutsch.")
