"""Unit tests for CapitalAllocatorRepository."""

from __future__ import annotations

import sqlite3

import pytest

from core.storage.base import init_db, migrate_db
from core.storage.capital_allocator import CapitalAllocatorRepository


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
    return CapitalAllocatorRepository(conn)


class TestCapitalAllocatorRepository:

    def test_create_session(self, repo):
        session = repo.create_session(
            position_id=1,
            ticker="AAPL",
            position_name="Apple",
            skill_name="Standard",
        )
        assert session.id is not None
        assert session.position_id == 1
        assert session.ticker == "AAPL"
        assert session.position_name == "Apple"
        assert session.skill_name == "Standard"

    def test_get_session(self, repo):
        created = repo.create_session(
            position_id=2, ticker="MSFT", position_name="Microsoft", skill_name="Standard"
        )
        fetched = repo.get_session(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.position_name == "Microsoft"

    def test_get_session_returns_none_for_unknown(self, repo):
        assert repo.get_session(9999) is None

    def test_list_sessions_empty(self, repo):
        assert repo.list_sessions() == []

    def test_list_sessions_ordered_newest_first(self, repo):
        s1 = repo.create_session(1, "AAPL", "Apple", "Standard")
        s2 = repo.create_session(2, "MSFT", "Microsoft", "Standard")
        sessions = repo.list_sessions()
        assert len(sessions) == 2
        assert sessions[0].id == s2.id
        assert sessions[1].id == s1.id

    def test_add_and_get_messages(self, repo):
        session = repo.create_session(1, "AAPL", "Apple", "Standard")
        msg = repo.add_message(session.id, "user", "Analyse diese Position.")
        assert msg.id is not None
        assert msg.role == "user"
        assert msg.content == "Analyse diese Position."

        messages = repo.get_messages(session.id)
        assert len(messages) == 1
        assert messages[0].content == "Analyse diese Position."

    def test_get_messages_multiple(self, repo):
        session = repo.create_session(1, "AAPL", "Apple", "Standard")
        repo.add_message(session.id, "user", "Frage")
        repo.add_message(session.id, "assistant", "Antwort")

        messages = repo.get_messages(session.id)
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    def test_delete_session(self, repo):
        session = repo.create_session(1, "AAPL", "Apple", "Standard")
        repo.add_message(session.id, "user", "Test")

        repo.delete_session(session.id)

        assert repo.get_session(session.id) is None
        assert repo.get_messages(session.id) == []

    def test_session_without_ticker(self, repo):
        session = repo.create_session(3, None, "Immobilienfonds XYZ", "Standard")
        fetched = repo.get_session(session.id)
        assert fetched is not None
        assert fetched.ticker is None
