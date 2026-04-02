"""
StructuralScansRepository — persistence for structural-change scan runs and messages.
"""

import sqlite3
from datetime import datetime
from typing import List, Optional

from core.storage.models import StructuralScanRun, StructuralScanMessage


class StructuralScansRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def save_run(
        self,
        skill_name: str,
        result: str,
        user_focus: Optional[str] = None,
    ) -> StructuralScanRun:
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            "INSERT INTO structural_scan_runs (skill_name, user_focus, result, created_at) VALUES (?, ?, ?, ?)",
            (skill_name, user_focus, result, now),
        )
        self._conn.commit()
        return StructuralScanRun(
            id=cursor.lastrowid,
            skill_name=skill_name,
            user_focus=user_focus,
            result=result,
            created_at=datetime.fromisoformat(now),
        )

    def get_run(self, run_id: int) -> Optional[StructuralScanRun]:
        row = self._conn.execute(
            "SELECT * FROM structural_scan_runs WHERE id = ?", (run_id,)
        ).fetchone()
        return self._run_from_row(row) if row else None

    def get_recent_runs(self, limit: int = 10) -> List[StructuralScanRun]:
        rows = self._conn.execute(
            "SELECT * FROM structural_scan_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._run_from_row(r) for r in rows]

    def _run_from_row(self, row: sqlite3.Row) -> StructuralScanRun:
        return StructuralScanRun(
            id=row["id"],
            skill_name=row["skill_name"],
            user_focus=row["user_focus"],
            result=row["result"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, run_id: int, role: str, content: str) -> StructuralScanMessage:
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            "INSERT INTO structural_scan_messages (run_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (run_id, role, content, now),
        )
        self._conn.commit()
        return StructuralScanMessage(
            id=cursor.lastrowid,
            run_id=run_id,
            role=role,
            content=content,
            created_at=datetime.fromisoformat(now),
        )

    def get_messages(self, run_id: int) -> List[StructuralScanMessage]:
        rows = self._conn.execute(
            "SELECT * FROM structural_scan_messages WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        return [
            StructuralScanMessage(
                id=r["id"],
                run_id=r["run_id"],
                role=r["role"],
                content=r["content"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]
