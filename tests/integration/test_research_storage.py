"""
Integration tests for ResearchRepository.
Uses real SQLite in-memory — no mocking.
"""

import sqlite3
from datetime import datetime, timezone

import pytest

from core.storage.base import init_db
from core.storage.models import ResearchMessage, ResearchSession
from core.storage.research import ResearchRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    init_db(c)
    return c


@pytest.fixture
def repo(conn):
    return ResearchRepository(conn)


class TestCreateSession:
    def test_returns_session_with_id(self, repo):
        s = repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        assert s.id is not None
        assert s.ticker == "AAPL"
        assert s.strategy_name == "Value Investing"

    def test_ticker_uppercased(self, repo):
        s = repo.create_session("aapl", "Value Investing", strategy_prompt="Test prompt")
        assert s.ticker == "AAPL"

    def test_company_name_stored(self, repo):
        s = repo.create_session("AAPL", "Value Investing", company_name="Apple Inc.", strategy_prompt="Test prompt")
        fetched = repo.get_session(s.id)
        assert fetched.company_name == "Apple Inc."

    def test_company_name_optional(self, repo):
        s = repo.create_session("MSFT", "Growth", strategy_prompt="Test prompt")
        assert s.company_name is None

    def test_created_at_set(self, repo):
        s = repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        assert isinstance(s.created_at, datetime)


class TestGetSession:
    def test_get_existing_session(self, repo):
        created = repo.create_session("TSLA", "Wachstum 5-10 Jahre", strategy_prompt="Test prompt")
        fetched = repo.get_session(created.id)
        assert fetched is not None
        assert fetched.ticker == "TSLA"
        assert fetched.strategy_name == "Wachstum 5-10 Jahre"

    def test_get_nonexistent_returns_none(self, repo):
        assert repo.get_session(9999) is None


class TestListSessions:
    def test_returns_all_sessions(self, repo):
        repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        repo.create_session("MSFT", "Growth", strategy_prompt="Test prompt")
        sessions = repo.list_sessions()
        assert len(sessions) == 2

    def test_ordered_newest_first(self, repo):
        s1 = repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        s2 = repo.create_session("MSFT", "Growth", strategy_prompt="Test prompt")
        sessions = repo.list_sessions()
        assert sessions[0].id == s2.id
        assert sessions[1].id == s1.id

    def test_limit_respected(self, repo):
        for i in range(10):
            repo.create_session(f"T{i:02d}", "Value Investing", strategy_prompt="Test")
        sessions = repo.list_sessions(limit=3)
        assert len(sessions) == 3

    def test_empty_returns_empty_list(self, repo):
        assert repo.list_sessions() == []


class TestUpdateSummary:
    def test_summary_stored(self, repo):
        s = repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        repo.update_summary(s.id, "Strong buy — 30% undervalued.")
        fetched = repo.get_session(s.id)
        assert fetched.summary == "Strong buy — 30% undervalued."

    def test_summary_initially_none(self, repo):
        s = repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        assert repo.get_session(s.id).summary is None


class TestDeleteSession:
    def test_session_removed(self, repo):
        s = repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        repo.delete_session(s.id)
        assert repo.get_session(s.id) is None

    def test_messages_cascade_deleted(self, repo):
        s = repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        repo.add_message(s.id, "user", "Hello")
        repo.delete_session(s.id)
        assert repo.get_messages(s.id) == []


class TestAddMessage:
    def test_message_returned_with_id(self, repo):
        s = repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        msg = repo.add_message(s.id, "user", "Analysiere Apple.")
        assert msg.id is not None
        assert msg.role == "user"
        assert msg.content == "Analysiere Apple."
        assert msg.session_id == s.id

    def test_multiple_roles(self, repo):
        s = repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        repo.add_message(s.id, "user", "Frage")
        repo.add_message(s.id, "assistant", "Antwort")
        repo.add_message(s.id, "tool", "Suchergebnis")
        msgs = repo.get_messages(s.id)
        assert [m.role for m in msgs] == ["user", "assistant", "tool"]


class TestGetMessages:
    def test_chronological_order(self, repo):
        s = repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        repo.add_message(s.id, "user", "Erste Nachricht")
        repo.add_message(s.id, "assistant", "Zweite Nachricht")
        msgs = repo.get_messages(s.id)
        assert msgs[0].content == "Erste Nachricht"
        assert msgs[1].content == "Zweite Nachricht"

    def test_empty_for_new_session(self, repo):
        s = repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        assert repo.get_messages(s.id) == []

    def test_messages_isolated_per_session(self, repo):
        s1 = repo.create_session("AAPL", "Value Investing", strategy_prompt="Test prompt")
        s2 = repo.create_session("MSFT", "Growth", strategy_prompt="Test prompt")
        repo.add_message(s1.id, "user", "AAPL Frage")
        repo.add_message(s2.id, "user", "MSFT Frage")
        assert len(repo.get_messages(s1.id)) == 1
        assert repo.get_messages(s1.id)[0].content == "AAPL Frage"
