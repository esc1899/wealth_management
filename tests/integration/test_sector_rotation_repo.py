"""Integration tests for SectorRotationRepository."""

from __future__ import annotations

import sqlite3

import pytest

from core.storage.base import init_db, migrate_db
from core.storage.sector_rotation import SectorRotationRepository


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
    return SectorRotationRepository(conn)


class TestSectorRotationRunCRUD:
    def test_save_and_get_run(self, repo):
        run = repo.save_run(skill_name="Standard", result="## Report content")
        assert run.id is not None
        assert run.skill_name == "Standard"
        assert run.result == "## Report content"

        fetched = repo.get_run(run.id)
        assert fetched is not None
        assert fetched.id == run.id
        assert fetched.skill_name == "Standard"
        assert fetched.result == "## Report content"

    def test_get_run_returns_none_for_unknown(self, repo):
        assert repo.get_run(9999) is None

    def test_get_recent_runs_empty(self, repo):
        assert repo.get_recent_runs() == []

    def test_get_recent_runs_ordered_newest_first(self, repo):
        r1 = repo.save_run("Skill1", "Report 1")
        r2 = repo.save_run("Skill2", "Report 2")
        r3 = repo.save_run("Skill3", "Report 3")

        recent = repo.get_recent_runs(limit=10)
        assert len(recent) == 3
        assert recent[0].id == r3.id
        assert recent[1].id == r2.id
        assert recent[2].id == r1.id

    def test_get_recent_runs_respects_limit(self, repo):
        for i in range(5):
            repo.save_run(f"Skill{i}", f"Report {i}")
        recent = repo.get_recent_runs(limit=3)
        assert len(recent) == 3


class TestSectorRotationMessages:
    def test_add_and_get_messages(self, repo):
        run = repo.save_run("Standard", "Report")
        msg = repo.add_message(run.id, "user", "What sectors?")
        assert msg.id is not None
        assert msg.run_id == run.id
        assert msg.role == "user"
        assert msg.content == "What sectors?"

    def test_get_messages_ordered_by_time(self, repo):
        run = repo.save_run("Standard", "Report")
        repo.add_message(run.id, "user", "Question")
        repo.add_message(run.id, "assistant", "Answer")

        msgs = repo.get_messages(run.id)
        assert len(msgs) == 2
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"

    def test_get_messages_empty_for_new_run(self, repo):
        run = repo.save_run("Standard", "Report")
        assert repo.get_messages(run.id) == []


class TestSectorVerdicts:
    def test_save_and_get_verdict(self, repo):
        run = repo.save_run("Standard", "Report")
        v = repo.save_verdict(
            run_id=run.id,
            sector="Technology",
            verdict="aligned",
            momentum="inflow",
            summary="Tech strong",
        )
        assert v.id is not None
        assert v.run_id == run.id
        assert v.sector == "Technology"
        assert v.verdict == "aligned"
        assert v.momentum == "inflow"
        assert v.summary == "Tech strong"

    def test_get_verdicts_for_run(self, repo):
        run = repo.save_run("Standard", "Report")
        repo.save_verdict(run.id, "Technology", "aligned", "inflow", "Tech strong")
        repo.save_verdict(run.id, "Energy", "overexposed", "outflow", "Energy fading")

        verdicts = repo.get_verdicts(run.id)
        assert len(verdicts) == 2
        sectors = {v.sector for v in verdicts}
        assert sectors == {"Technology", "Energy"}

    def test_get_verdicts_empty_for_new_run(self, repo):
        run = repo.save_run("Standard", "Report")
        assert repo.get_verdicts(run.id) == []

    def test_verdict_optional_fields(self, repo):
        run = repo.save_run("Standard", "Report")
        v = repo.save_verdict(run.id, "Healthcare", "lagging", momentum=None, summary=None)
        fetched = repo.get_verdicts(run.id)
        assert len(fetched) == 1
        assert fetched[0].momentum is None
        assert fetched[0].summary is None

    def test_verdicts_isolated_by_run(self, repo):
        r1 = repo.save_run("Skill1", "Report 1")
        r2 = repo.save_run("Skill2", "Report 2")
        repo.save_verdict(r1.id, "Technology", "aligned", "inflow", "Run 1 tech")
        repo.save_verdict(r2.id, "Energy", "lagging", "outflow", "Run 2 energy")

        v1 = repo.get_verdicts(r1.id)
        v2 = repo.get_verdicts(r2.id)
        assert len(v1) == 1
        assert v1[0].sector == "Technology"
        assert len(v2) == 1
        assert v2[0].sector == "Energy"
