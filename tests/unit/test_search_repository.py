"""
Unit tests for SearchRepository.
Uses an in-memory SQLite database — no file I/O.
"""

import sqlite3

import pytest

from core.storage.base import init_db
from core.storage.search import SearchRepository


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
    return SearchRepository(conn)


# ------------------------------------------------------------------
# Sessions
# ------------------------------------------------------------------

class TestSessions:
    def test_create_and_get_session(self, repo):
        s = repo.create_session("European ETFs", "Fund Screener", "Focus on TER.")
        fetched = repo.get_session(s.id)
        assert fetched is not None
        assert fetched.query == "European ETFs"
        assert fetched.skill_name == "Fund Screener"

    def test_get_nonexistent_session_returns_none(self, repo):
        assert repo.get_session(999) is None

    def test_list_sessions_ordered_by_created_desc(self, repo):
        s1 = repo.create_session("ETFs", "Screener", "Prompt A")
        s2 = repo.create_session("Stocks", "Screener", "Prompt B")
        sessions = repo.list_sessions()
        assert sessions[0].id == s2.id
        assert sessions[1].id == s1.id

    def test_list_sessions_respects_limit(self, repo):
        for i in range(5):
            repo.create_session(f"Query {i}", "Screener", "Prompt")
        sessions = repo.list_sessions(limit=3)
        assert len(sessions) == 3

    def test_delete_session_removes_it(self, repo):
        s = repo.create_session("Stocks", "Screener", "Prompt")
        repo.delete_session(s.id)
        assert repo.get_session(s.id) is None

    def test_delete_session_removes_messages(self, repo):
        s = repo.create_session("Stocks", "Screener", "Prompt")
        repo.add_message(s.id, "user", "Hello")
        repo.delete_session(s.id)
        assert repo.get_messages(s.id) == []


# ------------------------------------------------------------------
# Messages
# ------------------------------------------------------------------

class TestMessages:
    def test_add_and_get_messages(self, repo):
        s = repo.create_session("Stocks", "Screener", "Prompt")
        repo.add_message(s.id, "user", "Find ETFs.")
        repo.add_message(s.id, "assistant", "Here are some ETFs.")
        msgs = repo.get_messages(s.id)
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"

    def test_messages_ordered_chronologically(self, repo):
        s = repo.create_session("Stocks", "Screener", "Prompt")
        repo.add_message(s.id, "user", "First")
        repo.add_message(s.id, "assistant", "Second")
        msgs = repo.get_messages(s.id)
        assert msgs[0].content == "First"
        assert msgs[1].content == "Second"

    def test_get_messages_empty_for_new_session(self, repo):
        s = repo.create_session("Stocks", "Screener", "Prompt")
        assert repo.get_messages(s.id) == []
