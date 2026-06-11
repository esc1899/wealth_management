"""
Unit tests for core/storage/research_queue.py.
Uses real SQLite :memory: — no mocking.
"""

import sqlite3
import pytest

from core.storage.base import init_db, migrate_db
from core.storage.research_queue import ResearchQueueRepository, ResearchRequest, ResearchAnswer


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
# Request CRUD
# ---------------------------------------------------------------------------

class TestCreateRequest:
    def test_creates_open_request(self, repo):
        req = repo.create_request("Analyse Q3-Zahlen", ticker="AAPL")
        assert req.id is not None
        assert req.status == "open"
        assert req.ticker == "AAPL"
        assert req.source == "manual"
        assert req.request_type == "research_question"

    def test_custom_fields(self, repo):
        req = repo.create_request(
            "Deep dive",
            request_type="analysis_deepdive",
            ticker="MSFT",
            context="DA-Verdict: kritisch",
            source="agent",
        )
        assert req.request_type == "analysis_deepdive"
        assert req.context == "DA-Verdict: kritisch"
        assert req.source == "agent"

    def test_invalid_request_type_raises(self, repo):
        with pytest.raises(ValueError, match="request_type"):
            repo.create_request("test", request_type="invalid_type")

    def test_invalid_source_raises(self, repo):
        with pytest.raises(ValueError, match="source"):
            repo.create_request("test", source="unknown")

    def test_no_ticker(self, repo):
        req = repo.create_request("General question")
        assert req.ticker is None

    def test_focus_exactly_500_chars_ok(self, repo):
        req = repo.create_request("x" * 500)
        assert req.id is not None

    def test_focus_501_chars_raises(self, repo):
        with pytest.raises(ValueError, match="focus"):
            repo.create_request("x" * 501)

    def test_context_exactly_2000_chars_ok(self, repo):
        req = repo.create_request("Test", context="y" * 2000)
        assert req.context == "y" * 2000

    def test_context_2001_chars_raises(self, repo):
        with pytest.raises(ValueError, match="context"):
            repo.create_request("Test", context="y" * 2001)

    def test_context_none_not_validated(self, repo):
        req = repo.create_request("Test", context=None)
        assert req.context is None


class TestListRequests:
    def test_list_open_empty(self, repo):
        assert repo.list_open_requests() == []

    def test_list_open_returns_only_open(self, repo):
        r1 = repo.create_request("Open 1")
        r2 = repo.create_request("Open 2")
        repo.complete_request(r1.id)

        open_reqs = repo.list_open_requests()
        assert len(open_reqs) == 1
        assert open_reqs[0].id == r2.id

    def test_list_all_includes_done(self, repo):
        r1 = repo.create_request("Open")
        r2 = repo.create_request("Done")
        repo.complete_request(r2.id)

        all_reqs = repo.list_all_requests()
        assert len(all_reqs) == 2
        statuses = {r.id: r.status for r in all_reqs}
        assert statuses[r1.id] == "open"
        assert statuses[r2.id] == "done"

    def test_list_open_ordered_by_created_at(self, repo):
        r1 = repo.create_request("First")
        r2 = repo.create_request("Second")
        r3 = repo.create_request("Third")

        open_reqs = repo.list_open_requests()
        ids = [r.id for r in open_reqs]
        assert ids == [r1.id, r2.id, r3.id]


class TestCompleteRequest:
    def test_marks_as_done(self, repo):
        req = repo.create_request("Test")
        result = repo.complete_request(req.id)
        assert result is True
        updated = repo.get_request(req.id)
        assert updated.status == "done"

    def test_already_done_returns_false(self, repo):
        req = repo.create_request("Test")
        repo.complete_request(req.id)
        result = repo.complete_request(req.id)
        assert result is False

    def test_nonexistent_id_returns_false(self, repo):
        result = repo.complete_request(99999)
        assert result is False


class TestDeleteRequest:
    def test_delete_removes_request(self, repo):
        req = repo.create_request("To be deleted")
        repo.delete_request(req.id)
        assert repo.get_request(req.id) is None

    def test_delete_nonexistent_returns_false(self, repo):
        result = repo.delete_request(99999)
        assert result is False


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

    def test_links_to_request(self, repo):
        req = repo.create_request("Deep dive", ticker="MSFT")
        answer = repo.submit_answer("Answer text", request_id=req.id, ticker="MSFT")
        assert answer.request_id == req.id

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
    def test_request_ticker_20_chars_ok(self, repo):
        req = repo.create_request("test", ticker="A" * 20)
        assert req.ticker == "A" * 20

    def test_request_ticker_21_chars_raises(self, repo):
        with pytest.raises(ValueError, match="ticker"):
            repo.create_request("test", ticker="A" * 21)

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
