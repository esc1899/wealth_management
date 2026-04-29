"""
PositionAnalysesRepository — persists analysis results per position.

Each cloud agent can save a verdict + summary here after completing an analysis.
No encryption: verdicts and summaries contain no private financial data.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional, Union

from core.storage.models import PositionAnalysis


class PositionAnalysesRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def save(
        self,
        position_id: int,
        agent: str,
        skill_name: str,
        verdict: Optional[str],
        summary: Optional[str],
        session_id: Optional[int] = None,
    ) -> PositionAnalysis:
        """Insert a new analysis record and return it."""
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO position_analyses
                (position_id, agent, skill_name, verdict, summary, session_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (position_id, agent, skill_name, verdict, summary, session_id, now.isoformat()),
        )
        self._conn.commit()
        return PositionAnalysis(
            id=cur.lastrowid,
            position_id=position_id,
            agent=agent,
            skill_name=skill_name,
            verdict=verdict,
            summary=summary,
            session_id=session_id,
            created_at=now,
        )

    def get_for_position(self, position_id: int, limit: int = 20) -> List[PositionAnalysis]:
        """Return analyses for a position, newest first."""
        rows = self._conn.execute(
            """
            SELECT * FROM position_analyses
            WHERE position_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (position_id, limit),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def get_latest_bulk(
        self, position_ids: list[int], agent: Union[str, list[str]]
    ) -> dict[int, PositionAnalysis]:
        """Return the most recent analysis per position for a list of ids.

        Args:
            position_ids: List of position IDs to fetch analyses for
            agent: Single agent name (str) or list of agent names to match
        """
        if not position_ids:
            return {}

        # Normalize agent to list
        agents = [agent] if isinstance(agent, str) else agent
        agent_placeholders = ",".join("?" * len(agents))
        pos_placeholders = ",".join("?" * len(position_ids))

        rows = self._conn.execute(
            f"""
            SELECT * FROM position_analyses
            WHERE agent IN ({agent_placeholders}) AND position_id IN ({pos_placeholders})
            ORDER BY created_at ASC
            """,
            agents + list(position_ids),
        ).fetchall()
        # Keep the last row per position_id (ORDER BY ASC → last = newest)
        result: dict[int, PositionAnalysis] = {}
        for row in rows:
            result[row["position_id"]] = self._row_to_model(row)
        return result

    def get_latest(self, position_id: int, agent: str) -> Optional[PositionAnalysis]:
        """Return the most recent analysis for a position/agent combination."""
        row = self._conn.execute(
            """
            SELECT * FROM position_analyses
            WHERE position_id = ? AND agent = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (position_id, agent),
        ).fetchone()
        return self._row_to_model(row) if row else None

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> PositionAnalysis:
        session_id = row["session_id"]
        # Convert session_id from string to int (or None if empty/null)
        if session_id:
            try:
                session_id = int(session_id)
            except (ValueError, TypeError):
                session_id = None
        else:
            session_id = None

        return PositionAnalysis(
            id=row["id"],
            position_id=row["position_id"],
            agent=row["agent"],
            skill_name=row["skill_name"],
            verdict=row["verdict"],
            summary=row["summary"],
            session_id=session_id,
            created_at=datetime.fromisoformat(row["created_at"]),
        )
