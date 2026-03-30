"""
Repository for LLM token usage tracking.
"""

import sqlite3
from datetime import datetime, date
from typing import Optional

from core.storage.models import UsageRecord


class UsageRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(self, agent: str, model: str, input_tokens: int, output_tokens: int) -> None:
        self._conn.execute(
            "INSERT INTO llm_usage (agent, model, input_tokens, output_tokens, created_at) VALUES (?, ?, ?, ?, ?)",
            (agent, model, input_tokens, output_tokens, datetime.utcnow().isoformat()),
        )
        self._conn.commit()

    def total_today(self) -> dict[str, int]:
        """Sum of input+output tokens per agent for today (UTC)."""
        today = date.today().isoformat()
        rows = self._conn.execute(
            """SELECT agent, model,
                      SUM(input_tokens) AS input_tokens,
                      SUM(output_tokens) AS output_tokens
               FROM llm_usage
               WHERE date(created_at) = ?
               GROUP BY agent, model
               ORDER BY agent""",
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]

    def total_all_time(self) -> list[dict]:
        """Sum of tokens per agent+model across all time."""
        rows = self._conn.execute(
            """SELECT agent, model,
                      SUM(input_tokens) AS input_tokens,
                      SUM(output_tokens) AS output_tokens,
                      COUNT(*) AS calls
               FROM llm_usage
               GROUP BY agent, model
               ORDER BY agent""",
        ).fetchall()
        return [dict(r) for r in rows]

    def daily_totals(self, limit: int = 30) -> list[dict]:
        """Aggregated tokens per day (last N days) — for a chart."""
        rows = self._conn.execute(
            """SELECT date(created_at) AS day,
                      SUM(input_tokens) AS input_tokens,
                      SUM(output_tokens) AS output_tokens
               FROM llm_usage
               GROUP BY day
               ORDER BY day DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
