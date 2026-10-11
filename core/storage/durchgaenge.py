"""DurchgaengeRepository -- eine Pruefung eines Titels: alle gewaehlten Checks, ein Datum.

Ein Durchgang beginnt, bevor der erste Check laeuft, und endet, wenn alle Antworten da sind.
Die Agenten speichern ihre Urteile wie bisher in ``position_analyses``; erst der Abschluss
ordnet ihnen den Durchgang zu -- alle Analysen des Titels von den Checks des Durchgangs, die
seit seinem Beginn ohne Durchgang entstanden sind. So braucht kein Agent eine neue Signatur,
und ein Batch, der erst am naechsten Morgen zurueckkommt, schliesst genauso ab.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional


@dataclass(frozen=True)
class Durchgang:
    id: int
    liste: str
    position_id: int
    ausloeser: str            # "knopf" oder "job"
    checks: tuple[str, ...]
    begonnen: datetime
    beendet: Optional[datetime]
    fehler: Optional[str]


def _jetzt() -> str:
    # Dasselbe Format wie position_analyses.created_at, damit der Vergleich als Text traegt.
    return datetime.now(timezone.utc).isoformat()


class DurchgaengeRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def beginnen(self, liste: str, position_id: int, ausloeser: str,
                 checks: Iterable[str]) -> int:
        cur = self._conn.execute(
            "INSERT INTO durchgaenge (liste, position_id, ausloeser, checks, begonnen) "
            "VALUES (?, ?, ?, ?, ?)",
            (liste, position_id, ausloeser, json.dumps(list(checks)), _jetzt()),
        )
        self._conn.commit()
        return cur.lastrowid

    def abschliessen(self, durchgang_id: int, fehler: Optional[str] = None) -> int:
        """Beendet den Durchgang und ordnet ihm seine Analysen zu; gibt deren Zahl zurueck.
        Ein zweiter Abschluss aendert nichts mehr (idempotent)."""
        d = self.get(durchgang_id)
        if d is None or d.beendet is not None:
            return 0
        platz = ",".join("?" * len(d.checks)) or "NULL"
        cur = self._conn.execute(
            f"UPDATE position_analyses SET durchgang_id = ? "
            f"WHERE position_id = ? AND durchgang_id IS NULL AND created_at >= ? "
            f"AND agent IN ({platz})",
            (d.id, d.position_id, d.begonnen.isoformat(), *d.checks),
        )
        gesamt = "; ".join(f for f in (d.fehler, fehler) if f) or None
        self._conn.execute("UPDATE durchgaenge SET beendet = ?, fehler = ? WHERE id = ?",
                           (_jetzt(), gesamt, d.id))
        self._conn.commit()
        return cur.rowcount

    def fehler_vermerken(self, ids: Iterable[int], fehler: str) -> None:
        """Ein Check ist fuer diese Durchgaenge gescheitert; der Abschluss behaelt es."""
        for i in ids:
            self._conn.execute(
                "UPDATE durchgaenge SET fehler = CASE WHEN fehler IS NULL THEN ? "
                "ELSE fehler || '; ' || ? END WHERE id = ? AND beendet IS NULL", (fehler, fehler, i))
        self._conn.commit()

    def get(self, durchgang_id: int) -> Optional[Durchgang]:
        row = self._conn.execute("SELECT * FROM durchgaenge WHERE id = ?", (durchgang_id,)).fetchone()
        return self._zeile(row) if row else None

    def offene(self) -> list[Durchgang]:
        rows = self._conn.execute(
            "SELECT * FROM durchgaenge WHERE beendet IS NULL ORDER BY begonnen").fetchall()
        return [self._zeile(r) for r in rows]

    def fuer_titel(self, position_id: int, limit: int = 20) -> list[Durchgang]:
        """Die Durchgaenge eines Titels, der juengste zuerst."""
        rows = self._conn.execute(
            "SELECT * FROM durchgaenge WHERE position_id = ? ORDER BY begonnen DESC LIMIT ?",
            (position_id, limit),
        ).fetchall()
        return [self._zeile(r) for r in rows]

    @staticmethod
    def _zeile(row: sqlite3.Row) -> Durchgang:
        return Durchgang(
            id=row["id"], liste=row["liste"], position_id=row["position_id"],
            ausloeser=row["ausloeser"], checks=tuple(json.loads(row["checks"])),
            begonnen=datetime.fromisoformat(row["begonnen"]),
            beendet=datetime.fromisoformat(row["beendet"]) if row["beendet"] else None,
            fehler=row["fehler"],
        )
