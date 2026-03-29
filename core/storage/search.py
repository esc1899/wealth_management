"""
Search repository — persists investment search sessions and their chat messages.
No encryption: search content is not sensitive (public market data).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from core.storage.models import SearchMessage, SearchSession


class SearchRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(
        self,
        query: str,
        skill_name: str,
        skill_prompt: str,
    ) -> SearchSession:
        """Insert a new search session and return it with its generated id."""
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO search_sessions (query, skill_name, skill_prompt, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (query, skill_name, skill_prompt, now.isoformat()),
        )
        self._conn.commit()
        return SearchSession(
            id=cur.lastrowid,
            query=query,
            skill_name=skill_name,
            skill_prompt=skill_prompt,
            created_at=now,
        )

    def get_session(self, session_id: int) -> Optional[SearchSession]:
        row = self._conn.execute(
            "SELECT * FROM search_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(self, limit: int = 50) -> List[SearchSession]:
        rows = self._conn.execute(
            "SELECT * FROM search_sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def delete_session(self, session_id: int) -> None:
        self._conn.execute(
            "DELETE FROM search_messages WHERE session_id = ?", (session_id,)
        )
        self._conn.execute(
            "DELETE FROM search_sessions WHERE id = ?", (session_id,)
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, session_id: int, role: str, content: str) -> SearchMessage:
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO search_messages (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, now.isoformat()),
        )
        self._conn.commit()
        return SearchMessage(
            id=cur.lastrowid,
            session_id=session_id,
            role=role,
            content=content,
            created_at=now,
        )

    def get_messages(self, session_id: int) -> List[SearchMessage]:
        rows = self._conn.execute(
            "SELECT * FROM search_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> SearchSession:
        return SearchSession(
            id=row["id"],
            query=row["query"],
            skill_name=row["skill_name"],
            skill_prompt=row["skill_prompt"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> SearchMessage:
        return SearchMessage(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
