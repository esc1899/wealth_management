"""
Portfolio Robustness repository — persists portfolio-level bear-case analyses.
Simple insert/retrieve pattern (no session/message structure needed).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from core.storage.models import PortfolioRobustnessAnalysis


class PortfolioRobustnessRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def save(
        self,
        verdict: str,
        summary: str,
        analysis_text: str,
        position_count: Optional[int] = None,
    ) -> PortfolioRobustnessAnalysis:
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO portfolio_robustness_analyses
                (verdict, summary, analysis_text, position_count, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (verdict, summary, analysis_text, position_count, now.isoformat()),
        )
        self._conn.commit()
        return PortfolioRobustnessAnalysis(
            id=cur.lastrowid,
            verdict=verdict,
            summary=summary,
            analysis_text=analysis_text,
            position_count=position_count,
            created_at=now,
        )

    def get_latest(self) -> Optional[PortfolioRobustnessAnalysis]:
        row = self._conn.execute(
            "SELECT * FROM portfolio_robustness_analyses ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return self._row_to_model(row) if row else None

    def list_recent(self, limit: int = 5) -> List[PortfolioRobustnessAnalysis]:
        rows = self._conn.execute(
            "SELECT * FROM portfolio_robustness_analyses ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> PortfolioRobustnessAnalysis:
        return PortfolioRobustnessAnalysis(
            id=row["id"],
            verdict=row["verdict"],
            summary=row["summary"],
            analysis_text=row["analysis_text"],
            position_count=row["position_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
