"""
Unit tests for NewsRepository.
Uses an in-memory SQLite database — no file I/O.
"""

import sqlite3

import pytest

from core.storage.base import init_db
from core.storage.news import NewsRepository


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    return c


@pytest.fixture
def repo(conn):
    return NewsRepository(conn)


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

class TestNewsRepository:
    def test_save_and_get_run(self, repo):
        run = repo.save_run("Long-term Investor", ["AAPL", "MSFT"], "## AAPL\n- Good news")
        fetched = repo.get_run(run.id)
        assert fetched is not None
        assert fetched.skill_name == "Long-term Investor"
        assert fetched.tickers == "AAPL, MSFT"
        assert "Good news" in fetched.result

    def test_get_nonexistent_returns_none(self, repo):
        assert repo.get_run(999) is None

    def test_list_runs_ordered_by_created_desc(self, repo):
        r1 = repo.save_run("Skill A", ["AAPL"], "Result 1")
        r2 = repo.save_run("Skill B", ["MSFT"], "Result 2")
        runs = repo.list_runs()
        assert runs[0].id == r2.id
        assert runs[1].id == r1.id

    def test_list_runs_respects_limit(self, repo):
        for i in range(5):
            repo.save_run(f"Skill {i}", ["AAPL"], f"Result {i}")
        runs = repo.list_runs(limit=3)
        assert len(runs) == 3

    def test_delete_run(self, repo):
        run = repo.save_run("Skill", ["AAPL"], "Result")
        repo.delete_run(run.id)
        assert repo.get_run(run.id) is None

    def test_tickers_stored_as_comma_separated(self, repo):
        run = repo.save_run("Skill", ["AAPL", "SAP.DE", "MSFT"], "Result")
        assert run.tickers == "AAPL, SAP.DE, MSFT"

    def test_empty_tickers_list(self, repo):
        run = repo.save_run("Skill", [], "No positions.")
        assert run.tickers == ""
