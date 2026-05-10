"""
YearlyDigestRepository — persists auto-generated yearly portfolio digests.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class YearlyDigest:
    id: Optional[int]
    year: str            # "2026"
    body_markdown: str
    generated_at: datetime


class YearlyDigestRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get(self, year: str) -> Optional[YearlyDigest]:
        row = self._conn.execute(
            "SELECT * FROM yearly_digests WHERE year = ?", (year,)
        ).fetchone()
        return self._deserialize(row) if row else None

    def save(self, year: str, body_markdown: str) -> YearlyDigest:
        now = datetime.now(timezone.utc)
        self._conn.execute(
            """
            INSERT INTO yearly_digests (year, body_markdown, generated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(year) DO UPDATE SET body_markdown=excluded.body_markdown,
                                             generated_at=excluded.generated_at
            """,
            (year, body_markdown, now.isoformat()),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM yearly_digests WHERE year = ?", (year,)
        ).fetchone()
        return self._deserialize(row)

    def get_recent(self, limit: int = 5) -> List[YearlyDigest]:
        rows = self._conn.execute(
            "SELECT * FROM yearly_digests ORDER BY year DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._deserialize(r) for r in rows]

    def _deserialize(self, row) -> YearlyDigest:
        return YearlyDigest(
            id=row["id"],
            year=row["year"],
            body_markdown=row["body_markdown"],
            generated_at=datetime.fromisoformat(row["generated_at"]),
        )
