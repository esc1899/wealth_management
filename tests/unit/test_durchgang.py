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


# ------------------------------------------------------------------
# Schritt 2: ein Job je Liste
# ------------------------------------------------------------------

import asyncio
from datetime import timedelta, timezone

from core.pruefung import JOB, jobs_umstellen, skill_fuer, skills
from core.portfolio_check import urteilszeilen
from core.scheduler import AgentSchedulerService
from core.storage.base import build_encryption_service
from core.storage.batch_queue import BatchQueueRepository
from core.storage.models import ScheduledJob, Skill
from core.storage.positions import PositionsRepository
from core.storage.scheduled_jobs import ScheduledJobsRepository
from core.storage.skills import SkillsRepository


def _job(repo, agent, **kw):
    werte = dict(agent_name=agent, skill_name="", skill_prompt="", frequency="monthly",
                 run_hour=8, run_minute=0, run_day=1)
    werte.update(kw)
    return repo.add(ScheduledJob(**werte))


class TestJobsUmstellen:
    def test_takt_des_storycheckers_alte_aus_skills_uebernommen(self, conn):
        jobs, cfg = ScheduledJobsRepository(conn), AppConfigRepository(conn)
        _job(jobs, "storychecker", frequency="weekly", run_weekday=0, run_hour=7, run_minute=30)
        _job(jobs, "fundamental_analyzer", skill_name="Tiefenpruefung")
        news = _job(jobs, "news")

        assert jobs_umstellen(jobs, cfg) is True
        alle = {j.agent_name: j for j in jobs.get_all()}
        depot, wl = alle[JOB["depot"]], alle[JOB["watchlist"]]
        assert (depot.frequency, depot.run_weekday, depot.run_hour, depot.run_minute) == ("weekly", 0, 7, 30)
        assert depot.enabled and not wl.enabled
        assert not alle["storychecker"].enabled and not alle["fundamental_analyzer"].enabled
        assert alle["news"].enabled and news.id == alle["news"].id
        assert skills(cfg, "depot") == {"fundamental_analyzer": "Tiefenpruefung"}
        assert skills(cfg, "watchlist") == {"fundamental_analyzer": "Tiefenpruefung"}

        # Ein zweites Mal aendert nichts -- auch nicht, wenn Erik einen alten Job wieder anschaltet.
        jobs.set_enabled(alle["storychecker"].id, True)
        assert jobs_umstellen(jobs, cfg) is False
        assert len(jobs.get_all()) == 5
        assert jobs.get(alle["storychecker"].id).enabled

    def test_ohne_storychecker_monatlich(self, conn):
        jobs, cfg = ScheduledJobsRepository(conn), AppConfigRepository(conn)
        jobs_umstellen(jobs, cfg)
        depot = next(j for j in jobs.get_all() if j.agent_name == JOB["depot"])
        assert (depot.frequency, depot.run_day, depot.run_hour, depot.enabled) == ("monthly", 1, 6, True)


def test_skill_fuer(conn):
    cfg, sk = AppConfigRepository(conn), SkillsRepository(conn)
    sk.add(Skill(name="Moat", area="consensus_gap", prompt="Achte auf den Burggraben."))
    cfg.set_json("pruefung_skills_depot", {"consensus_gap": "Moat", "fundamental_analyzer": "fehlt"})
    assert skill_fuer(cfg, sk, "depot", "consensus_gap") == ("Moat", "Achte auf den Burggraben.")
    assert skill_fuer(cfg, sk, "depot", "fundamental_analyzer") == ("Standard", "")
    assert skill_fuer(cfg, sk, "watchlist", "consensus_gap") == ("Standard", "")


def test_urteilszeilen_lesen_alle_gewaehlten_checks():
    p = SimpleNamespace(id=1, name="Munich Re", ticker="MUV2.DE")
    u = SimpleNamespace(verdict="fair", summary="Preis passt.")
    text = urteilszeilen([p], {"fundamental_analyzer": {1: u}}, ("storychecker", "fundamental_analyzer"))
    assert "- Munich Re (MUV2.DE)" in text
    assert "  - storychecker: noch nicht geprüft" in text
    assert "  - fundamental_analyzer: fair — Preis passt." in text


# --- Scheduler mit einer Datenbank im Testordner -----------------------------

@pytest.fixture
def dienst(tmp_path):
    pfad = str(tmp_path / "wm.db")
    c = get_connection(pfad)
    init_db(c)
    migrate_db(c)
    d = AgentSchedulerService(db_path=pfad, encryption_key="test-key", anthropic_api_key="k",
                              default_claude_model="claude-haiku-4-5-20251001")
    # Derselbe Schluessel wie der Dienst, aus seinem eigenen Pfad im Testordner.
    yield d, c, build_encryption_service("test-key", d._salt_path)
    c.close()


