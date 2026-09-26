"""Der Story-Check als Meldung auf der Startseite des Mac mini (Dienste Schritt 15).

Wenn der Story-Checker einmal durch das ganze Depot ist, steht auf der Kachel die Summe
seiner Urteile — "Story-Check: 10 intakt · 5 gemischt · 2 gefährdet" — mit einem Link auf
den Checker. Die anderen Läufe kommen und gehen; der Story-Check ist der, auf den es ankommt
(Erik, 26.09.2026).

"Durch" heißt: Jede Depot-Position mit Story hat ein Urteil, und der **Durchgang** ist das
älteste dieser jüngsten Urteile. Er wächst nur, wenn wirklich jede Position neu geprüft
wurde — gleich ob per Plan, Batch oder Knopf —, und ist damit Wasserstand und Schlüssel
zugleich: Wer die Meldung verwirft, verwirft diesen Durchgang; der nächste bringt eine neue.
Eine neu aufgenommene Position ohne Urteil nimmt die Meldung weg, bis sie geprüft ist.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import quote

#: Unter diesem Schlüssel merkt sich die App (app_config), welcher Durchgang verworfen ist.
VERWORFEN_KEY = "startseite.story_meldung.verworfen"

_WORTE = (("intact", "intakt"), ("gemischt", "gemischt"), ("gefaehrdet", "gefährdet"),
          ("unknown", "ohne Urteil"))


def _utc(ts: datetime) -> datetime:
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts   # created_at ist naives UTC


def durchgang(urteile: dict[int, tuple[str, datetime]], positionen: Iterable[int]) -> Optional[datetime]:
    """Der Zeitpunkt, zu dem das ganze Depot zuletzt geprüft war — oder None, solange
    eine Position noch kein Urteil hat (oder es keine gibt)."""
    ids = list(positionen)
    if not ids or any(i not in urteile for i in ids):
        return None
    return min(_utc(urteile[i][1]) for i in ids)


def story_meldung(urteile: dict[int, tuple[str, datetime]], positionen: Iterable[int],
                  verworfen: Optional[str] = None) -> Optional[dict]:
    """Die Meldung im Schema der Startseite — oder None (nicht durch, oder verworfen).

    `urteile`: je Position das jüngste Story-Urteil (verdict, created_at).
    `verworfen`: der Schlüssel des Durchgangs, den Erik weggeklickt hat."""
    ids = list(positionen)
    stamm = durchgang(urteile, ids)
    if stamm is None:
        return None
    schluessel = stamm.isoformat(timespec="seconds")
    if verworfen == schluessel:
        return None
    zahl = {k: 0 for k, _ in _WORTE}
    for i in ids:
        v = urteile[i][0]
        zahl[v if v in zahl else "unknown"] += 1
    teile = [f"{zahl[k]} {wort}" for k, wort in _WORTE if zahl[k] or k != "unknown"]
    fertig = max(_utc(urteile[i][1]) for i in ids).astimezone()
    return {"text": "Story-Check: " + " · ".join(teile),
            "zustand": "schlecht" if zahl["gefaehrdet"] else "hinweis",
            "lauf": "Story-Check", "von": fertig.date().isoformat(),
            "ziel": "storychecker", "schluessel": schluessel,
            # Das x: POST an den Empfänger (scripts/meldungen_dienst.py), über denselben Weg
            # wie das Kachel-JSON -- sonst zeigt die Startseite keins.
            "verwerfen": "kacheln/wealth/verwerfen?story=" + quote(schluessel, safe="")}
