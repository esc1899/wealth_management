"""
Unit tests for core/storage/research_queue.py.
Uses real SQLite :memory: — no mocking.
"""

import sqlite3
import pytest

from core.storage.base import init_db, migrate_db
from core.storage.research_queue import ResearchQueueRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.execute("PRAGMA foreign_keys=ON")
    init_db(c)
    migrate_db(c)
    return c


@pytest.fixture
def repo(conn):
    return ResearchQueueRepository(conn)


# ---------------------------------------------------------------------------
# Answer CRUD
# ---------------------------------------------------------------------------

class TestSubmitAnswer:
    def test_creates_answer(self, repo):
        answer = repo.submit_answer("## Analysis\nResult here", ticker="AAPL")
        assert answer.id is not None
        assert answer.ticker == "AAPL"
        assert answer.answer_md == "## Analysis\nResult here"
        assert answer.request_id is None

    def test_no_ticker(self, repo):
        answer = repo.submit_answer("General research finding")
        assert answer.ticker is None


class TestListAnswers:
    def test_list_all_empty(self, repo):
        assert repo.list_answers() == []

    def test_list_all_returns_answers(self, repo):
        repo.submit_answer("Answer 1", ticker="AAPL")
        repo.submit_answer("Answer 2", ticker="MSFT")
        answers = repo.list_answers()
        assert len(answers) == 2

    def test_filter_by_ticker(self, repo):
        repo.submit_answer("AAPL answer", ticker="AAPL")
        repo.submit_answer("MSFT answer", ticker="MSFT")
        repo.submit_answer("No ticker")

        aapl_answers = repo.list_answers(ticker="AAPL")
        assert len(aapl_answers) == 1
        assert aapl_answers[0].ticker == "AAPL"

    def test_filter_by_ticker_none_matches_all(self, repo):
        repo.submit_answer("A1", ticker="AAPL")
        repo.submit_answer("A2", ticker="MSFT")
        assert len(repo.list_answers()) == 2


class TestDeleteAnswer:
    def test_delete_removes_answer(self, repo):
        answer = repo.submit_answer("To delete")
        repo.delete_answer(answer.id)
        assert repo.get_answer(answer.id) is None

    def test_delete_nonexistent_returns_false(self, repo):
        result = repo.delete_answer(99999)
        assert result is False


# ---------------------------------------------------------------------------
# SEC-5 (e): Limits am Repo-Schreibpfad — synchron mit MCP-Server
# ---------------------------------------------------------------------------

class TestInputLimits:
    def test_answer_ticker_20_chars_ok(self, repo):
        assert repo.submit_answer("ok", ticker="A" * 20).ticker == "A" * 20

    def test_answer_exactly_100kb_ok(self, repo):
        answer = repo.submit_answer("x" * 100_000)
        assert answer.id is not None

    def test_answer_over_100kb_raises(self, repo):
        with pytest.raises(ValueError, match="answer_md"):
            repo.submit_answer("x" * 100_001)

    def test_answer_empty_raises(self, repo):
        with pytest.raises(ValueError, match="answer_md"):
            repo.submit_answer("   ")

    def test_answer_ticker_21_chars_raises(self, repo):
        with pytest.raises(ValueError, match="ticker"):
            repo.submit_answer("ok", ticker="A" * 21)

    def test_limits_match_mcp_server(self):
        """Beide Schreibpfade (Repo + MCP-Server) müssen dieselben Limits haben."""
        from core.storage import research_queue as rq
        from mcp_server import _helpers as mcp_helpers
        assert rq.MAX_TICKER_LEN == mcp_helpers.MAX_TICKER_LEN
        assert rq.MAX_ANSWER_BYTES == mcp_helpers.MAX_ANSWER_BYTES


class TestListAnswersForTicker:
    """Basis-Symbol-Matching: Co-Pilot kennt die Börsensuffix-Notation nicht (SAP vs SAP.DE)."""

    def test_plain_ticker_matches_suffixed_position(self, repo):
        repo.submit_answer("SAP Deep-Dive.", ticker="SAP")
        answers = repo.list_answers_for_ticker("SAP.DE")
        assert len(answers) == 1

    def test_suffixed_answer_matches_plain_lookup(self, repo):
        repo.submit_answer("SAP Deep-Dive.", ticker="SAP.DE")
        answers = repo.list_answers_for_ticker("SAP")
        assert len(answers) == 1

    def test_exact_match_still_works(self, repo):
        repo.submit_answer("Antwort.", ticker="NOVO-B.CO")
        assert len(repo.list_answers_for_ticker("NOVO-B.CO")) == 1

    def test_hyphen_share_class_matches(self, repo):
        repo.submit_answer("Antwort.", ticker="NOVO-B")
        assert len(repo.list_answers_for_ticker("NOVO-B.CO")) == 1

    def test_no_false_positive_on_different_base(self, repo):
        repo.submit_answer("Antwort.", ticker="SAPX")
        assert repo.list_answers_for_ticker("SAP.DE") == []

    def test_case_insensitive(self, repo):
        repo.submit_answer("Antwort.", ticker="sap")
        assert len(repo.list_answers_for_ticker("SAP.DE")) == 1

    def test_answers_without_ticker_excluded(self, repo):
        repo.submit_answer("Antwort ohne Ticker.")
        assert repo.list_answers_for_ticker("SAP.DE") == []
