"""
ScheduledJobsRepository — CRUD for the scheduled_jobs table.
"""

import sqlite3
from datetime import datetime
from typing import List, Optional

from core.storage.models import ScheduledJob


class ScheduledJobsRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def add(self, job: ScheduledJob) -> ScheduledJob:
        cursor = self._conn.execute(
            """
            INSERT INTO scheduled_jobs (
                agent_name, skill_name, skill_prompt,
                frequency, run_hour, run_minute, run_weekday, run_day,
                model, enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.agent_name, job.skill_name, job.skill_prompt,
                job.frequency, job.run_hour, job.run_minute,
                job.run_weekday, job.run_day,
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

    def _deserialize(self, row: sqlite3.Row) -> ScheduledJob:
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
