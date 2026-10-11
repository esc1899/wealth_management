"""Der Durchgang: welche Checks je Liste gewählt sind, wie ein Durchgang seine Urteile
zuordnet und in welcher Reihenfolge die Checks laufen (core/pruefung.py,
core/storage/durchgaenge.py, core/background_jobs.py::run_durchgang)."""

from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime
from types import SimpleNamespace

import pytest

import core.background_jobs as bj
from core.kacheln import kachel
from core.pruefung import MOEGLICH, auswahl, auswahl_setzen, depot_kontext, reihenfolge
from core.storage.analyses import PositionAnalysesRepository
from core.storage.app_config import AppConfigRepository
from core.storage.base import get_connection, init_db, migrate_db
from core.storage.durchgaenge import DurchgaengeRepository
from core.storage.models import Position, PositionAnalysis


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    migrate_db(c)
    yield c
    c.close()


# ------------------------------------------------------------------
# Auswahl je Liste
# ------------------------------------------------------------------

class TestAuswahl:
    def test_ohne_einstellung_alles_moegliche(self, conn):
        cfg = AppConfigRepository(conn)
        assert auswahl(cfg, "depot") == MOEGLICH["depot"]
        assert auswahl(cfg, "watchlist") == MOEGLICH["watchlist"]

    def test_devils_advocate_nur_auf_der_watchlist(self):
        assert "devils_advocate" not in MOEGLICH["depot"]
        assert "devils_advocate" in MOEGLICH["watchlist"]

    def test_feste_reihenfolge_und_nur_moegliches(self, conn):
        cfg = AppConfigRepository(conn)
        gespeichert = auswahl_setzen(cfg, "depot", ["capital_allocator", "devils_advocate", "storychecker"])
        assert gespeichert == ("storychecker", "capital_allocator")
        assert auswahl(cfg, "depot") == ("storychecker", "capital_allocator")
        assert auswahl(cfg, "watchlist") == MOEGLICH["watchlist"]

    def test_leere_auswahl_bleibt_leer(self, conn):
        cfg = AppConfigRepository(conn)
        auswahl_setzen(cfg, "watchlist", [])
        assert auswahl(cfg, "watchlist") == ()

    def test_unbekannter_name_faellt_weg(self, conn):
        cfg = AppConfigRepository(conn)
        cfg.set_json("pruefung_auswahl_depot", ["storychecker", "gibt_es_nicht"])
        assert auswahl(cfg, "depot") == ("storychecker",)

    def test_watchlist_checker_zuletzt(self):
        zuerst, danach = reihenfolge(MOEGLICH["watchlist"])
        assert "watchlist_checker" not in zuerst
        assert danach == ("watchlist_checker",)
        assert reihenfolge(MOEGLICH["depot"])[1] == ()


def test_depot_kontext():
    portfolio = [SimpleNamespace(asset_class="Aktie")] * 3 + [SimpleNamespace(asset_class="Gold")]
    snapshot, story = depot_kontext(portfolio)
    assert "- Aktie: 3 Positionen (75%)" in snapshot
    assert story is None
    analyse = SimpleNamespace(verdict="v", summary="s", perf_verdict="p", perf_summary="ps",
                              stability_verdict="st", stability_summary="sts", full_text="voll")
    _, story = depot_kontext([], analyse, leer="leer")
    assert "Story: v" in story and "voll" in story


# ------------------------------------------------------------------
# Durchgang in der Datenbank
# ------------------------------------------------------------------

