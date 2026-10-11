"""KandidatenRepository -- die stehende Liste der Suche (BACKLOG.md, "Suche", 11.10.2026).

Ein Kandidat ist eine Position auf keiner der beiden Listen (``in_portfolio = in_watchlist = 0``)
mit einer Zeile hier. So tragen Checks, Urteilsband und Titelseite ohne Umbau -- sie haengen
an der Positions-ID. Eine Position ohne Zeile hier ist kein Kandidat, auch wenn sie auf keiner
Liste steht.

Zustand: ``offen`` (unentschieden), ``verworfen`` (gemerktes Nein, nie geloescht) oder
``uebernommen`` (auf die Watchlist gelegt; die Zeile bleibt als Herkunft). "Ignoriert" ist kein
Zustand, sondern ein offener Kandidat, den 60 Tage niemand beruehrt hat -- gerechnet beim Lesen,
damit nichts still zum Nein wird.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

#: Nach so vielen Tagen ohne Beruehrung rueckt ein offener Kandidat unter "Ignoriert".
IGNORIERT_NACH_TAGEN = 60

ZUSTAENDE = ("offen", "verworfen", "uebernommen")


@dataclass(frozen=True)
class Kandidat:
    position_id: int
    zustand: str
    strategie: str            # frei | einzeltitel | strukturwandel
    skill: Optional[str]
    lauf_id: Optional[int]    # der juengste Lauf, der ihn fand (Sitzung bzw. Scan der Strategie)
    funde: int
    gefunden: datetime
    beruehrt: datetime
    entschieden: Optional[datetime]

    def ignoriert(self, jetzt: Optional[datetime] = None) -> bool:
        jetzt = jetzt or datetime.now(timezone.utc)
        return self.zustand == "offen" and jetzt - self.beruehrt >= timedelta(days=IGNORIERT_NACH_TAGEN)


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


def _zeit(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    ts = datetime.fromisoformat(text)
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


class KandidatenRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def anlegen(self, position_id: int, strategie: str, skill: Optional[str],
                lauf_id: Optional[int], jetzt: Optional[datetime] = None) -> Kandidat:
        zeit = (jetzt or _jetzt()).isoformat()
        self._conn.execute(
            "INSERT INTO kandidaten (position_id, zustand, strategie, skill, lauf_id, funde, "
            "gefunden, beruehrt) VALUES (?, 'offen', ?, ?, ?, 1, ?, ?)",
            (position_id, strategie, skill, lauf_id, zeit, zeit),
        )
        self._conn.commit()
        return self.get(position_id)

    def wieder_gefunden(self, position_id: int, strategie: str, skill: Optional[str],
                        lauf_id: Optional[int], jetzt: Optional[datetime] = None) -> Kandidat:
        """Ein spaeterer Lauf fand ihn noch einmal: die Herkunft waechst, kein zweiter Kandidat.
        Ein verworfener bleibt verworfen -- ein Nein wird nicht still zurueckgenommen."""
        self._conn.execute(
            "UPDATE kandidaten SET funde = funde + 1, strategie = ?, skill = ?, lauf_id = ?, "
            "beruehrt = ? WHERE position_id = ?",
            (strategie, skill, lauf_id, (jetzt or _jetzt()).isoformat(), position_id),
        )
        self._conn.commit()
        return self.get(position_id)

    def beruehren(self, position_id: int, jetzt: Optional[datetime] = None) -> None:
        """Jemand hat sich mit ihm befasst (genauer geprueft) -- er ist nicht ignoriert."""
        self._conn.execute("UPDATE kandidaten SET beruehrt = ? WHERE position_id = ?",
                           ((jetzt or _jetzt()).isoformat(), position_id))
        self._conn.commit()

    def setzen(self, position_id: int, zustand: str, jetzt: Optional[datetime] = None) -> None:
        if zustand not in ZUSTAENDE:
            raise ValueError(f"Unbekannter Zustand: {zustand}")
        zeit = (jetzt or _jetzt()).isoformat()
        self._conn.execute(
            "UPDATE kandidaten SET zustand = ?, beruehrt = ?, entschieden = ? WHERE position_id = ?",
            (zustand, zeit, None if zustand == "offen" else zeit, position_id),
        )
        self._conn.commit()

    def get(self, position_id: int) -> Optional[Kandidat]:
        row = self._conn.execute("SELECT * FROM kandidaten WHERE position_id = ?",
                                 (position_id,)).fetchone()
        return self._zeile(row) if row else None

    def alle(self, zustand: Optional[str] = None) -> list[Kandidat]:
        if zustand is None:
            rows = self._conn.execute("SELECT * FROM kandidaten ORDER BY beruehrt DESC").fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM kandidaten WHERE zustand = ? ORDER BY beruehrt DESC",
                                      (zustand,)).fetchall()
        return [self._zeile(r) for r in rows]

    @staticmethod
    def _zeile(row) -> Kandidat:
        return Kandidat(
            position_id=row["position_id"], zustand=row["zustand"], strategie=row["strategie"],
            skill=row["skill"], lauf_id=row["lauf_id"], funde=row["funde"],
            gefunden=_zeit(row["gefunden"]), beruehrt=_zeit(row["beruehrt"]),
            entschieden=_zeit(row["entschieden"]),
        )
