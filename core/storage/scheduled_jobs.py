"""
ScheduledJobsRepository + ScheduledJobRunsRepository — CRUD for scheduler tables.
"""

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from core.storage.models import ScheduledJob, ScheduledJobRun


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
            last_run=(
                datetime.fromisoformat(row["last_run"])
                if row["last_run"]
                else None
            ),
            created_at=(
                datetime.fromisoformat(row["created_at"])
                if "created_at" in keys and row["created_at"]
                else None
            ),
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

    def append_log(self, run_id: int, msg: str) -> None:
        self._conn.execute(
            "UPDATE scheduled_job_runs SET log_output = COALESCE(log_output || char(10), '') || ? WHERE id = ?",
            (msg, run_id),
        )
        self._conn.commit()

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
