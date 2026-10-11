"""Volltexte verfallen, Urteile bleiben (Erik, 11.10.2026).

Die langen Texte der Checks sind irgendwann Schnee von gestern, die Entwicklung der Urteile
nicht. Darum bleiben Urteil und Satz in ``position_analyses`` für immer -- Urteilsband und
Urteils-Rückblick leben davon --, die Texte nur für die jüngsten ``BEHALTEN`` Urteile je Titel
und Check. Älter: Die Nachrichten der Sitzung werden gelöscht, die Sitzung selbst bleibt (das
Urteil verweist auf sie), ``analysis_text`` wird leer. Die Titelseite zeigt dann nur den Satz.

Nie gelöscht wird ein Dialog: eine Sitzung mit mehr als einer Nachricht von Erik (Nachfrage im
Storychecker oder Fundamental Analyzer). Was weg ist, liegt noch in der Sicherung.

Idempotent: Ein zweiter Lauf findet nichts mehr. Läuft im Job ``agenten`` (scripts/job.py).
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict

#: So viele Volltexte je Titel und Check bleiben lesbar (Erik, 11.10.2026).
BEHALTEN = 2

#: Je Check die Tabelle seiner Nachrichten.
NACHRICHTEN = {
    "storychecker": "storychecker_messages",
    "fundamental_analyzer": "fundamental_analyzer_messages",
    "consensus_gap": "consensus_gap_messages",
    "capital_allocator": "capital_allocator_messages",
    "devils_advocate": "devils_advocate_messages",
}


def verfallen_lassen(conn: sqlite3.Connection, behalten: int = BEHALTEN) -> int:
    """Löscht die Volltexte aller Urteile außer den jüngsten ``behalten`` je Titel und Check.
    Gibt zurück, wie viele Urteile dabei einen Text verloren haben."""
    platz = ",".join("?" * len(NACHRICHTEN))
    rows = conn.execute(
        f"SELECT id, position_id, agent, session_id, analysis_text FROM position_analyses "
        f"WHERE agent IN ({platz}) ORDER BY position_id, agent, created_at DESC, id DESC",
        tuple(NACHRICHTEN),
    ).fetchall()

    reihe: dict[tuple, list] = defaultdict(list)
    for r in rows:
        reihe[(r["position_id"], r["agent"])].append(r)

    verloren = 0
    for (_, agent), urteile in reihe.items():
        tabelle = NACHRICHTEN[agent]
        # Teilt sich ein altes Urteil die Sitzung mit einem jungen, bleibt sie.
        junge_sitzungen = {u["session_id"] for u in urteile[:behalten] if u["session_id"]}
        for u in urteile[behalten:]:
            weg = False
            sitzung = u["session_id"]
            if sitzung and sitzung not in junge_sitzungen and not _ist_dialog(conn, tabelle, sitzung):
                weg = conn.execute(f"DELETE FROM {tabelle} WHERE session_id = ?",
                                   (sitzung,)).rowcount > 0
            if u["analysis_text"]:
                conn.execute("UPDATE position_analyses SET analysis_text = NULL WHERE id = ?", (u["id"],))
                weg = True
            verloren += weg
    conn.commit()
    return verloren


def _ist_dialog(conn: sqlite3.Connection, tabelle: str, sitzung: int) -> bool:
    return conn.execute(f"SELECT COUNT(*) FROM {tabelle} WHERE session_id = ? AND role = 'user'",
                        (sitzung,)).fetchone()[0] > 1