def _titel(enc, c, name, **kw):
    return PositionsRepository(c, enc).add(Position(
        asset_class="Aktie", investment_type="Wertpapiere", name=name, ticker=name[:3].upper(),
        unit="Stück", added_date=date(2026, 1, 1), story="These", **kw))


class TestNachziehen:
    def test_wartet_auf_den_batch_seiner_checks(self, dienst):
        d, c, _ = dienst
        repo = DurchgaengeRepository(c)
        did = repo.beginnen("depot", 1, "job", ["storychecker"])
        BatchQueueRepository(c).create("b1", "storychecker", None, "de", 1)
        aufrufe = []

        async def portfolio(conn):
            aufrufe.append("pc")
            return "Portfolio Checker: ok"
        d._portfolio_check_lauf = portfolio

        assert asyncio.run(d._nachziehen(c)) == []
        assert repo.get(did).beendet is None
        BatchQueueRepository(c).mark_done("b1", 1, 0)
        zeilen = asyncio.run(d._nachziehen(c))
        assert repo.get(did).beendet is not None and aufrufe == ["pc"]
        assert any("1 Durchgänge fertig" in z for z in zeilen)

    def test_schluss_stufe_einmal_je_liste_und_ihr_fehler_bleibt(self, dienst):
        d, c, _ = dienst
        repo = DurchgaengeRepository(c)
        ids = [repo.beginnen("watchlist", p, "job", ["storychecker", "watchlist_checker"]) for p in (1, 2)]
        gesehen = []

        async def wc(conn, position_ids):
            gesehen.append(sorted(position_ids))
            raise RuntimeError("Ollama nicht erreichbar")
        d._watchlist_checker_lauf = wc

        asyncio.run(d._nachziehen(c))
        assert gesehen == [[1, 2]]
        assert all("Ollama nicht erreichbar" in repo.get(i).fehler for i in ids)
        assert all(repo.get(i).beendet for i in ids)

    def test_verwaister_knopf_durchgang(self, dienst):
        d, c, _ = dienst
        repo = DurchgaengeRepository(c)
        alt = repo.beginnen("depot", 1, "knopf", ["storychecker"])
        neu = repo.beginnen("depot", 2, "knopf", ["storychecker"])
        c.execute("UPDATE durchgaenge SET begonnen = ? WHERE id = ?",
                  ((datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(), alt))
        c.commit()
        asyncio.run(d._nachziehen(c))
        assert repo.get(alt).fehler == "Abgebrochen (App beendet)"
        assert repo.get(neu).beendet is None


class TestPruefungsJob:
    def _vorbereiten(self, d, c, enc, scheitern=()):
        a = _titel(enc, c, "Alpha", in_portfolio=True)
        b = _titel(enc, c, "Beta", in_portfolio=True)
        _titel(enc, c, "Gamma", in_watchlist=True)
        AppConfigRepository(c).set_json("pruefung_auswahl_depot", ["storychecker", "capital_allocator"])
        laeufe = []

        def fake(check):
            async def lauf(job, conn, log, positionen=None):
                laeufe.append((check, job.agent_name, sorted(p.name for p in positionen)))
                if check in scheitern:
                    raise RuntimeError(f"{check} kaputt")
            return lauf
        for check, methode in d._CHECK_LAEUFE.items():
            setattr(d, methode, fake(check))

        async def portfolio(conn):
            return "Portfolio Checker: ok"
        d._portfolio_check_lauf = portfolio
        return a, b, laeufe

    def _job(self):
        return ScheduledJob(agent_name="pruefung_depot", skill_name="", skill_prompt="", frequency="monthly")

    def test_live_alle_titel_je_titel_ein_durchgang(self, dienst):
        d, c, enc = dienst
        a, b, laeufe = self._vorbereiten(d, c, enc)
        asyncio.run(d._run_pruefung_job(self._job(), c, lambda _: None, "depot"))
        assert laeufe == [("storychecker", "storychecker", ["Alpha", "Beta"]),
                          ("capital_allocator", "capital_allocator", ["Alpha", "Beta"])]
        ds = DurchgaengeRepository(c)
        for p in (a, b):
            [x] = ds.fuer_titel(p.id)
            assert x.beendet and x.ausloeser == "job" and x.fehler is None

    def test_ein_check_scheitert_der_job_bleibt_gruen(self, dienst):
        d, c, enc = dienst
        a, _, _ = self._vorbereiten(d, c, enc, scheitern=("capital_allocator",))
        asyncio.run(d._run_pruefung_job(self._job(), c, lambda _: None, "depot"))
        [durchgang] = DurchgaengeRepository(c).fuer_titel(a.id)
        assert "capital_allocator kaputt" in durchgang.fehler

    def test_alle_checks_scheitern_der_job_ist_rot(self, dienst):
        d, c, enc = dienst
        self._vorbereiten(d, c, enc, scheitern=("storychecker", "capital_allocator"))
        with pytest.raises(RuntimeError):
            asyncio.run(d._run_pruefung_job(self._job(), c, lambda _: None, "depot"))


def test_ca_batch_antwort_wird_urteil(dienst):
    d, c, enc = dienst
    a = _titel(enc, c, "Alpha", in_portfolio=True)
    block = SimpleNamespace(type="tool_use", name="submit_ca_verdict",
                            input={"position_id": a.id, "verdict": "solide", "summary": "Ordentlich.",
                                   "analysis": "Rueckkaeufe guenstig."})
    result = SimpleNamespace(custom_id=f"ca_{a.id}",
                             result=SimpleNamespace(message=SimpleNamespace(content=[block])))
    assert d._process_ca_result(result, "Standard", c) is True
    [u] = PositionAnalysesRepository(c).get_for_position(a.id)
    assert (u.agent, u.verdict, u.summary) == ("capital_allocator", "solide", "Ordentlich.")
    falsch = SimpleNamespace(custom_id="ca_x", result=result.result)
    assert d._process_ca_result(falsch, "Standard", c) is False


def test_batch_antwort_ohne_gelungene_suche_wird_kein_urteil(dienst):
    d, c, enc = dienst
    a = _titel(enc, c, "Alpha", in_portfolio=True)
    fehler = SimpleNamespace(type="web_search_tool_result",
                             content=SimpleNamespace(error_code="too_many_requests"))
    block = SimpleNamespace(type="tool_use", name="submit_ca_verdict",
                            input={"position_id": a.id, "verdict": "solide", "summary": "Ohne Beleg."})
    message = SimpleNamespace(content=[fehler, block], model="claude-sonnet-5-5",
                              usage=SimpleNamespace(input_tokens=1, output_tokens=1))
    result = SimpleNamespace(custom_id=f"ca_{a.id}",
                             result=SimpleNamespace(type="succeeded", message=message))
    assert d._process_batch_results("capital_allocator", "Standard", [result], c) == (0, 1)
    assert PositionAnalysesRepository(c).get_for_position(a.id) == []


# ------------------------------------------------------------------
# Ein Cloud-Modell je Bereich
# ------------------------------------------------------------------

from core.pruefung import modell, modell_setzen


def test_modell_je_bereich_rueckfall_und_mitschreiben(conn):
    cfg = AppConfigRepository(conn)
    cfg.set("model_public_storychecker", "claude-sonnet-5-5")
    assert modell(cfg, "depot") == "claude-sonnet-5-5"        # bisheriger Eintrag
    assert modell(cfg, "watchlist") == ""                     # Standard der App
    modell_setzen(cfg, "research", "claude-opus-5-5")
    modell_setzen(cfg, "watchlist", "claude-haiku-5-5")
    assert cfg.get("model_public_research") == "claude-opus-5-5"
    assert cfg.get("model_public_structural_scan") == "claude-opus-5-5"
    assert cfg.get("model_public_devils_advocate") == "claude-haiku-5-5"
    assert cfg.get("model_public_storychecker") == "claude-sonnet-5-5"   # Depot unberuehrt


def test_knopf_reicht_modell_der_liste_weiter(tmp_path, monkeypatch):
    pfad = str(tmp_path / "m.db")
    c = get_connection(pfad)
    init_db(c)
    migrate_db(c)
    AppConfigRepository(c).set("model_bereich_watchlist", "claude-haiku-5-5")
    c.close()
    gesehen = {}

    def lauf(positions, language, job, db_path, enc_key, api_key):
        gesehen["modell"] = job.get("modell")
        job.update({"running": False, "error": None})

    monkeypatch.setattr(bj, "CHECK_JOBS", {"fundamental_analyzer": lauf})
    bj.run_durchgang(SimpleNamespace(id=1, name="X"), "watchlist", ("fundamental_analyzer",),
                     "de", {"running": True}, pfad, "", "")
    assert gesehen["modell"] == "claude-haiku-5-5"
    assert bj._resolve_model_from_conn(None, "fundamental_analyzer", "x", {"modell": "m"}) == "m"


def test_job_reicht_modell_der_liste_weiter(dienst):
    d, c, enc = dienst
    _titel(enc, c, "Alpha", in_portfolio=True)
    AppConfigRepository(c).set("model_bereich_depot", "claude-opus-5-5")
    AppConfigRepository(c).set_json("pruefung_auswahl_depot", ["storychecker"])
    modelle = []

    async def lauf(job, conn, log, positionen=None):
        modelle.append(job.model)
    d._run_storychecker_job = lauf

    async def portfolio(conn):
        return ""
    d._portfolio_check_lauf = portfolio
    job = ScheduledJob(agent_name="pruefung_depot", skill_name="", skill_prompt="", frequency="monthly")
    asyncio.run(d._run_pruefung_job(job, c, lambda _: None, "depot"))
    assert modelle == ["claude-opus-5-5"]
