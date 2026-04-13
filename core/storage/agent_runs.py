"""Repository for agent_runs — execution lineage tracking."""

import json
from datetime import datetime
from typing import Optional, Any
import sqlite3


class AgentRunsRepository:
    """Tracks metadata about agent executions (lineage, context, dependencies)."""

    def __init__(self, db_connection: sqlite3.Connection):
        self.conn = db_connection

    def log_run(
        self,
        agent_name: str,
        model: Optional[str] = None,
        skills_used: Optional[list[str]] = None,
        agent_deps: Optional[list[str]] = None,
        output_summary: Optional[str] = None,
        context_summary: Optional[str] = None,
        started_at: Optional[str] = None,
        finished_at: Optional[str] = None,
        status: str = "done",
    ) -> int:
        """Log an agent run. Returns the run ID."""
        if started_at is None:
            started_at = datetime.now().isoformat()
        if finished_at is None:
            finished_at = datetime.now().isoformat()

        cursor = self.conn.execute(
            """
            INSERT INTO agent_runs
            (agent_name, model, skills_used, agent_deps, output_summary,
             context_summary, started_at, finished_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_name,
                model,
                json.dumps(skills_used) if skills_used else None,
                json.dumps(agent_deps) if agent_deps else None,
                output_summary,
                context_summary,
                started_at,
                finished_at,
                status,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_recent_runs(self, limit: int = 20) -> list[dict]:
        """Get recent agent runs, ordered by created_at DESC."""
        rows = self.conn.execute(
            """
            SELECT id, agent_name, model, skills_used, agent_deps, status,
                   started_at, finished_at, output_summary, context_summary, created_at
            FROM agent_runs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        return [
            {
                "id": row["id"],
                "agent_name": row["agent_name"],
                "model": row["model"],
                "skills_used": json.loads(row["skills_used"]) if row["skills_used"] else [],
                "agent_deps": json.loads(row["agent_deps"]) if row["agent_deps"] else [],
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "output_summary": row["output_summary"],
                "context_summary": row["context_summary"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_runs_for_agents(self, agent_names: list[str], limit: int = 50) -> list[dict]:
        """Get recent runs for specific agents (used for lineage display)."""
        placeholders = ",".join("?" * len(agent_names))
        rows = self.conn.execute(
            f"""
            SELECT id, agent_name, model, skills_used, agent_deps, status,
                   started_at, finished_at, output_summary, context_summary, created_at
            FROM agent_runs
            WHERE agent_name IN ({placeholders})
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (*agent_names, limit),
        ).fetchall()

        return [
            {
                "id": row["id"],
                "agent_name": row["agent_name"],
                "model": row["model"],
                "skills_used": json.loads(row["skills_used"]) if row["skills_used"] else [],
                "agent_deps": json.loads(row["agent_deps"]) if row["agent_deps"] else [],
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "output_summary": row["output_summary"],
                "context_summary": row["context_summary"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_latest_run(self, agent_name: str) -> Optional[dict]:
        """Get the most recent run for an agent."""
        row = self.conn.execute(
            """
            SELECT id, agent_name, model, skills_used, agent_deps, status,
                   started_at, finished_at, output_summary, context_summary, created_at
            FROM agent_runs
            WHERE agent_name = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (agent_name,),
        ).fetchone()

        if not row:
            return None

        return {
            "id": row["id"],
            "agent_name": row["agent_name"],
            "model": row["model"],
            "skills_used": json.loads(row["skills_used"]) if row["skills_used"] else [],
            "agent_deps": json.loads(row["agent_deps"]) if row["agent_deps"] else [],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "output_summary": row["output_summary"],
            "context_summary": row["context_summary"],
            "created_at": row["created_at"],
        }
