"""
Devils Advocate repository — persists bear-case analysis sessions and messages.
No encryption: session metadata (ticker, skill names) is not sensitive.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from core.storage.models import DevilsAdvocateMessage, DevilsAdvocateSession


class DevilsAdvocateRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(
        self,
        position_id: int,
        ticker: Optional[str],
        position_name: str,
        skill_name: str,
    ) -> DevilsAdvocateSession:
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO devils_advocate_sessions
                (position_id, ticker, position_name, skill_name, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (position_id, ticker, position_name, skill_name, now.isoformat()),
        )
        self._conn.commit()
        return DevilsAdvocateSession(
            id=cur.lastrowid,
            position_id=position_id,
            ticker=ticker,
            position_name=position_name,
            skill_name=skill_name,
            created_at=now,
        )

    def get_session(self, session_id: int) -> Optional[DevilsAdvocateSession]:
        row = self._conn.execute(
            """
            SELECT s.*, pa.verdict
            FROM devils_advocate_sessions s
            LEFT JOIN position_analyses pa ON pa.session_id = s.id AND pa.agent = 'devils_advocate'
            WHERE s.id = ?
            """,
            (session_id,),
        ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(self, limit: int = 50) -> List[DevilsAdvocateSession]:
        rows = self._conn.execute(
            """
            SELECT s.*, pa.verdict
            FROM devils_advocate_sessions s
            LEFT JOIN position_analyses pa ON pa.session_id = s.id AND pa.agent = 'devils_advocate'
            ORDER BY s.created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def delete_session(self, session_id: int) -> None:
        self._conn.execute(
            "DELETE FROM devils_advocate_messages WHERE session_id = ?", (session_id,)
        )
        self._conn.execute(
            "DELETE FROM devils_advocate_sessions WHERE id = ?", (session_id,)
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, session_id: int, role: str, content: str) -> DevilsAdvocateMessage:
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO devils_advocate_messages (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, now.isoformat()),
        )
        self._conn.commit()
        return DevilsAdvocateMessage(
            id=cur.lastrowid,
            session_id=session_id,
            role=role,
            content=content,
            created_at=now,
        )

    def get_messages(self, session_id: int) -> List[DevilsAdvocateMessage]:
        rows = self._conn.execute(
            "SELECT * FROM devils_advocate_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> DevilsAdvocateSession:
        keys = row.keys()
        return DevilsAdvocateSession(
            id=row["id"],
            position_id=row["position_id"],
            ticker=row["ticker"],
            position_name=row["position_name"],
            skill_name=row["skill_name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            verdict=row["verdict"] if "verdict" in keys else None,
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> DevilsAdvocateMessage:
        return DevilsAdvocateMessage(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
