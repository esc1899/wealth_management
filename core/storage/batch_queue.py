"""
BatchQueueRepository — tracks pending Anthropic Message Batches.

Each row represents one submitted batch (all positions for one agent run).
Polling job checks processing_status and calls mark_done/mark_error when complete.
"""

import sqlite3
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class PendingBatch:
    id: int
    batch_id: str
    agent_name: str
    skill_name: Optional[str]
    language: str
    status: str
    submitted_at: str
    completed_at: Optional[str]
    request_count: Optional[int]
    success_count: Optional[int]
    error_count: Optional[int]
    error_msg: Optional[str]


class BatchQueueRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def create(
        self,
        batch_id: str,
        agent_name: str,
        skill_name: Optional[str],
        language: str,
        request_count: int,
    ) -> None:
        self._conn.execute(
            """INSERT OR IGNORE INTO pending_batches
               (batch_id, agent_name, skill_name, language, request_count)
               VALUES (?, ?, ?, ?, ?)""",
            (batch_id, agent_name, skill_name, language, request_count),
        )
        self._conn.commit()

    def get_pending(self) -> List[PendingBatch]:
        rows = self._conn.execute(
            "SELECT * FROM pending_batches WHERE status = 'processing' ORDER BY submitted_at"
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def mark_done(self, batch_id: str, success_count: int, error_count: int) -> None:
        self._conn.execute(
            """UPDATE pending_batches
               SET status = 'done', completed_at = datetime('now'),
                   success_count = ?, error_count = ?
               WHERE batch_id = ?""",
            (success_count, error_count, batch_id),
        )
        self._conn.commit()

    def mark_error(self, batch_id: str, error_msg: str) -> None:
        self._conn.execute(
            """UPDATE pending_batches
               SET status = 'error', completed_at = datetime('now'), error_msg = ?
               WHERE batch_id = ?""",
            (error_msg, batch_id),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_model(row) -> PendingBatch:
        return PendingBatch(
            id=row["id"],
            batch_id=row["batch_id"],
            agent_name=row["agent_name"],
            skill_name=row["skill_name"],
            language=row["language"] or "de",
            status=row["status"],
            submitted_at=row["submitted_at"],
            completed_at=row["completed_at"],
            request_count=row["request_count"],
            success_count=row["success_count"],
            error_count=row["error_count"],
            error_msg=row["error_msg"],
        )
