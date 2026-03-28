"""
Research repository — persists research sessions and their chat messages.
No encryption: research content is not considered sensitive (public market data).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from core.storage.models import ResearchMessage, ResearchSession


class ResearchRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(
        self,
        ticker: str,
        strategy_name: str,
        strategy_prompt: str,
        company_name: Optional[str] = None,
    ) -> ResearchSession:
        """Insert a new research session and return it with its generated id."""
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO research_sessions (ticker, company_name, strategy_name, strategy_prompt, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ticker.upper().strip(), company_name, strategy_name, strategy_prompt, now.isoformat()),
        )
        self._conn.commit()
        return ResearchSession(
            id=cur.lastrowid,
            ticker=ticker,
            company_name=company_name,
            strategy_name=strategy_name,
            strategy_prompt=strategy_prompt,
            created_at=now,
        )

    def get_session(self, session_id: int) -> Optional[ResearchSession]:
        """Return a session by id, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM research_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def list_sessions(self, limit: int = 50) -> List[ResearchSession]:
        """Return the most recent sessions ordered by creation time descending."""
        rows = self._conn.execute(
            "SELECT * FROM research_sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def update_summary(self, session_id: int, summary: str) -> None:
        """Attach a generated summary to a finished session."""
        self._conn.execute(
            "UPDATE research_sessions SET summary = ? WHERE id = ?",
            (summary, session_id),
        )
        self._conn.commit()

    def delete_session(self, session_id: int) -> None:
        """Delete a session and all its messages (FK cascade)."""
        self._conn.execute(
            "DELETE FROM research_messages WHERE session_id = ?", (session_id,)
        )
        self._conn.execute(
            "DELETE FROM research_sessions WHERE id = ?", (session_id,)
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, session_id: int, role: str, content: str) -> ResearchMessage:
        """Append a message to a session and return it with its generated id."""
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO research_messages (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, now.isoformat()),
        )
        self._conn.commit()
        return ResearchMessage(
            id=cur.lastrowid,
            session_id=session_id,
            role=role,
            content=content,
            created_at=now,
        )

    def get_messages(self, session_id: int) -> List[ResearchMessage]:
        """Return all messages for a session in chronological order."""
        rows = self._conn.execute(
            "SELECT * FROM research_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> ResearchSession:
        return ResearchSession(
            id=row["id"],
            ticker=row["ticker"],
            company_name=row["company_name"],
            strategy_name=row["strategy_name"],
            strategy_prompt=row["strategy_prompt"],
            created_at=datetime.fromisoformat(row["created_at"]),
            summary=row["summary"],
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> ResearchMessage:
        return ResearchMessage(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
