"""Was die Titelseite eines Titels rechnet — ohne Streamlit, damit die Tests es direkt lesen.

Die Titelseite (``core/ui/titelseite.py``) ist die eine Seite hinter den Kacheln, für Depot
und Watchlist. Jeder Abschnitt beginnt mit einem Satz; die Sätze entstehen hier aus dem, was
schon gespeichert ist (Kurse, Urteile). Nichts wird geholt, kein Check wird gestartet.

Das Urteilsband unter dem Kurschart zeigt je Check, welches Urteil wann galt: Ein Urteil gilt
von seinem Tag bis zum nächsten Urteil desselben Checks, das jüngste bis heute. Gelesen wird
nur ``position_analyses`` (Urteil und Satz), nie die Volltexte — die dürfen später verfallen
(BACKLOG.md, "Checks je Liste").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable, Optional, Sequence

#: Ampelfarbe je Symbol aus ``VERDICT_CONFIGS``; dieselben Töne wie auf den Kacheln.
FARBE = {
    "🟢": "#1A7F4B",
    "🟡": "#D9A21B",
    "🟠": "#E07B00",
    "🔠": "#E07B00",   # so steht "schließt" in VERDICT_CONFIGS
    "🔴": "#C0262D",
    "⚪": "#A3ABBA",
}
FARBE_SONST = "#A3ABBA"

_POSITIV = {"🟢"}
_NEGATIV = {"🟠", "🔠", "🔴"}


@dataclass(frozen=True)
class Strecke:
    """Ein Stück des Urteilsbands: von ``von`` bis ``bis`` galt ``verdict`` dieses Checks."""
    agent: str
    von: date
    bis: date
    verdict: Optional[str]
    summary: Optional[str]
    geprueft_am: date          # der Tag des Urteils (vor dem Fenster, wenn ``von`` abgeschnitten ist)


def _tag(ts) -> date:
    if isinstance(ts, datetime):
        return (ts if ts.tzinfo is None else ts.astimezone(timezone.utc)).date()
    return ts


def band(analysen: Iterable, agenten: Sequence[str], von: date, bis: date) -> list[Strecke]:
    """Die Strecken je Check im Fenster ``von``..``bis``.

    ``analysen``: Zeilen aus ``position_analyses`` (``agent``, ``verdict``, ``summary``,
    ``created_at``), in beliebiger Reihenfolge. Ein Urteil von vor dem Fenster beginnt am
    Fensterrand; liegt vor ihm ein jüngeres, fällt es weg. Ein Check ohne Urteil hat keine
    Strecke -- die Lücke ist die Aussage.
    """
    je_agent: dict[str, list] = {a: [] for a in agenten}
    for a in analysen:
        if a.agent in je_agent and a.created_at is not None:
            je_agent[a.agent].append(a)

    strecken: list[Strecke] = []
    for agent in agenten:
        reihe = sorted(je_agent[agent], key=lambda a: a.created_at)
        # Am selben Tag zählt das letzte Urteil.
        je_tag: dict[date, object] = {}
        for a in reihe:
            je_tag[_tag(a.created_at)] = a
        tage = sorted(je_tag)
        for i, tag in enumerate(tage):
            ende = tage[i + 1] if i + 1 < len(tage) else bis
            anfang, schluss = max(tag, von), min(ende, bis)
            # Abgelöst, bevor das Fenster beginnt -- oder erst nach seinem Ende geprüft.
            if schluss < anfang or (schluss == anfang and tag < von):
                continue
            a = je_tag[tag]
            strecken.append(Strecke(agent, anfang, schluss, a.verdict, a.summary, tag))
    return strecken


def symbol(verdict: Optional[str], config: dict) -> str:
    """Das Ampelsymbol eines Urteils; die ASCII-Schreibweise ("gefaehrdet") findet ihren
    Umlaut-Schlüssel."""
    v = verdict or ""
    if v not in config:
        v = v.replace("ae", "ä").replace("oe", "ö").replace("ue", "ü")
    return config.get(v, ("⚪", ""))[0]


def urteile_zaehlen(symbole: Sequence[Optional[str]]) -> dict[str, int]:
    """Wie viele Checks positiv, kritisch, dazwischen und nie geprüft sind (None = nie)."""
    da = [s for s in symbole if s is not None]
    return {
        "positiv": sum(1 for s in da if s in _POSITIV),
        "kritisch": sum(1 for s in da if s in _NEGATIV),
        "mitte": sum(1 for s in da if s not in _POSITIV and s not in _NEGATIV),
        "nie": len(symbole) - len(da),
        "alle": len(symbole),
    }


def kurs_veraenderung(verlauf: Sequence, tage: Optional[int] = None) -> Optional[float]:
    """Prozent vom ersten Kurs (oder dem vor ``tage`` Tagen) bis zum letzten. ``verlauf``:
    ``HistoricalPrice`` aufsteigend nach Datum."""
    if len(verlauf) < 2:
        return None
    letzter = verlauf[-1]
    if tage is None:
        erster = verlauf[0]
    else:
        grenze = letzter.date.toordinal() - tage
        frueher = [h for h in verlauf if h.date.toordinal() <= grenze]
        if not frueher:
            return None
        erster = frueher[-1]
    if not erster.close_eur:
        return None
    return (letzter.close_eur / erster.close_eur - 1) * 100


def news_abschnitt(digest: Optional[str], ticker: Optional[str]) -> Optional[str]:
    """Der Abschnitt ``## TICKER ...`` aus einem News Digest, bis zum nächsten ``##``."""
    if not digest or not ticker:
        return None
    zeilen = digest.split("\n")
    start = None
    for i, zeile in enumerate(zeilen):
        if zeile.strip().startswith("##"):
            kopf = zeile.replace("##", "").strip()
            if kopf and kopf.split()[0].upper() == ticker.upper():
                start = i
                break
    if start is None:
        return None
    ende = next((i for i in range(start + 1, len(zeilen)) if zeilen[i].strip().startswith("##")),
                len(zeilen))
    abschnitt = "\n".join(zeilen[start:ende]).strip()
    if abschnitt.endswith("---"):
        abschnitt = abschnitt[:-3].strip()
    return abschnitt or None
