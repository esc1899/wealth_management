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
        analysis_text: Optional[str] = None,
    ) -> PositionAnalysis:
        """Insert a new analysis record and return it."""
        now = datetime.now(timezone.utc)
        # Survivorship insurance (FEAT-59 v2): capture ticker + scope now, while the
        # position still exists, so the verdict stays evaluable if it is later sold.
        ticker_snapshot, scope_snapshot = self._position_snapshot(position_id)
        cur = self._conn.execute(
            """
            INSERT INTO position_analyses
                (position_id, agent, skill_name, verdict, summary, session_id, analysis_text,
                 ticker_snapshot, scope_snapshot, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (position_id, agent, skill_name, verdict, summary, session_id, analysis_text,
             ticker_snapshot, scope_snapshot, now.isoformat()),
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
            analysis_text=analysis_text,
            created_at=now,
        )

    def _position_snapshot(self, position_id: int) -> tuple[Optional[str], Optional[str]]:
        """Return (ticker, scope) for a position at save time, or (None, None) if gone."""
        row = self._conn.execute(
            "SELECT ticker, in_portfolio, in_watchlist FROM positions WHERE id = ?",
            (position_id,),
        ).fetchone()
        if row is None:
            return None, None
        scope = "portfolio" if row["in_portfolio"] else "watchlist" if row["in_watchlist"] else "other"
        return (row["ticker"] or None), scope

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

    def get_verdicts_with_ticker(self, agents: List[str]) -> List[dict]:
        """Return every persisted verdict for ``agents``, joined to its position ticker.

        Read-only feed for the Verdict-Hindsight analysis (FEAT-59). Positions that were
        deleted/sold drop out of the INNER JOIN — that is the documented survivorship
        blind spot, surfaced (not hidden) by the caller. Verdicts with a NULL verdict are
        skipped. Each row: ``{agent, verdict, created_at, ticker, scope}`` where ``scope``
        is ``portfolio`` / ``watchlist`` / ``other`` (current flag — a position may have
        moved since the verdict, the documented approximation).
        """
        if not agents:
            return []
        placeholders = ",".join("?" * len(agents))
        # LEFT JOIN + COALESCE: a still-existing position uses its live ticker/scope; a
        # sold/deleted one falls back to the snapshot captured at save time (FEAT-59 v2).
        # Rows from before the snapshot columns existed and whose position is gone have
        # neither → dropped (the residual, shrinking survivorship blind spot).
        rows = self._conn.execute(
            f"""
            SELECT pa.agent, pa.verdict, pa.created_at,
                   COALESCE(p.ticker, pa.ticker_snapshot) AS ticker,
                   p.in_portfolio, p.in_watchlist, pa.scope_snapshot
            FROM position_analyses pa
            LEFT JOIN positions p ON p.id = pa.position_id
            WHERE pa.agent IN ({placeholders})
              AND pa.verdict IS NOT NULL AND pa.verdict != ''
              AND COALESCE(p.ticker, pa.ticker_snapshot) IS NOT NULL
              AND COALESCE(p.ticker, pa.ticker_snapshot) != ''
            ORDER BY pa.created_at ASC
            """,
            list(agents),
        ).fetchall()
        result = []
        for r in rows:
            if r["in_portfolio"] is not None:  # position still exists → live scope
                scope = "portfolio" if r["in_portfolio"] else "watchlist" if r["in_watchlist"] else "other"
            else:  # deleted → snapshot scope (may be None for pre-v2 rows)
                scope = r["scope_snapshot"] or "other"
            result.append({
                "agent": r["agent"],
                "verdict": r["verdict"],
                "created_at": r["created_at"],
                "ticker": r["ticker"],
                "scope": scope,
            })
        return result

    def count_directional_verdicts(self, agents: List[str]) -> int:
        """Count all non-empty verdicts for ``agents``, including deleted positions.

        Companion to :meth:`get_verdicts_with_ticker`: the difference between this total
        and the joined rows is the survivorship gap (verdicts whose position was sold or
        deleted), which the hindsight page surfaces explicitly.
        """
        if not agents:
            return 0
        placeholders = ",".join("?" * len(agents))
        row = self._conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM position_analyses
            WHERE agent IN ({placeholders})
              AND verdict IS NOT NULL AND verdict != ''
            """,
            list(agents),
        ).fetchone()
        return int(row["n"]) if row else 0

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
