"""
Consensus Gap repository — persists analysis sessions and chat messages.
No encryption: session metadata (ticker, skill names) is not sensitive.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from core.storage.models import ConsensusGapMessage, ConsensusGapSession


class ConsensusGapRepository:

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
    ) -> ConsensusGapSession:
        """Insert a new consensus gap session and return it with its generated id."""
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO consensus_gap_sessions
                (position_id, ticker, position_name, skill_name, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (position_id, ticker, position_name, skill_name, now.isoformat()),
        )
        self._conn.commit()
        return ConsensusGapSession(
            id=cur.lastrowid,
            position_id=position_id,
            ticker=ticker,
            position_name=position_name,
            skill_name=skill_name,
            created_at=now,
        )

    def get_session(self, session_id: int) -> Optional[ConsensusGapSession]:
        row = self._conn.execute(
            """
            SELECT s.*, pa.verdict
            FROM consensus_gap_sessions s
            LEFT JOIN position_analyses pa ON pa.session_id = s.id AND pa.agent = 'consensus_gap'
            WHERE s.id = ?
            """,
            (session_id,)
        ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(self, limit: int = 50) -> List[ConsensusGapSession]:
        rows = self._conn.execute(
            """
            SELECT s.*, pa.verdict
            FROM consensus_gap_sessions s
            LEFT JOIN position_analyses pa ON pa.session_id = s.id AND pa.agent = 'consensus_gap'
            ORDER BY s.created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def delete_session(self, session_id: int) -> None:
        self._conn.execute(
            "DELETE FROM consensus_gap_messages WHERE session_id = ?", (session_id,)
        )
        self._conn.execute(
            "DELETE FROM consensus_gap_sessions WHERE id = ?", (session_id,)
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, session_id: int, role: str, content: str) -> ConsensusGapMessage:
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO consensus_gap_messages (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, now.isoformat()),
        )
        self._conn.commit()
        return ConsensusGapMessage(
            id=cur.lastrowid,
            session_id=session_id,
            role=role,
            content=content,
            created_at=now,
        )

    def get_messages(self, session_id: int) -> List[ConsensusGapMessage]:
        rows = self._conn.execute(
            "SELECT * FROM consensus_gap_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> ConsensusGapSession:
        keys = row.keys()
        return ConsensusGapSession(
            id=row["id"],
            position_id=row["position_id"],
            ticker=row["ticker"],
            position_name=row["position_name"],
            skill_name=row["skill_name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            verdict=row["verdict"] if "verdict" in keys else None,
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> ConsensusGapMessage:
        return ConsensusGapMessage(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
