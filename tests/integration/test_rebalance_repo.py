"""Integration tests for RebalanceRepository (sessions + messages roundtrip)."""

from __future__ import annotations

import sqlite3

import pytest

from core.storage.base import init_db, migrate_db
from core.storage.rebalance import RebalanceRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    init_db(c)
    migrate_db(c)
    return c


@pytest.fixture
def repo(conn):
    return RebalanceRepository(conn)


class TestSessionCRUD:
    def test_create_and_get_session(self, repo):
        session = repo.create_session(
            skill_name="Long Term Investor",
            skill_prompt="Hold for 10+ years.",
            portfolio_snapshot="### Portfolio\n- AAPL 50%",
        )
        assert session.id is not None

        fetched = repo.get_session(session.id)
        assert fetched is not None
        assert fetched.skill_name == "Long Term Investor"
        assert fetched.skill_prompt == "Hold for 10+ years."
        assert fetched.portfolio_snapshot == "### Portfolio\n- AAPL 50%"

    def test_get_unknown_session_returns_none(self, repo):
        assert repo.get_session(9999) is None

    def test_list_sessions_newest_first(self, repo):
        s1 = repo.create_session("A", "p", "snap1")
        s2 = repo.create_session("B", "p", "snap2")
        sessions = repo.list_sessions()
        ids = [s.id for s in sessions]
        assert ids.index(s2.id) < ids.index(s1.id)

    def test_list_sessions_carries_first_user_message(self, repo):
        """The list label uses the first user message, not the (often generic) skill name."""
        session = repo.create_session("Ohne Strategie", "", "snap")
        repo.add_message(session.id, "user", "Ich will Alphabet kaufen — was weicht?")
        repo.add_message(session.id, "assistant", "Apple wäre ein Kandidat …")
        listed = next(s for s in repo.list_sessions() if s.id == session.id)
        assert listed.first_message == "Ich will Alphabet kaufen — was weicht?"

    def test_list_sessions_first_message_none_without_messages(self, repo):
        session = repo.create_session("A", "p", "snap")
        listed = next(s for s in repo.list_sessions() if s.id == session.id)
        assert listed.first_message is None

    def test_delete_session_removes_messages(self, repo):
        session = repo.create_session("A", "p", "snap")
        repo.add_message(session.id, "user", "hi")
        repo.delete_session(session.id)
        assert repo.get_session(session.id) is None
        assert repo.get_messages(session.id) == []


class TestMessages:
    def test_add_and_get_messages_in_order(self, repo):
        session = repo.create_session("A", "p", "snap")
        repo.add_message(session.id, "user", "first")
        repo.add_message(session.id, "assistant", "second")
        msgs = repo.get_messages(session.id)
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert [m.content for m in msgs] == ["first", "second"]

    def test_messages_scoped_to_session(self, repo):
        s1 = repo.create_session("A", "p", "snap")
        s2 = repo.create_session("B", "p", "snap")
        repo.add_message(s1.id, "user", "only-s1")
        assert repo.get_messages(s2.id) == []
