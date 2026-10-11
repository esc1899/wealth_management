"""Volltexte verfallen, Urteile bleiben (core/storage/volltexte.py)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from core.storage.base import init_db, migrate_db
from core.storage.volltexte import verfallen_lassen


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    migrate_db(c)
    yield c
    c.close()


_T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _urteil(c, position, agent, tag, *, nachfragen=0, text=None):
    """Ein Urteil mit Sitzung: eine Frage, eine Antwort, dazu ``nachfragen`` Rueckfragen."""
    tabelle = {"storychecker": "storychecker", "fundamental_analyzer": "fundamental_analyzer"}[agent]
    zeit = (_T0 + timedelta(days=tag)).isoformat()
    spalten = "position_id, ticker, position_name, skill_name, created_at"
    werte = [position, "T", "Titel", "s", zeit]
    if agent == "storychecker":
        spalten += ", skill_prompt"
        werte.append("")
    sitzung = c.execute(f"INSERT INTO {tabelle}_sessions ({spalten}) VALUES ({','.join('?' * len(werte))})",
                        werte).lastrowid
    for rolle in ["user", "assistant"] + ["user", "assistant"] * nachfragen:
        c.execute(f"INSERT INTO {tabelle}_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                  (sitzung, rolle, f"Text {tag}", zeit))
    uid = c.execute(
        "INSERT INTO position_analyses (position_id, agent, skill_name, verdict, summary, session_id, "
        "analysis_text, created_at) VALUES (?, ?, 's', 'intact', ?, ?, ?, ?)",
        (position, agent, f"Satz {tag}", sitzung, text, zeit)).lastrowid
    c.commit()
    return uid, sitzung


def _nachrichten(c, tabelle, sitzung):
    return c.execute(f"SELECT COUNT(*) FROM {tabelle}_messages WHERE session_id = ?", (sitzung,)).fetchone()[0]


def test_die_juengsten_zwei_bleiben_aeltere_verlieren_den_text(conn):
    alt = _urteil(conn, 1, "storychecker", 1, text="voll")
    mitte = _urteil(conn, 1, "storychecker", 2)
    neu = _urteil(conn, 1, "storychecker", 3)
    anderer_check = _urteil(conn, 1, "fundamental_analyzer", 0)
    anderer_titel = _urteil(conn, 2, "storychecker", 0)

    assert verfallen_lassen(conn) == 1
    assert _nachrichten(conn, "storychecker", alt[1]) == 0
    assert _nachrichten(conn, "storychecker", mitte[1]) == 2
    assert _nachrichten(conn, "storychecker", neu[1]) == 2
    assert _nachrichten(conn, "fundamental_analyzer", anderer_check[1]) == 2
    assert _nachrichten(conn, "storychecker", anderer_titel[1]) == 2
    # Urteil, Satz und Sitzung bleiben; nur der Text ist weg.
    zeile = conn.execute("SELECT verdict, summary, session_id, analysis_text FROM position_analyses "
                         "WHERE id = ?", (alt[0],)).fetchone()
    assert tuple(zeile) == ("intact", "Satz 1", alt[1], None)
    assert conn.execute("SELECT COUNT(*) FROM storychecker_sessions WHERE id = ?", (alt[1],)).fetchone()[0] == 1


def test_ein_dialog_bleibt(conn):
    dialog = _urteil(conn, 1, "fundamental_analyzer", 1, nachfragen=1)
    _urteil(conn, 1, "fundamental_analyzer", 2)
    _urteil(conn, 1, "fundamental_analyzer", 3)
    assert verfallen_lassen(conn) == 0
    assert _nachrichten(conn, "fundamental_analyzer", dialog[1]) == 4


def test_ein_zweiter_lauf_findet_nichts(conn):
    for tag in range(5):
        _urteil(conn, 1, "storychecker", tag, text="voll")
    assert verfallen_lassen(conn) == 3
    assert verfallen_lassen(conn) == 0
