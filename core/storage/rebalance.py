"""
Rebalance repository — persists rebalancing sessions and their chat messages.
No encryption: portfolio snapshots contain only public market data and quantities,
which are already visible on the dashboard.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from core.storage.models import RebalanceMessage, RebalanceSession


class RebalanceRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def create_session(
        self,
        skill_name: str,
        skill_prompt: str,
        portfolio_snapshot: str,
    ) -> RebalanceSession:
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO rebalance_sessions (skill_name, skill_prompt, portfolio_snapshot, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (skill_name, skill_prompt, portfolio_snapshot, now.isoformat()),
        )
        self._conn.commit()
        return RebalanceSession(
            id=cur.lastrowid,
            skill_name=skill_name,
            skill_prompt=skill_prompt,
            portfolio_snapshot=portfolio_snapshot,
            created_at=now,
        )

    def get_session(self, session_id: int) -> Optional[RebalanceSession]:
        row = self._conn.execute(
            "SELECT * FROM rebalance_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(self, limit: int = 30) -> List[RebalanceSession]:
        rows = self._conn.execute(
            "SELECT * FROM rebalance_sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def delete_session(self, session_id: int) -> None:
        self._conn.execute(
            "DELETE FROM rebalance_messages WHERE session_id = ?", (session_id,)
        )
        self._conn.execute(
            "DELETE FROM rebalance_sessions WHERE id = ?", (session_id,)
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, session_id: int, role: str, content: str) -> RebalanceMessage:
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO rebalance_messages (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, now.isoformat()),
        )
        self._conn.commit()
        return RebalanceMessage(
            id=cur.lastrowid,
            session_id=session_id,
            role=role,
            content=content,
            created_at=now,
        )

    def get_messages(self, session_id: int) -> List[RebalanceMessage]:
        rows = self._conn.execute(
            "SELECT * FROM rebalance_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> RebalanceSession:
        return RebalanceSession(
            id=row["id"],
            skill_name=row["skill_name"],
            skill_prompt=row["skill_prompt"],
            portfolio_snapshot=row["portfolio_snapshot"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> RebalanceMessage:
        return RebalanceMessage(
            id=row["id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
