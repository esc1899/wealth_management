"""Der Planer (scripts/planer_dienst.py): die Zeitpläne laufen ab dem Login in einem
eigenen Prozess, nicht erst, wenn jemand die Seite öffnet (01.10.2026).

Datenbank: eine Datei unter tmp_path — sync_jobs() öffnet je Abgleich eine eigene
Verbindung, :memory: wäre jedes Mal leer.
"""

import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import planer_dienst as p  # noqa: E402
from core.scheduler import AgentSchedulerService  # noqa: E402
from core.storage.base import get_connection, init_db, migrate_db  # noqa: E402
from core.storage.models import ScheduledJob  # noqa: E402
from core.storage.scheduled_jobs import ScheduledJobsRepository  # noqa: E402


@pytest.fixture
def db(tmp_path):
    pfad = str(tmp_path / "planer.db")
    conn = get_connection(pfad)
    init_db(conn)
    migrate_db(conn)
    yield pfad, ScheduledJobsRepository(conn)
    conn.close()


def _service(pfad):
    return AgentSchedulerService(
        db_path=pfad,
        encryption_key="test-key",
        anthropic_api_key="test-api",
        default_claude_model="claude-haiku-4-5-20251001",
    )


def _job(**kw):
    werte = dict(agent_name="news", skill_name="", skill_prompt="", frequency="monthly",
                 run_hour=8, run_minute=0, run_day=1)
    werte.update(kw)
    return ScheduledJob(**werte)


def _agenten_jobs(service):
    return [j for j in service._scheduler.get_jobs() if j.id.startswith("agent_job_")]


class TestAbgleich:
    def test_erster_abgleich_laedt_die_jobs(self, db):
        pfad, repo = db
        repo.add(_job())
        s = _service(pfad)
        assert s.sync_jobs() is True
        assert len(_agenten_jobs(s)) == 1

    def test_ohne_aenderung_wird_nicht_neu_geladen(self, db):
        pfad, repo = db
        repo.add(_job())
        s = _service(pfad)
        s.sync_jobs()
        assert s.sync_jobs() is False

    def test_ein_eigener_lauf_ist_keine_aenderung(self, db):
        """last_run ändert sich bei jedem Lauf — ein Neuladen genau zur Feuerzeit
        könnte den Lauf verschlucken."""
        pfad, repo = db
        job = repo.add(_job())
        s = _service(pfad)
        s.sync_jobs()
        repo.update_last_run(job.id)
        assert s.sync_jobs() is False

    def test_abschalten_auf_der_seite_kommt_an(self, db):
        pfad, repo = db
        job = repo.add(_job())
        s = _service(pfad)
        s.sync_jobs()
        repo.set_enabled(job.id, False)
        assert s.sync_jobs() is True
        assert _agenten_jobs(s) == []

    def test_neuer_job_auf_der_seite_kommt_an(self, db):
        pfad, repo = db
        s = _service(pfad)
        s.sync_jobs()
        repo.add(_job(frequency="weekly", run_weekday=0, run_hour=20))
        assert s.sync_jobs() is True
        assert len(_agenten_jobs(s)) == 1


class TestAppStartetNichts:
    def test_reload_jobs_ohne_start_tut_nichts(self, db):
        """Die App hält eine ungestartete Instanz nur für "Jetzt ausführen"; ihr
        reload_jobs() nach einer Änderung auf der Seite darf keinen Zeitplan aufbauen."""
        pfad, repo = db
        repo.add(_job())
        s = _service(pfad)
        s.reload_jobs()
        assert _agenten_jobs(s) == []
        assert s._scheduler.running is False

    def test_die_app_startet_keinen_zeitplan(self):
        quelle = (Path(__file__).resolve().parents[2] / "state_agents.py").read_text(encoding="utf-8")
        assert "service.start()" not in quelle
        assert "setup_scheduler" not in quelle
        assert "catchup_fetch_if_missed" not in quelle


class TestLaufen:
    def test_startet_beide_holt_nach_und_gleicht_ab_bis_zum_ende(self):
        agenten, markt, kurse = MagicMock(), MagicMock(), MagicMock()
        markt.setup_scheduler.return_value = kurse
        ende = threading.Event()
        agenten.sync_jobs.side_effect = lambda: ende.set()

        p.laufen(agenten, markt, 18, ende, pruefen_alle=0.01)

        markt.setup_scheduler.assert_called_once_with(fetch_hour=18)
        kurse.start.assert_called_once()
        markt.catchup_fetch_if_missed.assert_called_once_with(fetch_hour=18)
        agenten.start.assert_called_once()
        agenten.sync_jobs.assert_called_once()
        kurse.shutdown.assert_called_once()
        agenten.shutdown.assert_called_once()

    def test_ein_fehler_beim_abgleich_beendet_den_planer_nicht(self):
        agenten, markt = MagicMock(), MagicMock()
        ende = threading.Event()
        aufrufe = []

        def abgleich():
            aufrufe.append(1)
            if len(aufrufe) == 1:
                raise RuntimeError("Datenbank gesperrt")
            ende.set()

        agenten.sync_jobs.side_effect = abgleich
        p.laufen(agenten, markt, 18, ende, pruefen_alle=0.01)
        assert len(aufrufe) == 2


class TestLetzterLaufInOrtszeit:
    """SQLite schreibt `datetime('now')` in UTC, das Nachholen rechnet in Ortszeit. Bis zum
    01.10.2026 wurde beides ohne Umrechnung verglichen: Ein Monatsjob, der um 08:00 gelaufen
    war, stand mit 06:00 da — ein Neustart des Planers am selben Tag hätte ihn noch einmal
    ausgeführt, und die Seite "Scheduler" zeigte den Lauf zwei Stunden zu früh."""

    def test_letzter_lauf_kommt_in_ortszeit_zurueck(self, db):
        pfad, repo = db
        job = repo.add(_job())
        repo.update_last_run(job.id)
        abstand = abs((repo.get(job.id).last_run - datetime.now()).total_seconds())
        assert abstand < 60

    @pytest.mark.asyncio
    async def test_neustart_am_selben_tag_holt_nicht_doppelt_nach(self, db):
        pfad, repo = db
        job = repo.add(_job(run_hour=8, run_minute=0, run_day=1))
        gelaufen_lokal = datetime(2026, 10, 1, 8, 1)
        gelaufen_utc = gelaufen_lokal.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        repo._conn.execute("UPDATE scheduled_jobs SET last_run = ? WHERE id = ?", (gelaufen_utc, job.id))
        repo._conn.commit()

        s = _service(pfad)
        s._execute_job = AsyncMock()
        await s._catchup_missed_jobs(now=datetime(2026, 10, 1, 12, 0))
        s._execute_job.assert_not_called()
