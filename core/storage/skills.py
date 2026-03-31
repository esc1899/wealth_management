"""
Skills repository — persists reusable prompt skills grouped by area.
No encryption: skills are configuration, not personal financial data.

hidden=0 → user-facing skill (shown in UI, editable)
hidden=1 → system skill (injected into agent prompts, never shown in UI)
"""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from core.storage.models import Skill


class SkillsRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(self, skill: Skill) -> Skill:
        """Insert a new skill and return it with its generated id."""
        cur = self._conn.execute(
            """
            INSERT INTO skills (name, area, description, prompt, hidden)
            VALUES (?, ?, ?, ?, ?)
            """,
            (skill.name, skill.area, skill.description, skill.prompt, 1 if skill.hidden else 0),
        )
        self._conn.commit()
        return skill.model_copy(update={"id": cur.lastrowid})

    def update(self, skill: Skill) -> None:
        """Update an existing skill by id."""
        self._conn.execute(
            """
            UPDATE skills
            SET name = ?, area = ?, description = ?, prompt = ?
            WHERE id = ?
            """,
            (skill.name, skill.area, skill.description, skill.prompt, skill.id),
        )
        self._conn.commit()

    def delete(self, skill_id: int) -> None:
        """Delete a skill by id."""
        self._conn.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
        self._conn.commit()

    def seed_if_empty(self, area: str, skills_list: list[dict]) -> None:
        """Insert default skills for an area only if none exist yet.

        Uses INSERT OR IGNORE so duplicate (name, area) pairs are silently skipped
        even if the table already contains unrelated entries for this area.
        Only seeds visible (hidden=0) skills.
        """
        if self.get_by_area(area):
            return
        for s in skills_list:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO skills (name, area, description, prompt, hidden)
                VALUES (?, ?, ?, ?, 0)
                """,
                (s["name"], area, s.get("description"), s["prompt"]),
            )
        self._conn.commit()

    def seed_system_skills(self, skills_list: list[dict]) -> None:
        """Seed hidden system skills (INSERT OR IGNORE — never overwrites existing).

        Called on every startup from state.py so new system skills are picked up.
        Uses (name, area) uniqueness constraint to avoid duplicates.
        """
        for s in skills_list:
            area = s.get("area", "system")
            self._conn.execute(
                """
                INSERT OR IGNORE INTO skills (name, area, description, prompt, hidden)
                VALUES (?, ?, ?, ?, 1)
                """,
                (s["name"], area, s.get("description"), s["prompt"]),
            )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get_all(self) -> List[Skill]:
        """Return all visible (non-hidden) skills ordered by area then name."""
        rows = self._conn.execute(
            "SELECT * FROM skills WHERE hidden = 0 ORDER BY area, name"
        ).fetchall()
        return [self._row_to_skill(r) for r in rows]

    def get_by_area(self, area: str) -> List[Skill]:
        """Return all visible skills for a given area, ordered by name."""
        rows = self._conn.execute(
            "SELECT * FROM skills WHERE area = ? AND hidden = 0 ORDER BY name",
            (area,),
        ).fetchall()
        return [self._row_to_skill(r) for r in rows]

    def get_system_skills(self) -> List[Skill]:
        """Return all hidden system skills (for agent prompt injection)."""
        rows = self._conn.execute(
            "SELECT * FROM skills WHERE hidden = 1 ORDER BY area, name"
        ).fetchall()
        return [self._row_to_skill(r) for r in rows]

    def get(self, skill_id: int) -> Optional[Skill]:
        """Return a skill by id, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM skills WHERE id = ?", (skill_id,)
        ).fetchone()
        return self._row_to_skill(row) if row else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_skill(row: sqlite3.Row) -> Skill:
        keys = row.keys()
        return Skill(
            id=row["id"],
            name=row["name"],
            area=row["area"],
            description=row["description"],
            prompt=row["prompt"],
            created_at=row["created_at"],
            hidden=bool(row["hidden"]) if "hidden" in keys else False,
        )
