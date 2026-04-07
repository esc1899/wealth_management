"""
Storychecker repository — persists story-check sessions and chat messages.
No encryption: session metadata (ticker, skill names) is not sensitive.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from core.storage.models import StorycheckerMessage, StorycheckerSession


class StorycheckerRepository:

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
        skill_prompt: str,
    ) -> StorycheckerSession:
        """Insert a new storychecker session and return it with its generated id."""
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO storychecker_sessions
                (position_id, ticker, position_name, skill_name, skill_prompt, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (position_id, ticker, position_name, skill_name, skill_prompt, now.isoformat()),
        )
        self._conn.commit()
        return StorycheckerSession(
            id=cur.lastrowid,
            position_id=position_id,
            ticker=ticker,
            position_name=position_name,
            skill_name=skill_name,
            skill_prompt=skill_prompt,
            created_at=now,
        )

    def get_session(self, session_id: int) -> Optional[StorycheckerSession]:
        row = self._conn.execute(
            "SELECT * FROM storychecker_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(self, limit: int = 50) -> List[StorycheckerSession]:
        rows = self._conn.execute(
            """
            SELECT s.*, pa.verdict
            FROM storychecker_sessions s
            LEFT JOIN position_analyses pa ON pa.session_id = s.id AND pa.agent = 'storychecker'
            ORDER BY s.created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def delete_session(self, session_id: int) -> None:
        self._conn.execute(
            "DELETE FROM storychecker_messages WHERE session_id = ?", (session_id,)
        )
        self._conn.execute(
            "DELETE FROM storychecker_sessions WHERE id = ?", (session_id,)
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, session_id: int, role: str, content: str) -> StorycheckerMessage:
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO storychecker_messages (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, now.isoformat()),
        )
        self._conn.commit()
        return StorycheckerMessage(
            id=cur.lastrowid,
            session_id=session_id,
            role=role,
            content=content,
            created_at=now,
        )

    def get_messages(self, session_id: int) -> List[StorycheckerMessage]:
        rows = self._conn.execute(
            "SELECT * FROM storychecker_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> StorycheckerSession:
        keys = row.keys()
        return StorycheckerSession(
            id=row["id"],
            position_id=row["position_id"],
            ticker=row["ticker"],
            position_name=row["position_name"],
            skill_name=row["skill_name"],
            skill_prompt=row["skill_prompt"],
            created_at=datetime.fromisoformat(row["created_at"]),
            verdict=row["verdict"] if "verdict" in keys else None,
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> StorycheckerMessage:
        return StorycheckerMessage(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
