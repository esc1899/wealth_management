"""
MonthlyDigestRepository — persists auto-generated monthly portfolio digests.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class MonthlyDigest:
    id: Optional[int]
    month: str           # "2026-05"
    body_markdown: str
    generated_at: datetime


class MonthlyDigestRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get(self, month: str) -> Optional[MonthlyDigest]:
        row = self._conn.execute(
            "SELECT * FROM monthly_digests WHERE month = ?", (month,)
        ).fetchone()
        return self._deserialize(row) if row else None

    def save(self, month: str, body_markdown: str) -> MonthlyDigest:
        now = datetime.now(timezone.utc)
        self._conn.execute(
            """
            INSERT INTO monthly_digests (month, body_markdown, generated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(month) DO UPDATE SET body_markdown=excluded.body_markdown,
                                              generated_at=excluded.generated_at
            """,
            (month, body_markdown, now.isoformat()),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM monthly_digests WHERE month = ?", (month,)
        ).fetchone()
        return self._deserialize(row)

    def get_recent(self, limit: int = 6) -> List[MonthlyDigest]:
        rows = self._conn.execute(
            "SELECT * FROM monthly_digests ORDER BY month DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._deserialize(r) for r in rows]

    def _deserialize(self, row) -> MonthlyDigest:
        return MonthlyDigest(
            id=row["id"],
            month=row["month"],
            body_markdown=row["body_markdown"],
            generated_at=datetime.fromisoformat(row["generated_at"]),
        )
