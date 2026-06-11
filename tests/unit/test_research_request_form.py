"""
Unit tests for core/ui/research_request_form.py (FEAT-54).

Uses AppTest.from_function with a real SQLite :memory: repository — no mocking.
"""

import sqlite3

import pytest
from streamlit.testing.v1 import AppTest

from core.storage.base import init_db, migrate_db
from core.storage.research_queue import ResearchQueueRepository

def _make_app(db_path: str, **form_kwargs):
    """Build an AppTest script that renders the form against a file-backed DB.

    AppTest scripts run in a separate exec context, so the repo must be
    reconstructable from a path (no object passing).
    """
    kwargs_repr = ", ".join(f"{k}={v!r}" for k, v in form_kwargs.items())
    source = f"""
import sqlite3
import streamlit as st
from core.storage.research_queue import ResearchQueueRepository
from core.ui.research_request_form import render_research_request_form

conn = sqlite3.connect({db_path!r}, check_same_thread=False)
repo = ResearchQueueRepository(conn)
render_research_request_form(repo, {kwargs_repr})
"""
    return AppTest.from_string(source)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    init_db(conn)
    migrate_db(conn)
    conn.close()
    return path


def _open_requests(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT focus, request_type, ticker, context FROM research_requests "
        "WHERE status = 'open'"
    ).fetchall()
    conn.close()
    return rows


class TestFixedTicker:
    """Position-Dashboard variant: ticker fixed, no ticker field."""

    def test_renders_without_exception(self, db_path):
        at = _make_app(db_path, ticker="NVDA").run()
        assert not at.exception

    def test_no_ticker_field_shown(self, db_path):
        at = _make_app(db_path, ticker="NVDA").run()
        # Only the context text_input — no ticker input
        assert len(at.text_input) == 1

    def test_submit_creates_request_with_ticker(self, db_path):
        at = _make_app(db_path, ticker="NVDA").run()
        at.text_area[0].set_value("Wettbewerbsposition nach Q3 prüfen")
        at.button[0].set_value(True).run()
        rows = _open_requests(db_path)
        assert len(rows) == 1
        focus, req_type, ticker, context = rows[0]
        assert focus == "Wettbewerbsposition nach Q3 prüfen"
        assert req_type == "research_question"
        assert ticker == "NVDA"
        assert context is None

    def test_empty_focus_creates_nothing(self, db_path):
        at = _make_app(db_path, ticker="NVDA").run()
        at.button[0].set_value(True).run()
        assert _open_requests(db_path) == []
        assert len(at.warning) == 1


class TestFreeTextTicker:
    """Research-Answers variant: optional free-text ticker field."""

    def test_renders_ticker_field(self, db_path):
        at = _make_app(db_path, show_ticker_field=True).run()
        # Ticker input + context input
        assert len(at.text_input) == 2

    def test_submit_without_ticker(self, db_path):
        at = _make_app(db_path, show_ticker_field=True).run()
        at.text_area[0].set_value("Wie entwickelt sich der Halbleitersektor?")
        at.button[0].set_value(True).run()
        rows = _open_requests(db_path)
        assert len(rows) == 1
        assert rows[0][2] is None  # ticker

    def test_submit_with_ticker_uppercased(self, db_path):
        at = _make_app(db_path, show_ticker_field=True).run()
        at.text_area[0].set_value("SpaceX IPO zeichnen?")
        at.text_input[0].set_value("spacex")
        at.button[0].set_value(True).run()
        rows = _open_requests(db_path)
        assert len(rows) == 1
        assert rows[0][2] == "SPACEX"

    def test_context_is_stored(self, db_path):
        at = _make_app(db_path, show_ticker_field=True).run()
        at.text_area[0].set_value("Frage mit Kontext")
        at.text_input[1].set_value("Anlass: News Digest")
        at.button[0].set_value(True).run()
        rows = _open_requests(db_path)
        assert rows[0][3] == "Anlass: News Digest"
