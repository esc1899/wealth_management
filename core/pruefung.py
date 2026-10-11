"""Welche Checks zu einer Prüfung gehören -- je Liste (Depot, Watchlist) eine Auswahl.

Eine Prüfung eines Titels ist ein **Durchgang**: alle gewählten Checks, ein Datum
(``core/storage/durchgaenge.py``). Was gewählt ist, steht in ``app_config`` unter
``pruefung_auswahl_<liste>`` und wird auf der Seite Einstellungen bearbeitet; die Kacheln und
die Titelseite zeigen genau diese Checks, auch die, die für einen Titel nie liefen.

Möglich ist je Liste eine feste Reihe in fester Reihenfolge. Devil's Advocate gehört nur auf
die Watchlist (Erik, 11.10.2026): Er sucht Gründe, einen Titel *nicht* zu kaufen.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Optional

#: Was je Liste gewählt werden kann, in Anzeigereihenfolge.
MOEGLICH: dict[str, tuple[str, ...]] = {
    "depot": ("storychecker", "fundamental_analyzer", "consensus_gap", "capital_allocator"),
    "watchlist": ("watchlist_checker", "devils_advocate", "fundamental_analyzer",
                  "capital_allocator", "consensus_gap", "storychecker"),
}

#: Läuft lokal und liest die Urteile der anderen -- darum im Durchgang zuletzt.
ZULETZT = ("watchlist_checker",)

_SCHLUESSEL = "pruefung_auswahl_{}"


def auswahl(app_cfg, liste: str) -> tuple[str, ...]:
    """Die gewählten Checks der Liste in fester Reihenfolge; nie gewählt = alles Mögliche.
    Ein gespeicherter Name, den es nicht mehr gibt, fällt still weg."""
    moeglich = MOEGLICH[liste]
    gespeichert = app_cfg.get_json(_SCHLUESSEL.format(liste)) if app_cfg is not None else None
    if not isinstance(gespeichert, list):
        return moeglich
    return tuple(c for c in moeglich if c in gespeichert)


def auswahl_setzen(app_cfg, liste: str, checks: Iterable[str]) -> tuple[str, ...]:
    """Speichert die Auswahl (nur Mögliches, feste Reihenfolge) und gibt sie zurück."""
    gewaehlt = set(checks)
    reihe = tuple(c for c in MOEGLICH[liste] if c in gewaehlt)
    app_cfg.set_json(_SCHLUESSEL.format(liste), list(reihe))
    return reihe


def reihenfolge(checks: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(zuerst, danach): die Cloud-Checks parallel, dann die, die deren Urteile lesen."""
    checks = tuple(checks)
    return (tuple(c for c in checks if c not in ZULETZT),
            tuple(c for c in checks if c in ZULETZT))


def depot_kontext(portfolio: list, story_analyse=None, stabilitaet: str = "Stabilität:",
                  leer: str = "") -> tuple[str, Optional[str]]:
    """Was der Watchlist Checker über das Depot erfährt: die Verteilung nach Anlageklasse und
    die jüngste Analyse der Portfolio-Story. Beides lokal (Ollama), nie in die Cloud."""
    snapshot = "## Portfolio Allocation (Josef's Regel)\n"
    if portfolio:
        zahl = Counter(p.asset_class for p in portfolio if p.asset_class)
        gesamt = len(portfolio)
        for klasse, n in zahl.most_common():
            snapshot += f"- {klasse}: {n} Positionen ({100 * n / gesamt:.0f}%)\n"
    else:
        snapshot += leer + "\n"

    if story_analyse is None:
        return snapshot, None
    a = story_analyse
    return snapshot, f"""## Portfolio Story Context
Story: {a.verdict}
Summary: {a.summary}
Performance: {a.perf_verdict} - {a.perf_summary}
{stabilitaet} {a.stability_verdict} - {a.stability_summary}

Full Analysis:
{a.full_text}
"""
