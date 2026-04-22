"""
Watchlist Checker Repository — persistence for watchlist analysis results.

Stores summaries, full LLM responses, position fit verdicts, and metadata.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from core.storage.models import WatchlistCheckerAnalysis


class WatchlistCheckerRepository:
    """
    Manages watchlist checker analysis results (how watchlist positions fit the portfolio).
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def save_analysis(self, analysis: WatchlistCheckerAnalysis) -> WatchlistCheckerAnalysis:
        """Insert a new analysis record."""
        import json
        now = datetime.now(timezone.utc)

        # Serialize fit_counts to JSON if it's a dict
        fit_counts_str = analysis.fit_counts
        if isinstance(fit_counts_str, dict):
            fit_counts_str = json.dumps(fit_counts_str)

        cur = self._conn.execute(
            """INSERT INTO watchlist_checker_analyses
               (summary, full_text, fit_counts, position_fits_json, skill_name, model, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                analysis.summary,
                analysis.full_text,
                fit_counts_str,
                analysis.position_fits_json,
                analysis.skill_name,
                analysis.model,
                now.isoformat(),
            ),
        )
        self._conn.commit()
        # Return updated copy with DB-assigned id and timestamp
        return analysis.model_copy(update={
            "id": cur.lastrowid,
            "created_at": now,
        })

    def get_latest_analysis(self) -> Optional[WatchlistCheckerAnalysis]:
        """Return the most recent analysis."""
        row = self._conn.execute(
            """SELECT * FROM watchlist_checker_analyses
               ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
        return self._row_to_model(row) if row else None

    def get_analysis_history(self, limit: int = 10) -> list[WatchlistCheckerAnalysis]:
        """Return past analyses, newest first."""
        rows = self._conn.execute(
            """SELECT * FROM watchlist_checker_analyses
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [self._row_to_model(row) for row in rows if row]

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> WatchlistCheckerAnalysis:
        """Convert a database row to a WatchlistCheckerAnalysis model."""
        import json

        # Deserialize fit_counts from JSON
        fit_counts = row["fit_counts"]
        if fit_counts and isinstance(fit_counts, str):
            try:
                fit_counts = json.loads(fit_counts)
            except (json.JSONDecodeError, ValueError):
                fit_counts = None

        return WatchlistCheckerAnalysis(
            id=row["id"],
            summary=row["summary"],
            full_text=row["full_text"],
            fit_counts=fit_counts,
            position_fits_json=row["position_fits_json"],
            skill_name=row["skill_name"],
            model=row["model"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
