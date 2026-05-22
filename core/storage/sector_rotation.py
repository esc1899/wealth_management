"""
SectorRotationRepository — persistence for sector rotation scan runs, messages, and verdicts.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class SectorRotationRun:
    id: int
    skill_name: str
    result: str
    created_at: datetime


@dataclass
class SectorRotationMessage:
    id: int
    run_id: int
    role: str
    content: str
    created_at: datetime


@dataclass
class SectorVerdict:
    id: int
    run_id: int
    sector: str
    verdict: str
    momentum: Optional[str]
    summary: Optional[str]
    created_at: datetime


class SectorRotationRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def save_run(self, skill_name: str, result: str) -> SectorRotationRun:
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            "INSERT INTO sector_rotation_runs (skill_name, result, created_at) VALUES (?, ?, ?)",
            (skill_name, result, now),
        )
        self._conn.commit()
        return SectorRotationRun(
            id=cursor.lastrowid,
            skill_name=skill_name,
            result=result,
            created_at=datetime.fromisoformat(now),
        )

    def get_run(self, run_id: int) -> Optional[SectorRotationRun]:
        row = self._conn.execute(
            "SELECT * FROM sector_rotation_runs WHERE id = ?", (run_id,)
        ).fetchone()
        return self._run_from_row(row) if row else None

    def get_recent_runs(self, limit: int = 10) -> List[SectorRotationRun]:
        rows = self._conn.execute(
            "SELECT * FROM sector_rotation_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._run_from_row(r) for r in rows]

    def _run_from_row(self, row: sqlite3.Row) -> SectorRotationRun:
        return SectorRotationRun(
            id=row["id"],
            skill_name=row["skill_name"],
            result=row["result"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, run_id: int, role: str, content: str) -> SectorRotationMessage:
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            "INSERT INTO sector_rotation_messages (run_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (run_id, role, content, now),
        )
        self._conn.commit()
        return SectorRotationMessage(
            id=cursor.lastrowid,
            run_id=run_id,
            role=role,
            content=content,
            created_at=datetime.fromisoformat(now),
        )

    def get_messages(self, run_id: int) -> List[SectorRotationMessage]:
        rows = self._conn.execute(
            "SELECT * FROM sector_rotation_messages WHERE run_id = ? ORDER BY created_at",
            (run_id,),
        ).fetchall()
        return [
            SectorRotationMessage(
                id=r["id"],
                run_id=r["run_id"],
                role=r["role"],
                content=r["content"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Verdicts
    # ------------------------------------------------------------------

    def save_verdict(
        self,
        run_id: int,
        sector: str,
        verdict: str,
        momentum: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> SectorVerdict:
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            "INSERT INTO sector_verdicts (run_id, sector, verdict, momentum, summary, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, sector, verdict, momentum, summary, now),
        )
        self._conn.commit()
        return SectorVerdict(
            id=cursor.lastrowid,
            run_id=run_id,
            sector=sector,
            verdict=verdict,
            momentum=momentum,
            summary=summary,
            created_at=datetime.fromisoformat(now),
        )

    def get_verdicts(self, run_id: int) -> List[SectorVerdict]:
        rows = self._conn.execute(
            "SELECT * FROM sector_verdicts WHERE run_id = ? ORDER BY sector",
            (run_id,),
        ).fetchall()
        return [
            SectorVerdict(
                id=r["id"],
                run_id=r["run_id"],
                sector=r["sector"],
                verdict=r["verdict"],
                momentum=r["momentum"],
                summary=r["summary"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]
