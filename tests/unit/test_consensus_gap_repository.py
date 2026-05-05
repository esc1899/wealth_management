"""
Unit tests for ConsensusGapRepository.
Uses in-memory SQLite with both init_db and migrate_db (CG tables are in migrate_db).
"""

import sqlite3
from datetime import datetime

import pytest

from core.storage.base import init_db, migrate_db
from core.storage.consensus_gap import ConsensusGapRepository
from core.storage.models import ConsensusGapSession, ConsensusGapMessage


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    init_db(c)
    migrate_db(c)
    return c


@pytest.fixture
def repo(conn):
    return ConsensusGapRepository(conn)


# ------------------------------------------------------------------
# Sessions
# ------------------------------------------------------------------

class TestSessions:
    def test_create_and_get_session(self, repo):
        s = repo.create_session(position_id=1, ticker="AAPL", position_name="Apple", skill_name="Conservative")
        fetched = repo.get_session(s.id)
        assert fetched is not None
        assert fetched.position_id == 1
        assert fetched.ticker == "AAPL"
        assert fetched.position_name == "Apple"
        assert fetched.skill_name == "Conservative"

    def test_get_nonexistent_session_returns_none(self, repo):
        assert repo.get_session(999) is None

    def test_create_session_returns_with_id(self, repo):
        s = repo.create_session(position_id=1, ticker="MSFT", position_name="Microsoft", skill_name="Aggressive")
        assert s.id is not None
        assert isinstance(s.id, int)
        assert isinstance(s.created_at, datetime)

    def test_create_session_with_null_ticker(self, repo):
        s = repo.create_session(position_id=1, ticker=None, position_name="Unknown", skill_name="Default")
        fetched = repo.get_session(s.id)
        assert fetched.ticker is None

    def test_list_sessions_ordered_newest_first(self, repo):
        s1 = repo.create_session(position_id=1, ticker="AAPL", position_name="Apple", skill_name="Conservative")
        s2 = repo.create_session(position_id=2, ticker="MSFT", position_name="Microsoft", skill_name="Aggressive")
        sessions = repo.list_sessions()
        assert len(sessions) >= 2
        assert sessions[0].id == s2.id
        assert sessions[1].id == s1.id

    def test_list_sessions_respects_limit(self, repo):
        for i in range(5):
            repo.create_session(
                position_id=i+1, ticker=f"TICK{i}", position_name=f"Pos{i}", skill_name="Test"
            )
        sessions = repo.list_sessions(limit=3)
        assert len(sessions) == 3

    def test_delete_session_removes_it(self, repo):
        s = repo.create_session(position_id=1, ticker="AAPL", position_name="Apple", skill_name="Conservative")
        repo.delete_session(s.id)
        assert repo.get_session(s.id) is None

    def test_delete_session_cascades_messages(self, repo):
        s = repo.create_session(position_id=1, ticker="AAPL", position_name="Apple", skill_name="Conservative")
        repo.add_message(s.id, "user", "Analyze this.")
        repo.add_message(s.id, "assistant", "Here's the analysis.")
        repo.delete_session(s.id)
        msgs = repo.get_messages(s.id)
        assert msgs == []

    def test_list_sessions_empty(self, repo):
        sessions = repo.list_sessions()
        assert sessions == []


# ------------------------------------------------------------------
# Messages
# ------------------------------------------------------------------

class TestMessages:
    def test_add_and_get_messages(self, repo):
        s = repo.create_session(position_id=1, ticker="AAPL", position_name="Apple", skill_name="Conservative")
        repo.add_message(s.id, "user", "Analyze consensus gap.")
        repo.add_message(s.id, "assistant", "The gap is stable.")
        msgs = repo.get_messages(s.id)
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[0].content == "Analyze consensus gap."
        assert msgs[1].role == "assistant"
        assert msgs[1].content == "The gap is stable."

    def test_messages_ordered_chronologically(self, repo):
        s = repo.create_session(position_id=1, ticker="AAPL", position_name="Apple", skill_name="Conservative")
        repo.add_message(s.id, "user", "First message")
        repo.add_message(s.id, "assistant", "Second message")
        msgs = repo.get_messages(s.id)
        assert msgs[0].content == "First message"
        assert msgs[1].content == "Second message"

    def test_messages_isolated_per_session(self, repo):
        s1 = repo.create_session(position_id=1, ticker="AAPL", position_name="Apple", skill_name="Conservative")
        s2 = repo.create_session(position_id=2, ticker="MSFT", position_name="Microsoft", skill_name="Aggressive")
        repo.add_message(s1.id, "user", "Session 1 message")
        repo.add_message(s2.id, "user", "Session 2 message")
        msgs1 = repo.get_messages(s1.id)
        msgs2 = repo.get_messages(s2.id)
        assert len(msgs1) == 1
        assert len(msgs2) == 1
        assert msgs1[0].content == "Session 1 message"
        assert msgs2[0].content == "Session 2 message"

    def test_get_messages_empty_for_new_session(self, repo):
        s = repo.create_session(position_id=1, ticker="AAPL", position_name="Apple", skill_name="Conservative")
        msgs = repo.get_messages(s.id)
        assert msgs == []

    def test_add_message_returns_with_id(self, repo):
        s = repo.create_session(position_id=1, ticker="AAPL", position_name="Apple", skill_name="Conservative")
        msg = repo.add_message(s.id, "user", "Test message")
        assert msg.id is not None
        assert isinstance(msg.created_at, datetime)
        assert msg.session_id == s.id


# ------------------------------------------------------------------
# Verdict JOIN
# ------------------------------------------------------------------

class TestVerdictJoin:
    def test_get_session_populates_verdict_from_position_analyses(self, repo, conn):
        """Test that get_session LEFT JOINs verdict from position_analyses."""
        # Create session
        s = repo.create_session(position_id=1, ticker="AAPL", position_name="Apple", skill_name="Conservative")

        # Manually insert a position_analyses record with this session_id
        conn.execute("""
            INSERT INTO position_analyses
            (position_id, agent, skill_name, verdict, summary, session_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (1, 'consensus_gap', 'Conservative', 'wächst', 'Growing gap', s.id))
        conn.commit()

        # Fetch session and check verdict is populated
        fetched = repo.get_session(s.id)
        assert fetched.verdict == 'wächst'

    def test_get_session_verdict_is_none_when_no_analyses(self, repo):
        """Test that verdict is None if no position_analyses record exists."""
        s = repo.create_session(position_id=1, ticker="AAPL", position_name="Apple", skill_name="Conservative")
        fetched = repo.get_session(s.id)
        assert fetched.verdict is None
