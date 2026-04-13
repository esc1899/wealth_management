"""Tests for AgentRunsRepository — execution lineage tracking."""

import pytest
import sqlite3
import json
from datetime import datetime

from core.storage.agent_runs import AgentRunsRepository
from core.storage.base import get_connection, init_db, migrate_db


@pytest.fixture
def db_conn():
    """In-memory SQLite connection for testing."""
    conn = get_connection(":memory:")
    init_db(conn)
    migrate_db(conn)
    return conn


@pytest.fixture
def repo(db_conn):
    """AgentRunsRepository instance."""
    return AgentRunsRepository(db_conn)


class TestAgentRunsLog:
    """Test logging agent executions."""

    def test_log_run_returns_id(self, repo):
        """log_run returns the database ID."""
        run_id = repo.log_run(
            agent_name="test_agent",
            model="test-model",
            output_summary="Test output",
        )
        assert isinstance(run_id, int)
        assert run_id > 0

    def test_log_run_with_all_fields(self, repo):
        """log_run stores all provided fields."""
        run_id = repo.log_run(
            agent_name="portfolio_story",
            model="llama3.3:70b",
            skills_used=["Josef's Regel", "Story Analysis"],
            agent_deps=["storychecker"],
            output_summary="Story: intact, Performance: on_track",
            context_summary="Portfolio 5 positions, Story target_year 2030",
            status="done",
        )
        assert run_id > 0

    def test_log_run_defaults(self, repo):
        """log_run fills in defaults for timestamps and status."""
        run_id = repo.log_run(
            agent_name="watchlist_checker",
            model="ollama-local",
        )
        run = repo.get_latest_run("watchlist_checker")
        assert run is not None
        assert run["status"] == "done"
        assert run["started_at"] is not None
        assert run["finished_at"] is not None

    def test_log_run_with_skills_list(self, repo):
        """skills_used is stored as JSON array."""
        skills = ["Strategy A", "Strategy B"]
        run_id = repo.log_run(
            agent_name="investment_kompass",
            skills_used=skills,
        )
        run = repo.get_latest_run("investment_kompass")
        assert run["skills_used"] == skills

    def test_log_run_with_agent_deps(self, repo):
        """agent_deps is stored as JSON array."""
        deps = ["portfolio_story", "storychecker", "watchlist_checker"]
        run_id = repo.log_run(
            agent_name="investment_kompass",
            agent_deps=deps,
        )
        run = repo.get_latest_run("investment_kompass")
        assert run["agent_deps"] == deps


class TestAgentRunsRetrieval:
    """Test retrieving agent execution records."""

    def test_get_latest_run(self, repo):
        """get_latest_run returns the most recent run for an agent."""
        repo.log_run(agent_name="test_agent", output_summary="Run 1")
        repo.log_run(agent_name="test_agent", output_summary="Run 2")
        repo.log_run(agent_name="other_agent", output_summary="Run 3")

        latest = repo.get_latest_run("test_agent")
        assert latest is not None
        assert latest["agent_name"] == "test_agent"
        assert latest["output_summary"] == "Run 2"

    def test_get_latest_run_nonexistent(self, repo):
        """get_latest_run returns None for nonexistent agent."""
        result = repo.get_latest_run("nonexistent_agent")
        assert result is None

    def test_get_recent_runs(self, repo):
        """get_recent_runs returns multiple runs ordered by newest first."""
        for i in range(5):
            repo.log_run(agent_name=f"agent_{i % 2}", output_summary=f"Run {i}")

        recent = repo.get_recent_runs(limit=10)
        assert len(recent) == 5
        # Most recent first
        assert recent[0]["output_summary"] == "Run 4"
        assert recent[-1]["output_summary"] == "Run 0"

    def test_get_recent_runs_limit(self, repo):
        """get_recent_runs respects limit parameter."""
        for i in range(20):
            repo.log_run(agent_name="agent", output_summary=f"Run {i}")

        recent = repo.get_recent_runs(limit=5)
        assert len(recent) == 5
        assert recent[0]["output_summary"] == "Run 19"  # Most recent

    def test_get_runs_for_agents(self, repo):
        """get_runs_for_agents filters by agent names."""
        repo.log_run(agent_name="portfolio_story", output_summary="Story run")
        repo.log_run(agent_name="watchlist_checker", output_summary="Watchlist run")
        repo.log_run(agent_name="storychecker", output_summary="Checker run")

        runs = repo.get_runs_for_agents(["portfolio_story", "watchlist_checker"])
        assert len(runs) == 2
        agent_names = {r["agent_name"] for r in runs}
        assert agent_names == {"portfolio_story", "watchlist_checker"}


class TestAgentRunsPersistence:
    """Test that data persists correctly."""

    def test_runs_persist_across_queries(self, repo):
        """Logged runs persist across multiple get_* calls."""
        run_id = repo.log_run(
            agent_name="test_agent",
            model="test-model",
            skills_used=["skill1"],
            agent_deps=["dep1"],
            output_summary="Test",
        )

        # Query multiple times
        run1 = repo.get_latest_run("test_agent")
        run2 = repo.get_latest_run("test_agent")
        recent = repo.get_recent_runs(limit=1)

        assert run1 == run2
        assert run1["id"] == run_id
        assert recent[0]["skills_used"] == ["skill1"]
        assert recent[0]["agent_deps"] == ["dep1"]

    def test_json_arrays_roundtrip(self, repo):
        """JSON arrays in skills_used and agent_deps roundtrip correctly."""
        skills = ["A", "B", "C"]
        deps = ["X", "Y"]

        repo.log_run(
            agent_name="test",
            skills_used=skills,
            agent_deps=deps,
        )

        run = repo.get_latest_run("test")
        assert run["skills_used"] == skills
        assert run["agent_deps"] == deps
        assert isinstance(run["skills_used"], list)
        assert isinstance(run["agent_deps"], list)
