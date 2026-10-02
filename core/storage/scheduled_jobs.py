"""
ScheduledJobsRepository + ScheduledJobRunsRepository — CRUD for scheduler tables.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from core.storage.models import ScheduledJob, ScheduledJobRun


def _ortszeit(wert: Optional[str]) -> Optional[datetime]:
    """SQLite schreibt `datetime('now')` in UTC; Zeitplan, Nachholen und Seite rechnen in
    Ortszeit (naiv). Ohne Umrechnung lag ein Lauf um 08:00 vor der Feuerzeit 08:00 — ein
    Neustart am selben Tag hätte den Job noch einmal ausgeführt (01.10.2026)."""
    if not wert:
        return None
    zeit = datetime.fromisoformat(wert)
    if zeit.tzinfo is None:
        zeit = zeit.replace(tzinfo=timezone.utc)
    return zeit.astimezone().replace(tzinfo=None)


class ScheduledJobsRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, job: ScheduledJob) -> ScheduledJob:
        cursor = self._conn.execute(
            """
            INSERT INTO scheduled_jobs (
                agent_name, skill_name, skill_prompt,
                frequency, run_hour, run_minute, run_weekday, run_day, run_month,
                model, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.agent_name, job.skill_name, job.skill_prompt,
                job.frequency, job.run_hour, job.run_minute,
                job.run_weekday, job.run_day, job.run_month,
                job.model, 1 if job.enabled else 0,
            ),
        )
        self._conn.commit()
        return job.model_copy(update={"id": cursor.lastrowid})

    def get(self, job_id: int) -> Optional[ScheduledJob]:
        row = self._conn.execute(
            "SELECT * FROM scheduled_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return self._deserialize(row) if row else None

    def get_all(self) -> List[ScheduledJob]:
        rows = self._conn.execute(
            "SELECT * FROM scheduled_jobs ORDER BY created_at"
        ).fetchall()
        return [self._deserialize(r) for r in rows]

    def get_enabled(self) -> List[ScheduledJob]:
        rows = self._conn.execute(
            "SELECT * FROM scheduled_jobs WHERE enabled = 1"
        ).fetchall()
        return [self._deserialize(r) for r in rows]

    def set_enabled(self, job_id: int, enabled: bool) -> bool:
        cursor = self._conn.execute(
            "UPDATE scheduled_jobs SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, job_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def update_last_run(self, job_id: int) -> None:
        self._conn.execute(
            "UPDATE scheduled_jobs SET last_run = datetime('now') WHERE id = ?",
            (job_id,),
        )
        self._conn.commit()

    def update_model(self, job_id: int, model: Optional[str]) -> None:
        self._conn.execute(
            "UPDATE scheduled_jobs SET model = ? WHERE id = ?",
            (model, job_id),
        )
        self._conn.commit()

    def update_skill(self, job_id: int, skill_name: str, skill_prompt: str) -> None:
        self._conn.execute(
            "UPDATE scheduled_jobs SET skill_name = ?, skill_prompt = ? WHERE id = ?",
            (skill_name, skill_prompt, job_id),
        )
        self._conn.commit()

    def delete(self, job_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM scheduled_jobs WHERE id = ?", (job_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _deserialize(row: sqlite3.Row) -> ScheduledJob:
        keys = row.keys()
        return ScheduledJob(
            id=row["id"],
            agent_name=row["agent_name"],
            skill_name=row["skill_name"],
            skill_prompt=row["skill_prompt"],
            frequency=row["frequency"],
            run_hour=row["run_hour"],
            run_minute=row["run_minute"],
            run_weekday=row["run_weekday"],
            run_day=row["run_day"],
            run_month=row["run_month"] if "run_month" in keys else None,
            model=row["model"] if "model" in keys else None,
            enabled=bool(row["enabled"]),
            last_run=_ortszeit(row["last_run"]),
            created_at=_ortszeit(row["created_at"]) if "created_at" in keys else None,
        )


class ScheduledJobRunsRepository:
    """Persists execution history for scheduled jobs."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(self, job_id: int, source: str = "scheduled") -> ScheduledJobRun:
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            "INSERT INTO scheduled_job_runs (job_id, source, status, started_at) VALUES (?, ?, 'running', ?)",
            (job_id, source, now.isoformat()),
        )
        self._conn.commit()
        return ScheduledJobRun(id=cur.lastrowid, job_id=job_id, source=source, started_at=now)

    def complete(self, run_id: int) -> None:
        now = datetime.now(timezone.utc)
        self._conn.execute(
            "UPDATE scheduled_job_runs SET status = 'success', completed_at = ? WHERE id = ?",
            (now.isoformat(), run_id),
        )
        self._conn.commit()

    def fail(self, run_id: int, error_msg: str) -> None:
        now = datetime.now(timezone.utc)
        self._conn.execute(
            "UPDATE scheduled_job_runs SET status = 'failed', completed_at = ?, error_msg = ? WHERE id = ?",
            (now.isoformat(), error_msg[:500], run_id),
        )
        self._conn.commit()

    def fail_orphaned(self, error_msg: str = "Abgebrochen (App-Neustart)",
                      aelter_als: Optional[timedelta] = None) -> int:
        """Close run rows left in 'running' by a killed process.

        A run row only ever ends via complete()/fail() inside the executing process,
        so a power cut leaves in-flight runs stuck as 'running' forever. With
        `aelter_als`, only rows started longer ago are closed — the job and "run now"
        in the app are separate processes, a young 'running' row may be alive.
        Returns the number of rows closed.
        """
        now = datetime.now(timezone.utc)
        grenze = (now - aelter_als).isoformat() if aelter_als else now.isoformat()
        cur = self._conn.execute(
            "UPDATE scheduled_job_runs SET status = 'failed', completed_at = ?, error_msg = ? "
            "WHERE status = 'running' AND started_at <= ?",
            (now.isoformat(), error_msg[:500], grenze),
        )
        self._conn.commit()
        return cur.rowcount

    def append_log(self, run_id: int, msg: str) -> None:
        self._conn.execute(
            "UPDATE scheduled_job_runs SET log_output = COALESCE(log_output || char(10), '') || ? WHERE id = ?",
            (msg, run_id),
        )
        self._conn.commit()

    def count_jobs_with_failed_latest_run(self) -> int:
        """Number of enabled jobs whose most recent run failed.

        Feeds the sidebar warning: only the latest run per job counts, so a job
        that has recovered (green run after red ones) stops warning immediately.
        """
        row = self._conn.execute(
            """
            SELECT COUNT(*) FROM scheduled_jobs j
            JOIN scheduled_job_runs r ON r.id = (
                SELECT id FROM scheduled_job_runs
                WHERE job_id = j.id
                ORDER BY started_at DESC, id DESC LIMIT 1
            )
            WHERE j.enabled = 1 AND r.status = 'failed'
            """
        ).fetchone()
        return row[0]

    def count_failed_since(self, job_id: int, seit: datetime, source: str = "scheduled") -> int:
        """Failed runs of this job started at or after `seit` (aware), from `source`."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM scheduled_job_runs "
            "WHERE job_id = ? AND source = ? AND status = 'failed' AND started_at >= ?",
            (job_id, source, seit.astimezone(timezone.utc).isoformat()),
        ).fetchone()
        return row[0]

    def get_for_job(self, job_id: int, limit: int = 10) -> List[ScheduledJobRun]:
        rows = self._conn.execute(
            "SELECT * FROM scheduled_job_runs WHERE job_id = ? ORDER BY started_at DESC LIMIT ?",
            (job_id, limit),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_recent(self, limit: int = 50) -> List[ScheduledJobRun]:
        rows = self._conn.execute(
            "SELECT * FROM scheduled_job_runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> ScheduledJobRun:
        return ScheduledJobRun(
            id=row["id"],
            job_id=row["job_id"],
            source=row["source"],
            status=row["status"],
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            error_msg=row["error_msg"],
            log_output=row["log_output"] if row["log_output"] else None,
        )
