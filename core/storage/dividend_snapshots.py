"""
Dividend snapshot repository — persists historical dividend income snapshots.
Snapshots track total annual dividend income (in EUR) over time, including asset class breakdown.
"""

from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timezone, date
from typing import List, Optional, Dict

from core.storage.models import DividendSnapshot


class DividendSnapshotRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def create(
        self,
        date_str: str,
        total_eur: float,
        breakdown: Dict[str, float],
        coverage_pct: float = 100.0,
        missing_pos: Optional[List[str]] = None,
        is_manual: bool = False,
        note: Optional[str] = None,
    ) -> DividendSnapshot:
        """Create a new dividend snapshot for a given date."""
        now = datetime.now(timezone.utc)
        breakdown_json = json.dumps(breakdown)
        missing_pos_json = json.dumps(missing_pos or [])

        try:
            cur = self._conn.execute(
                """
                INSERT INTO dividend_snapshots
                (date, total_eur, breakdown, coverage_pct, missing_pos, is_manual, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (date_str, total_eur, breakdown_json, coverage_pct, missing_pos_json,
                 1 if is_manual else 0, note, now.isoformat()),
            )
            self._conn.commit()
        except sqlite3.IntegrityError:
            # Snapshot for this date already exists
            raise ValueError(f"Dividend snapshot for {date_str} already exists")

        return DividendSnapshot(
            id=cur.lastrowid,
            date=date_str,
            total_eur=total_eur,
            breakdown=breakdown,
            coverage_pct=coverage_pct,
            missing_pos=missing_pos,
            is_manual=is_manual,
            note=note,
            created_at=now,
        )

    def delete(self, snapshot_id: int) -> None:
        """Delete a snapshot by ID."""
        self._conn.execute("DELETE FROM dividend_snapshots WHERE id = ?", (snapshot_id,))
        self._conn.commit()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_by_date(self, date_str: str) -> Optional[DividendSnapshot]:
        """Get a snapshot for a specific date (YYYY-MM-DD)."""
        row = self._conn.execute(
            "SELECT * FROM dividend_snapshots WHERE date = ?", (date_str,)
        ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def get_by_id(self, snapshot_id: int) -> Optional[DividendSnapshot]:
        """Get a snapshot by ID."""
        row = self._conn.execute(
            "SELECT * FROM dividend_snapshots WHERE id = ?", (snapshot_id,)
        ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def latest(self) -> Optional[DividendSnapshot]:
        """Get the most recent snapshot."""
        row = self._conn.execute(
            "SELECT * FROM dividend_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def list(self, days: int = 365) -> List[DividendSnapshot]:
        """List all snapshots, optionally filtered by age (days back)."""
        if days is None:
            rows = self._conn.execute(
                "SELECT * FROM dividend_snapshots ORDER BY date ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM dividend_snapshots
                WHERE date >= date('now', '-' || ? || ' days')
                ORDER BY date ASC
                """,
                (days,),
            ).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def list_limit(self, limit: int = 50) -> List[DividendSnapshot]:
        """List most recent snapshots up to a limit."""
        rows = self._conn.execute(
            "SELECT * FROM dividend_snapshots ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_snapshot(r) for r in reversed(rows)]  # reverse to get ascending order

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _row_to_snapshot(self, row: sqlite3.Row) -> DividendSnapshot:
        """Convert a DB row to a DividendSnapshot object."""
        return DividendSnapshot(
            id=row["id"],
            date=row["date"],
            total_eur=row["total_eur"],
            breakdown=json.loads(row["breakdown"]),
            coverage_pct=row["coverage_pct"],
            missing_pos=json.loads(row["missing_pos"]) if row["missing_pos"] else None,
            is_manual=bool(row["is_manual"]),
            note=row["note"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
