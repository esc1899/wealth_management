"""
Unit tests for WatchlistCheckerRepository.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import pytest

from core.storage.base import init_db, migrate_db
from core.storage.models import WatchlistCheckerAnalysis
from core.storage.watchlist_checker_repo import WatchlistCheckerRepository


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
    return WatchlistCheckerRepository(conn)


class TestWatchlistCheckerRepository:
    def test_save_and_get_latest(self, repo):
        """Test saving and retrieving latest analysis."""
        analysis = WatchlistCheckerAnalysis(
            summary="Test summary",
            full_text="Test full text",
            fit_counts={"sehr_passend": 2, "passend": 3},
            position_fits_json=json.dumps([{"position_id": 1, "verdict": "sehr_passend"}]),
            skill_name="Josef's Regel",
            model="qwen3:8b",
            created_at=datetime.now(),
        )

        saved = repo.save_analysis(analysis)

        assert saved.id is not None
        assert saved.summary == "Test summary"
        assert saved.model == "qwen3:8b"

        # Retrieve and verify
        latest = repo.get_latest_analysis()
        assert latest is not None
        assert latest.id == saved.id
        assert latest.summary == "Test summary"
        assert latest.skill_name == "Josef's Regel"

    def test_get_latest_returns_none_if_empty(self, repo):
        """Test that get_latest returns None if no analyses exist."""
        latest = repo.get_latest_analysis()
        assert latest is None

    def test_get_analysis_history(self, repo):
        """Test retrieving multiple analyses in order (newest first)."""
        # Save first analysis
        analysis1 = WatchlistCheckerAnalysis(
            summary="First",
            full_text="Text 1",
            fit_counts={"sehr_passend": 1},
            position_fits_json="[]",
            skill_name="Skill 1",
            model="model1",
            created_at=datetime.now(),
        )
        saved1 = repo.save_analysis(analysis1)

        # Save second analysis
        analysis2 = WatchlistCheckerAnalysis(
            summary="Second",
            full_text="Text 2",
            fit_counts={"sehr_passend": 2},
            position_fits_json="[]",
            skill_name="Skill 2",
            model="model2",
            created_at=datetime.now(),
        )
        saved2 = repo.save_analysis(analysis2)

        # Retrieve history (newest first)
        history = repo.get_analysis_history(limit=10)

        assert len(history) == 2
        assert history[0].id == saved2.id  # Newest first
        assert history[1].id == saved1.id
        assert history[0].summary == "Second"
        assert history[1].summary == "First"

    def test_fit_counts_stored_as_json(self, repo):
        """Test that fit_counts are properly stored and retrieved as JSON."""
        fit_counts = {"sehr_passend": 5, "passend": 3, "neutral": 2, "nicht_passend": 1}

        analysis = WatchlistCheckerAnalysis(
            summary="Test",
            full_text="Full",
            fit_counts=fit_counts,
            position_fits_json="[]",
            skill_name="Test",
            model="test",
            created_at=datetime.now(),
        )

        saved = repo.save_analysis(analysis)
        latest = repo.get_latest_analysis()

        assert latest is not None
        # fit_counts is already deserialized as a dict by the repo
        assert latest.fit_counts == fit_counts

    def test_position_fits_json_stored(self, repo):
        """Test that position fits are properly serialized and stored."""
        position_fits = [
            {"position_id": 1, "verdict": "sehr_passend", "summary": "Great fit"},
            {"position_id": 2, "verdict": "passend", "summary": "Good fit"},
        ]

        analysis = WatchlistCheckerAnalysis(
            summary="Test",
            full_text="Full",
            fit_counts={"sehr_passend": 1, "passend": 1},
            position_fits_json=json.dumps(position_fits),
            skill_name="Test",
            model="test",
            created_at=datetime.now(),
        )

        saved = repo.save_analysis(analysis)
        latest = repo.get_latest_analysis()

        assert latest is not None
        retrieved_fits = json.loads(latest.position_fits_json)
        assert len(retrieved_fits) == 2
        assert retrieved_fits[0]["position_id"] == 1
        assert retrieved_fits[0]["verdict"] == "sehr_passend"

    def test_optional_fields_can_be_none(self, repo):
        """Test that optional fields can be None."""
        analysis = WatchlistCheckerAnalysis(
            summary=None,
            full_text=None,
            fit_counts=None,
            position_fits_json=None,
            skill_name=None,
            model=None,
            created_at=datetime.now(),
        )

        saved = repo.save_analysis(analysis)
        latest = repo.get_latest_analysis()

        assert latest is not None
        assert latest.summary is None
        assert latest.full_text is None
        assert latest.skill_name is None
