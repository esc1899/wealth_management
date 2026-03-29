"""
NewsRepository — persistence for News Digest runs.
Each run stores the skill used, tickers covered, and the full markdown result.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from core.storage.models import NewsRun


class NewsRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def save_run(self, skill_name: str, tickers: list[str], result: str) -> NewsRun:
        tickers_str = ", ".join(tickers)
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "INSERT INTO news_runs (skill_name, tickers, result, created_at) VALUES (?, ?, ?, ?)",
            (skill_name, tickers_str, result, now),
        )
        self._conn.commit()
        return NewsRun(
            id=cur.lastrowid,
            skill_name=skill_name,
            tickers=tickers_str,
            result=result,
            created_at=datetime.fromisoformat(now),
        )

    def delete_run(self, run_id: int) -> None:
        self._conn.execute("DELETE FROM news_runs WHERE id = ?", (run_id,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_run(self, run_id: int) -> Optional[NewsRun]:
        row = self._conn.execute(
            "SELECT * FROM news_runs WHERE id = ?", (run_id,)
        ).fetchone()
        return self._row_to_run(row) if row else None

    def list_runs(self, limit: int = 20) -> list[NewsRun]:
        rows = self._conn.execute(
            "SELECT * FROM news_runs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_run(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> NewsRun:
        return NewsRun(
            id=row["id"],
            skill_name=row["skill_name"],
            tickers=row["tickers"],
            result=row["result"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
