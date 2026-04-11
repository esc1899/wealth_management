"""
Portfolio Story Repository — persistence for portfolio-level narrative and analysis.

Encrypted field: story (personal financial goals).
All analysis verdicts and summaries are stored plain text (no privacy benefit to encrypt analysis results).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from core.encryption import EncryptionService
from core.storage.models import PortfolioStory, PortfolioStoryAnalysis


class PortfolioStoryRepository:
    """
    Manages portfolio story (user's goals, time horizon, priorities)
    and analysis results (story checks, performance checks).
    """

    def __init__(self, conn: sqlite3.Connection, enc: EncryptionService):
        self._conn = conn
        self._enc = enc

    # ────────────────────────────────────────────────────────────────────
    # Story CRUD
    # ────────────────────────────────────────────────────────────────────

    def get_current(self) -> Optional[PortfolioStory]:
        """Return the most recent portfolio story."""
        row = self._conn.execute(
            """SELECT * FROM portfolio_story
               ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
        return self._row_to_story(row) if row else None

    def save(self, story: PortfolioStory) -> PortfolioStory:
        """Insert or update a portfolio story. Returns the saved object."""
        now = datetime.now(timezone.utc)
        story.updated_at = now
        if story.id:
            # Update existing
            self._conn.execute(
                """UPDATE portfolio_story
                   SET story = ?, target_year = ?, liquidity_need = ?, priority = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    self._enc.encrypt(story.story),
                    story.target_year,
                    story.liquidity_need,
                    story.priority,
                    now.isoformat(),
                    story.id,
                ),
            )
            self._conn.commit()
            return story
        else:
            # Insert new
            story.created_at = now
            cur = self._conn.execute(
                """INSERT INTO portfolio_story
                   (story, target_year, liquidity_need, priority, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    self._enc.encrypt(story.story),
                    story.target_year,
                    story.liquidity_need,
                    story.priority,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            self._conn.commit()
            story.id = cur.lastrowid
            return story

    def get_history(self, limit: int = 10) -> list[PortfolioStory]:
        """Return past portfolio stories, newest first."""
        rows = self._conn.execute(
            """SELECT * FROM portfolio_story
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [self._row_to_story(row) for row in rows if row]

    # ────────────────────────────────────────────────────────────────────
    # Analysis CRUD
    # ────────────────────────────────────────────────────────────────────

    def save_analysis(self, analysis: PortfolioStoryAnalysis) -> PortfolioStoryAnalysis:
        """Insert a new analysis record."""
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """INSERT INTO portfolio_story_analyses
               (verdict, summary, perf_verdict, perf_summary, stability_verdict, stability_summary, full_text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                analysis.verdict,
                analysis.summary,
                analysis.perf_verdict,
                analysis.perf_summary,
                analysis.stability_verdict,
                analysis.stability_summary,
                analysis.full_text,
                now.isoformat(),
            ),
        )
        self._conn.commit()
        # Return updated copy with DB-assigned id and timestamp
        return analysis.model_copy(update={
            "id": cur.lastrowid,
            "created_at": now,
        })

    def get_latest_analysis(self) -> Optional[PortfolioStoryAnalysis]:
        """Return the most recent analysis."""
        row = self._conn.execute(
            """SELECT * FROM portfolio_story_analyses
               ORDER BY created_at DESC LIMIT 1"""
        ).fetchone()
        return self._row_to_analysis(row) if row else None

    def get_analysis_history(self, limit: int = 10) -> list[PortfolioStoryAnalysis]:
        """Return past analyses, newest first."""
        rows = self._conn.execute(
            """SELECT * FROM portfolio_story_analyses
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [self._row_to_analysis(row) for row in rows if row]

    # ────────────────────────────────────────────────────────────────────
    # Deserializers
    # ────────────────────────────────────────────────────────────────────

    def _row_to_story(self, row: sqlite3.Row) -> PortfolioStory:
        """Deserialize a portfolio_story row."""
        decrypted_story = (
            self._enc.decrypt(row["story"]) if row["story"] else ""
        )
        return PortfolioStory(
            id=row["id"],
            story=decrypted_story,
            target_year=row["target_year"],
            liquidity_need=row["liquidity_need"],
            priority=row["priority"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _row_to_analysis(self, row: sqlite3.Row) -> PortfolioStoryAnalysis:
        """Deserialize a portfolio_story_analyses row."""
        return PortfolioStoryAnalysis(
            id=row["id"],
            verdict=row["verdict"],
            summary=row["summary"],
            perf_verdict=row["perf_verdict"],
            perf_summary=row["perf_summary"],
            stability_verdict=row["stability_verdict"],
            stability_summary=row["stability_summary"],
            full_text=row["full_text"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