class TestDurchgaenge:
    def test_migration_legt_tabelle_und_spalte_an_und_ist_wiederholbar(self, conn):
        migrate_db(conn)
        spalten = {r[1] for r in conn.execute("PRAGMA table_info(position_analyses)")}
        assert "durchgang_id" in spalten
        assert conn.execute("SELECT COUNT(*) FROM durchgaenge").fetchone()[0] == 0

    def test_abschluss_ordnet_nur_passende_urteile_zu(self, conn):
        analysen = PositionAnalysesRepository(conn)
        vorher = analysen.save(1, "storychecker", "s", "intact", "alt")
        repo = DurchgaengeRepository(conn)
        did = repo.beginnen("depot", 1, "knopf", ["storychecker", "fundamental_analyzer"])
        time.sleep(0.001)
        passt = analysen.save(1, "storychecker", "s", "intact", "neu")
        auch = analysen.save(1, "fundamental_analyzer", "s", "fair", "neu")
        fremder_check = analysen.save(1, "devils_advocate", "s", "x", "nicht gewaehlt")
        fremder_titel = analysen.save(2, "storychecker", "s", "intact", "anderer Titel")

        assert repo.abschliessen(did) == 2
        zuordnung = dict(conn.execute("SELECT id, durchgang_id FROM position_analyses").fetchall())
        assert zuordnung[passt.id] == did and zuordnung[auch.id] == did
        assert zuordnung[vorher.id] is None
        assert zuordnung[fremder_check.id] is None
        assert zuordnung[fremder_titel.id] is None

        d = repo.get(did)
        assert d.beendet is not None and d.fehler is None
        assert d.checks == ("storychecker", "fundamental_analyzer")
        # Ein zweiter Abschluss aendert nichts.
        assert repo.abschliessen(did) == 0

    def test_fuer_titel_juengster_zuerst(self, conn):
        repo = DurchgaengeRepository(conn)
        a = repo.beginnen("watchlist", 7, "knopf", ["storychecker"])
        time.sleep(0.001)
        b = repo.beginnen("watchlist", 7, "job", ["storychecker"])
        assert [d.id for d in repo.fuer_titel(7)] == [b, a]


# ------------------------------------------------------------------
# Der Lauf
# ------------------------------------------------------------------

def test_run_durchgang_reihenfolge_fehler_und_abschluss(tmp_path, monkeypatch):
    pfad = str(tmp_path / "test.db")
    reihe: list[str] = []

    def fake(agent, fehler=None, warten=0.0):
        def lauf(positions, language, job, db_path, enc_key, api_key):
            time.sleep(warten)
            c = get_connection(db_path)
            PositionAnalysesRepository(c).save(positions[0].id, agent, "s", "v", "satz")
            c.close()
            reihe.append(agent)
            job.update({"running": False, "done": True, "count": 1, "error": fehler})
        return lauf

    monkeypatch.setattr(bj, "CHECK_JOBS", {
        "storychecker": fake("storychecker", warten=0.05),
        "devils_advocate": fake("devils_advocate", fehler="DA kaputt"),
        "watchlist_checker": fake("watchlist_checker"),
    })
    zustand = {"running": True}
    position = SimpleNamespace(id=3, name="Hermès")
    bj.run_durchgang(position, "watchlist", ("watchlist_checker", "devils_advocate", "storychecker"),
                     "de", zustand, pfad, "", "")

    assert reihe[-1] == "watchlist_checker"           # liest die Urteile der anderen
    assert zustand["running"] is False
    assert zustand["fehler"] == ["DA kaputt"]
    c = get_connection(pfad)
    d = DurchgaengeRepository(c).get(zustand["durchgang_id"])
    assert d.beendet is not None and d.fehler == "DA kaputt"
    # Auch das Urteil eines Checks, der einen Fehler meldet, gehoert zum Durchgang.
    assert c.execute("SELECT COUNT(*) FROM position_analyses WHERE durchgang_id = ?",
                     (d.id,)).fetchone()[0] == 3
    c.close()


# ------------------------------------------------------------------
# Die Kachel zeigt genau die Auswahl
# ------------------------------------------------------------------

def test_kachel_nennt_gewaehlte_checks_ohne_urteil():
    pos = Position(id=1, name="Munich Re", ticker="MUV2.DE", asset_class="Aktie",
                   investment_type="Wertpapiere", unit="Stück", added_date=date(2026, 1, 1),
                   in_portfolio=True)
    urteil = PositionAnalysis(position_id=1, agent="storychecker", skill_name="s", verdict="intact",
                              summary="These hält.", created_at=datetime(2026, 10, 1, 8, 0))
    k = kachel(pos, "depot", None, {"storychecker": urteil, "consensus_gap": urteil.model_copy(
        update={"agent": "consensus_gap"})}, agenten=("storychecker", "fundamental_analyzer"))
    assert [u.agent for u in k.urteile] == ["storychecker"]   # nicht gewaehlt: weg
    assert k.nie == ["fundamental_analyzer"]
