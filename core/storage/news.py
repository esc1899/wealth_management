"""
NewsRepository — persistence for News Digest runs and follow-up messages.
Each run stores the skill used, tickers covered, and the full markdown result.
Follow-up chat messages are stored per run in news_messages.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from core.storage.models import NewsMessage, NewsRun


class NewsRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # Runs
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
        self._conn.execute("DELETE FROM news_messages WHERE run_id = ?", (run_id,))
        self._conn.execute("DELETE FROM news_runs WHERE id = ?", (run_id,))
        self._conn.commit()

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
    # Messages
    # ------------------------------------------------------------------

    def add_message(self, run_id: int, role: str, content: str) -> NewsMessage:
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO news_messages (run_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (run_id, role, content, now.isoformat()),
        )
        self._conn.commit()
        return NewsMessage(
            id=cur.lastrowid,
            run_id=run_id,
            role=role,
            content=content,
            created_at=now,
        )

    def get_messages(self, run_id: int) -> List[NewsMessage]:
        rows = self._conn.execute(
            "SELECT * FROM news_messages WHERE run_id = ? ORDER BY created_at ASC",
            (run_id,),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

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

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> NewsMessage:
        return NewsMessage(
            id=row["id"],
            run_id=row["run_id"],
            role=row["role"],
            content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
