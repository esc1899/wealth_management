"""Wann ein Job der Seite "Scheduler" fällig ist (core.scheduler.ist_faellig) und was
der ops-core-Job `agenten` daraus macht (scripts/job.py), seit 02.10.2026.

Fällig heißt: Der letzte Termin ist vorbei, und seitdem lief der Job nicht. Das ist
idempotent — der stündliche Lauf darf beliebig oft kommen, ein ausgefallener Lauf wird
vom nächsten nachgeholt.

Datenbank: eine Datei unter tmp_path — der Dienst öffnet je Schritt eine eigene
Verbindung, :memory: wäre jedes Mal leer.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import job as skript  # noqa: E402
from core.scheduler import AgentSchedulerService, ist_faellig, letzte_feuerzeit  # noqa: E402
from core.storage.base import get_connection, init_db, migrate_db  # noqa: E402
from core.storage.models import ScheduledJob  # noqa: E402
from core.storage.scheduled_jobs import ScheduledJobsRepository  # noqa: E402


def _job(**kw):
    werte = dict(id=1, agent_name="news", skill_name="", skill_prompt="", frequency="monthly",
                 run_hour=8, run_minute=0, run_day=1, enabled=True)
    werte.update(kw)
    return ScheduledJob(**werte)


class TestLetzteFeuerzeit:
    def test_monatlich_vor_dem_termin_gilt_der_vormonat(self):
        assert letzte_feuerzeit(_job(), datetime(2026, 10, 1, 7, 0)) == datetime(2026, 9, 1, 8, 0)

    def test_monatlich_nach_dem_termin(self):
        assert letzte_feuerzeit(_job(), datetime(2026, 10, 2, 7, 0)) == datetime(2026, 10, 1, 8, 0)

    def test_monatlich_im_januar_vor_dem_termin_ist_dezember(self):
        assert letzte_feuerzeit(_job(), datetime(2027, 1, 1, 7, 0)) == datetime(2026, 12, 1, 8, 0)

    def test_monatlich_tag_31_im_kurzen_monat(self):
        assert letzte_feuerzeit(_job(run_day=31), datetime(2026, 9, 30, 9, 0)) == datetime(2026, 9, 30, 8, 0)

    def test_taeglich(self):
        j = _job(frequency="daily", run_hour=20)
        assert letzte_feuerzeit(j, datetime(2026, 10, 2, 19, 0)) == datetime(2026, 10, 1, 20, 0)
        assert letzte_feuerzeit(j, datetime(2026, 10, 2, 20, 0)) == datetime(2026, 10, 2, 20, 0)

    def test_woechentlich_montag(self):
        j = _job(frequency="weekly", run_weekday=0, run_hour=8)
        # 02.10.2026 ist ein Freitag, der Montag davor der 28.09.
        assert letzte_feuerzeit(j, datetime(2026, 10, 2, 12, 0)) == datetime(2026, 9, 28, 8, 0)
        # Montag vor 8 Uhr: der Montag der Vorwoche
        assert letzte_feuerzeit(j, datetime(2026, 9, 28, 7, 0)) == datetime(2026, 9, 21, 8, 0)

    def test_jaehrlich(self):
        j = _job(frequency="yearly", run_month=1, run_day=1, run_hour=6)
        assert letzte_feuerzeit(j, datetime(2026, 10, 2)) == datetime(2026, 1, 1, 6, 0)
        assert letzte_feuerzeit(j, datetime(2027, 1, 1, 5, 0)) == datetime(2026, 1, 1, 6, 0)

    def test_von_hand_hat_keinen_termin(self):
        assert letzte_feuerzeit(_job(frequency="manual"), datetime(2026, 10, 2)) is None


class TestIstFaellig:
    def test_am_ersten_nach_dem_termin_faellig(self):
        j = _job(last_run=datetime(2026, 9, 1, 8, 1))
        assert ist_faellig(j, datetime(2026, 10, 1, 9, 0)) is True

    def test_nach_dem_lauf_nicht_mehr(self):
        j = _job(last_run=datetime(2026, 10, 1, 8, 1))
        assert ist_faellig(j, datetime(2026, 10, 1, 10, 0)) is False

    def test_verpasst_wird_am_naechsten_tag_nachgeholt(self):
        """Der Mac war am 1. aus — am 2. beim Login ist der Monatsjob fällig."""
        j = _job(last_run=datetime(2026, 9, 1, 8, 1))
        assert ist_faellig(j, datetime(2026, 10, 2, 7, 20)) is True

    def test_nie_gelaufen_ist_faellig(self):
        assert ist_faellig(_job(last_run=None), datetime(2026, 10, 2)) is True

    def test_abgeschaltet_nie(self):
        assert ist_faellig(_job(enabled=False), datetime(2026, 10, 2)) is False

    def test_von_hand_nie(self):
        assert ist_faellig(_job(frequency="manual", last_run=None), datetime(2026, 10, 2)) is False


@pytest.fixture
def db(tmp_path):
    pfad = str(tmp_path / "jobs.db")
    conn = get_connection(pfad)
    init_db(conn)
    migrate_db(conn)
    yield pfad, ScheduledJobsRepository(conn)
    conn.close()


def _dienst(pfad):
    return AgentSchedulerService(
        db_path=pfad,
        encryption_key="test-key",
        anthropic_api_key="test-api",
        default_claude_model="claude-haiku-4-5-20251001",
    )


def _neu(repo, **kw):
    werte = dict(agent_name="news", skill_name="", skill_prompt="", frequency="monthly",
                 run_hour=8, run_minute=0, run_day=1)
    werte.update(kw)
    return repo.add(ScheduledJob(**werte))


def _lief_um(repo, job_id, lokal: datetime):
    """last_run so ablegen, wie SQLite es tut: UTC."""
    utc = lokal.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    repo._conn.execute("UPDATE scheduled_jobs SET last_run = ? WHERE id = ?", (utc, job_id))
    repo._conn.commit()


class TestLaufenLassen:
    def test_devils_advocate_laeuft_nie_eingeplant(self, db):
        # Die Watchlist prueft Erik auf Knopfdruck (2026-10-06); ein frueher
        # angelegter Job laeuft nicht mehr von selbst, auch wenn er faellig waere.
        pfad, repo = db
        _neu(repo, agent_name="devils_advocate")
        news = _neu(repo, agent_name="news")
        d = _dienst(pfad)
        d._execute_job = AsyncMock()
        gelaufen, fehl, _ = d.laufen_lassen(now=datetime(2026, 10, 1, 12, 0), aus=lambda _: None)
        assert (gelaufen, fehl) == (1, [])
        d._execute_job.assert_awaited_once_with(news.id)

    def test_laesst_nur_faellige_laufen(self, db):
        pfad, repo = db
        faellig = _neu(repo, agent_name="news")
        erledigt = _neu(repo, agent_name="storychecker")
        _neu(repo, agent_name="search_agent", frequency="manual")
        _lief_um(repo, faellig.id, datetime(2026, 9, 1, 8, 1))
        _lief_um(repo, erledigt.id, datetime(2026, 10, 1, 8, 1))

        d = _dienst(pfad)
        d._execute_job = AsyncMock()
        gelaufen, fehl, _ = d.laufen_lassen(now=datetime(2026, 10, 1, 12, 0), aus=lambda _: None)

        assert (gelaufen, fehl) == (1, [])
        d._execute_job.assert_awaited_once_with(faellig.id)

    def test_ein_fehler_haelt_die_anderen_nicht_auf(self, db):
        pfad, repo = db
        a = _neu(repo, agent_name="news")
        b = _neu(repo, agent_name="storychecker")

        d = _dienst(pfad)
        aufrufe = []

        async def ausfuehren(job_id):
            aufrufe.append(job_id)
            if job_id == a.id:
                raise RuntimeError("Guthaben aufgebraucht")

        d._execute_job = ausfuehren
        gelaufen, fehl, _ = d.laufen_lassen(now=datetime(2026, 10, 1, 12, 0), aus=lambda _: None)

        assert sorted(aufrufe) == sorted([a.id, b.id])
        assert gelaufen == 2 and fehl == [f"news (#{a.id})"]

    def test_neustart_am_selben_tag_holt_nicht_doppelt_nach(self, db):
        """last_run steht in UTC; bis 01.10.2026 wurde es mit Ortszeit verglichen, ein Lauf
        um 08:01 lag dann vor dem Termin 08:00 — und lief noch einmal."""
        pfad, repo = db
        j = _neu(repo)
        _lief_um(repo, j.id, datetime(2026, 10, 1, 8, 1))
        assert _dienst(pfad).faellige_jobs(now=datetime(2026, 10, 1, 12, 0)) == []

    def test_letzter_lauf_kommt_in_ortszeit_zurueck(self, db):
        pfad, repo = db
        j = _neu(repo)
        repo.update_last_run(j.id)
        assert abs((repo.get(j.id).last_run - datetime.now()).total_seconds()) < 60


class TestSkript:
    def test_nichts_faellig_ist_ein_guter_lauf(self, capsys):
        d = MagicMock()
        d.laufen_lassen.return_value = (0, [], [])
        assert skript.agenten(d, batch_api=False) == 0
        assert "Nichts fällig" in capsys.readouterr().out
        d.batches_abholen.assert_not_called()

    def test_ein_fehlschlag_macht_den_lauf_rot(self, capsys):
        d = MagicMock()
        d.laufen_lassen.return_value = (2, ["news (#8)"], [])
        assert skript.agenten(d, batch_api=False) == 1
        assert "news (#8)" in capsys.readouterr().out

    def test_batch_api_holt_die_batches_ab(self):
        d = MagicMock()
        d.laufen_lassen.return_value = (0, [], [])
        d.wartet.return_value = {"anzahl": 0, "seit": None, "was": []}
        skript.agenten(d, batch_api=True)
        d.batches_abholen.assert_called_once()

    def test_meldet_ins_run_log_worauf_es_wartet(self, capsys, tmp_path, monkeypatch):
        """02.10.2026: der Messwert wartet fuer die ops-core-Kachel, Form wie im
        Vertrag (heimnetzwerk docs/haus/vertraege/wartet.ndjson)."""
        import json
        (tmp_path / "runs").mkdir()
        monkeypatch.setenv("OPS_CORE_HOME", str(tmp_path))
        monkeypatch.setenv("OPS_RUN_ID", "01TEST")
        monkeypatch.setenv("OPS_JOB", "agenten")
        d = MagicMock()
        d.laufen_lassen.return_value = (0, [], [])
        d.batches_abholen.return_value = ["Batch Storychecker: läuft noch"]
        d.wartet.return_value = {"anzahl": 1, "seit": "2026-10-02T13:05:12+02:00", "was": ["Storychecker"]}
        assert skript.agenten(d, batch_api=True) == 0
        assert "Wartet auf Storychecker seit 13:05." in capsys.readouterr().out
        [zeile] = [json.loads(z) for f in (tmp_path / "runs").iterdir() for z in f.read_text().splitlines()]
        assert (zeile["kind"], zeile["job"], zeile["run_id"]) == ("metric", "agenten", "01TEST")
        assert zeile["payload"] == {"metric": "wartet", "anzahl": 1,
                                    "seit": "2026-10-02T13:05:12+02:00", "was": ["Storychecker"]}

    def test_kurse_nicht_faellig_ist_ein_guter_lauf(self, capsys):
        markt = MagicMock()
        markt.tagesabruf_wenn_faellig.return_value = False
        assert skript.kurse(markt, 18) == 0
        assert "Nicht fällig" in capsys.readouterr().out

    def test_die_app_startet_keinen_zeitplan(self):
        wurzel = Path(__file__).resolve().parents[2]
        for datei in ["state_agents.py", "app.py", "core/scheduler.py", "agents/market_data_agent.py"]:
            quelle = (wurzel / datei).read_text(encoding="utf-8")
            assert "from apscheduler" not in quelle and "import apscheduler" not in quelle, datei


class TestBremse:
    """Ein Job, der scheitert, setzt last_run nicht — er wäre eine Stunde später wieder
    fällig, 15-mal am Tag. Bricht er erst nach Modellaufrufen ab, kostet jeder Versuch.
    Nach drei gescheiterten Versuchen seit seinem letzten Termin wartet er auf den nächsten
    Termin; rot bleibt der Lauf trotzdem (02.10.2026)."""

    JETZT = datetime(2026, 10, 1, 12, 0)

    @staticmethod
    def _gescheitert(repo, job_id, lokal: datetime, source="scheduled"):
        from core.storage.scheduled_jobs import ScheduledJobRunsRepository
        runs = ScheduledJobRunsRepository(repo._conn)
        run = runs.create(job_id, source=source)
        runs.fail(run.id, "abgebrochen")
        repo._conn.execute("UPDATE scheduled_job_runs SET started_at = ? WHERE id = ?",
                           (lokal.astimezone(timezone.utc).isoformat(), run.id))
        repo._conn.commit()

    def _laufen(self, pfad):
        d = _dienst(pfad)
        d._execute_job = AsyncMock()
        return d, d.laufen_lassen(now=self.JETZT, aus=lambda _: None)

    def test_nach_drei_fehlversuchen_wartet_er(self, db):
        pfad, repo = db
        j = _neu(repo)
        for stunde in (8, 9, 10):
            self._gescheitert(repo, j.id, datetime(2026, 10, 1, stunde, 5))
        d, (gelaufen, fehl, gebremst) = self._laufen(pfad)
        d._execute_job.assert_not_awaited()
        assert gelaufen == 0 and gebremst == [f"news (#{j.id})"]

    def test_nach_zwei_fehlversuchen_noch_einmal(self, db):
        pfad, repo = db
        j = _neu(repo)
        for stunde in (8, 9):
            self._gescheitert(repo, j.id, datetime(2026, 10, 1, stunde, 5))
        d, (gelaufen, _, gebremst) = self._laufen(pfad)
        assert gelaufen == 1 and gebremst == []

    def test_fehlversuche_vor_dem_termin_zaehlen_nicht(self, db):
        """Der September ist erledigt — am 1. Oktober beginnt der Zähler neu."""
        pfad, repo = db
        j = _neu(repo)
        for tag in (1, 2, 3):
            self._gescheitert(repo, j.id, datetime(2026, 9, tag, 9, 5))
        d, (gelaufen, _, gebremst) = self._laufen(pfad)
        assert gelaufen == 1 and gebremst == []

    def test_jetzt_ausfuehren_zaehlt_nicht(self, db):
        """Wer auf der Seite von Hand probiert, bremst den geplanten Lauf nicht."""
        pfad, repo = db
        j = _neu(repo)
        for stunde in (8, 9, 10):
            self._gescheitert(repo, j.id, datetime(2026, 10, 1, stunde, 5), source="manual")
        d, (gelaufen, _, gebremst) = self._laufen(pfad)
        assert gelaufen == 1 and gebremst == []

    def test_gebremst_bleibt_der_lauf_rot(self, capsys):
        d = MagicMock()
        d.laufen_lassen.return_value = (0, [], ["news (#8)"])
        assert skript.agenten(d, batch_api=False) == 1
        assert "news (#8)" in capsys.readouterr().out
