"""
Integration tests for Cowork Research Ingest — importer + repository.

Uses real SQLite :memory: and real temp filesystem. No mocking.
"""

import sqlite3
import shutil
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.storage.base import init_db
from core.storage.cowork import CoworkRepository
from core.cowork.importer import CoworkImporter
from core.cowork.parser import ParseError

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_research.md"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    init_db(c)
    return c


@pytest.fixture
def cowork_repo(conn):
    return CoworkRepository(conn)


@pytest.fixture
def mock_positions_repo():
    repo = MagicMock()
    repo.list_watchlist.return_value = []
    repo.get_watchlist.return_value = []
    return repo


@pytest.fixture
def outbox(tmp_path):
    ob = tmp_path / "outbox"
    ob.mkdir()
    return ob


@pytest.fixture
def importer(cowork_repo, mock_positions_repo, outbox):
    return CoworkImporter(
        cowork_repo=cowork_repo,
        positions_repo=mock_positions_repo,
        outbox_path=str(outbox),
        archive_subfolder="archive",
        auto_import_ready=True,
    )


# ---------------------------------------------------------------------------
# Repository tests
# ---------------------------------------------------------------------------

class TestCoworkRepository:
    def test_create_and_get_entry(self, cowork_repo):
        entry = cowork_repo.create_entry(
            research_id="test-001",
            type="stock_analysis",
            date=date(2026, 5, 8),
            model="test-model",
            status="draft",
            body_markdown="# Test",
            sources=["https://example.com"],
            disclaimer="Test disclaimer.",
        )
        assert entry.id is not None
        assert entry.research_id == "test-001"

        fetched = cowork_repo.get_entry(entry.id)
        assert fetched is not None
        assert fetched.research_id == "test-001"
        assert fetched.sources == ["https://example.com"]

    def test_get_by_research_id(self, cowork_repo):
        cowork_repo.create_entry(
            research_id="lookup-test",
            type="sector_scan",
            date=date(2026, 1, 1),
            model="m",
            status="draft",
            body_markdown="",
            sources=[],
            disclaimer="d",
        )
        found = cowork_repo.get_by_research_id("lookup-test")
        assert found is not None
        assert found.research_id == "lookup-test"

    def test_get_by_research_id_missing(self, cowork_repo):
        assert cowork_repo.get_by_research_id("nonexistent") is None

    def test_list_entries_filter_status(self, cowork_repo):
        cowork_repo.create_entry(
            research_id="e-draft", type="stock_analysis", date=date(2026, 5, 1),
            model="m", status="draft", body_markdown="", sources=[], disclaimer="d",
        )
        cowork_repo.create_entry(
            research_id="e-ready", type="stock_analysis", date=date(2026, 5, 2),
            model="m", status="ready_for_import", body_markdown="", sources=[], disclaimer="d",
        )
        drafts = cowork_repo.list_entries(status="draft")
        assert len(drafts) == 1
        assert drafts[0].research_id == "e-draft"

    def test_update_status(self, cowork_repo):
        entry = cowork_repo.create_entry(
            research_id="status-test", type="stock_analysis", date=date(2026, 5, 1),
            model="m", status="draft", body_markdown="", sources=[], disclaimer="d",
        )
        cowork_repo.update_status(entry.id, "imported")
        updated = cowork_repo.get_entry(entry.id)
        assert updated.status == "imported"
        assert updated.imported_at is not None

    def test_create_suggestion(self, cowork_repo):
        cowork_repo.create_entry(
            research_id="s-test", type="stock_analysis", date=date(2026, 5, 1),
            model="m", status="draft", body_markdown="", sources=[], disclaimer="d",
        )
        suggestion = cowork_repo.create_suggestion(
            research_id="s-test",
            ticker="AAPL",
            exchange="NASDAQ",
            name="Apple Inc.",
            rationale="Strong ecosystem.",
            conviction="high",
            suggested_action="add",
        )
        assert suggestion.id is not None
        assert suggestion.ticker == "AAPL"

    def test_list_suggestions_by_research_id(self, cowork_repo):
        cowork_repo.create_entry(
            research_id="s-list", type="stock_analysis", date=date(2026, 5, 1),
            model="m", status="draft", body_markdown="", sources=[], disclaimer="d",
        )
        cowork_repo.create_suggestion(
            research_id="s-list", ticker="AAPL", exchange="NASDAQ", name="Apple",
            rationale="r", conviction="high", suggested_action="add",
        )
        cowork_repo.create_suggestion(
            research_id="s-list", ticker="MSFT", exchange="NASDAQ", name="Microsoft",
            rationale="r", conviction="medium", suggested_action="watch",
        )
        subs = cowork_repo.list_suggestions(research_id="s-list")
        assert len(subs) == 2

    def test_update_suggestion_status(self, cowork_repo):
        cowork_repo.create_entry(
            research_id="sug-status", type="stock_analysis", date=date(2026, 5, 1),
            model="m", status="draft", body_markdown="", sources=[], disclaimer="d",
        )
        sug = cowork_repo.create_suggestion(
            research_id="sug-status", ticker="AAPL", exchange="NASDAQ", name="Apple",
            rationale="r", conviction="high", suggested_action="add",
        )
        cowork_repo.update_suggestion_status(sug.id, "accepted", reviewed_by="test-user")
        updated = cowork_repo.get_suggestion(sug.id)
        assert updated.status == "accepted"
        assert updated.reviewed_by == "test-user"
        assert updated.reviewed_at is not None


# ---------------------------------------------------------------------------
# Importer tests
# ---------------------------------------------------------------------------

class TestImporterWithFixture:
    def test_process_ready_for_import_file(self, importer, outbox, cowork_repo):
        dest = outbox / "2026-05-08-aapl-001.md"
        shutil.copy(FIXTURE_PATH, dest)

        result = importer.process_file(str(dest))

        assert result.success
        assert result.action == "stored_pending_review"
        assert result.candidates_added == 1   # AAPL → add (pending)
        assert result.candidates_queued == 1  # MSFT → watch (pending)

    def test_file_moved_to_archive(self, importer, outbox):
        dest = outbox / "2026-05-08-aapl-001.md"
        shutil.copy(FIXTURE_PATH, dest)

        importer.process_file(str(dest))

        assert not dest.exists()
        assert (outbox / "archive" / "2026-05-08-aapl-001.md").exists()

    def test_db_entry_status_remains_ready_for_import(self, importer, outbox, cowork_repo):
        """Entry stays ready_for_import until user confirms via UI."""
        dest = outbox / "2026-05-08-aapl-001.md"
        shutil.copy(FIXTURE_PATH, dest)

        importer.process_file(str(dest))

        entry = cowork_repo.get_by_research_id("2026-05-08-aapl-001")
        assert entry is not None
        assert entry.status == "ready_for_import"

    def test_candidates_stored_as_pending(self, importer, outbox, cowork_repo):
        """Candidates are stored with status=pending for UI review."""
        dest = outbox / "2026-05-08-aapl-001.md"
        shutil.copy(FIXTURE_PATH, dest)

        importer.process_file(str(dest))

        entry = cowork_repo.get_by_research_id("2026-05-08-aapl-001")
        suggestions = cowork_repo.list_suggestions(research_id=entry.research_id, status="pending")
        assert len(suggestions) == 2  # AAPL + MSFT both pending

    def test_reprocesses_if_status_changed_to_ready(self, importer, outbox, cowork_repo):
        """A draft entry that is marked ready_for_import must be processable (not skipped)."""
        # First pass: draft file → stored, not processed
        draft_text = FIXTURE_PATH.read_text().replace("status: ready_for_import", "status: draft")
        dest = outbox / "2026-05-08-aapl-001.md"
        dest.write_text(draft_text, encoding="utf-8")
        r1 = importer.process_file(str(dest))
        assert r1.action == "stored_draft"
        assert dest.exists()  # not archived

        # Simulate user marking as ready_for_import (file is updated)
        ready_text = draft_text.replace("status: draft", "status: ready_for_import")
        dest.write_text(ready_text, encoding="utf-8")

        # Second pass: should now store candidates, not skip
        r2 = importer.process_file(str(dest))
        assert r2.action == "stored_pending_review"
        assert r2.candidates_added == 1
        assert not dest.exists()  # archived

        entry = cowork_repo.get_by_research_id("2026-05-08-aapl-001")
        assert entry.status == "ready_for_import"  # not imported yet — UI confirms

    def test_idempotent_duplicate_research_id(self, importer, outbox, cowork_repo):
        dest = outbox / "2026-05-08-aapl-001.md"
        shutil.copy(FIXTURE_PATH, dest)
        importer.process_file(str(dest))
        # Entry is now ready_for_import in DB, file is archived

        # Copy file back (as if it reappeared in outbox)
        archive = outbox / "archive" / "2026-05-08-aapl-001.md"
        dest2 = outbox / "2026-05-08-aapl-001-copy.md"
        shutil.copy(archive, dest2)
        result2 = importer.process_file(str(dest2))

        assert result2.action == "skipped_duplicate"

    def test_dedup_against_existing_watchlist(self, outbox, cowork_repo, mock_positions_repo):
        # Simulate AAPL already in watchlist
        existing = MagicMock()
        existing.ticker = "AAPL"
        existing.extra_data = {"exchange": "NASDAQ"}
        mock_positions_repo.get_watchlist.return_value = [existing]

        imp = CoworkImporter(
            cowork_repo=cowork_repo,
            positions_repo=mock_positions_repo,
            outbox_path=str(outbox),
        )
        dest = outbox / "2026-05-08-aapl-001.md"
        shutil.copy(FIXTURE_PATH, dest)
        result = imp.process_file(str(dest))

        assert result.candidates_deduped == 1   # AAPL deduped
        assert result.candidates_queued == 1    # MSFT still pending


class TestImporterStatusRouting:
    def _write_file(self, outbox: Path, status: str, research_id: str) -> Path:
        text = f"""---
research_id: "{research_id}"
type: stock_analysis
date: 2026-05-08
ai_generated: true
model: test
status: {status}
disclaimer: Test disclaimer.
sources: []
watchlist_candidates: []
---

Body.
"""
        path = outbox / f"{research_id}.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_draft_stored_no_action(self, importer, outbox, cowork_repo):
        path = self._write_file(outbox, "draft", "draft-001")
        result = importer.process_file(str(path))
        assert result.action == "stored_draft"
        entry = cowork_repo.get_by_research_id("draft-001")
        assert entry is not None
        assert entry.status == "draft"

    def test_failed_stored_no_action(self, importer, outbox, cowork_repo):
        path = self._write_file(outbox, "failed", "failed-001")
        result = importer.process_file(str(path))
        assert result.action == "stored_failed"
        entry = cowork_repo.get_by_research_id("failed-001")
        assert entry.status == "failed"

    def test_already_imported_skipped(self, importer, outbox):
        path = self._write_file(outbox, "imported", "imported-001")
        result = importer.process_file(str(path))
        assert result.action == "skipped_already_imported"

    def test_ready_for_import_stores_pending_review(self, importer, outbox, cowork_repo):
        path = self._write_file(outbox, "ready_for_import", "ready-001")
        result = importer.process_file(str(path))
        assert result.action == "stored_pending_review"
        assert not path.exists()  # file archived


class TestImporterErrorHandling:
    def test_invalid_yaml_moves_to_invalid(self, importer, outbox):
        bad = outbox / "bad-001.md"
        bad.write_text("---\nbroken: [\n---\nbody", encoding="utf-8")
        result = importer.process_file(str(bad))
        assert not result.success
        assert result.action == "parse_failed"
        assert (outbox / ".invalid" / "bad-001.md").exists()
        assert not bad.exists()

    def test_missing_required_field_moves_to_invalid(self, importer, outbox):
        text = "---\nresearch_id: x\n---\nbody"  # missing all required fields
        path = outbox / "incomplete-001.md"
        path.write_text(text, encoding="utf-8")
        result = importer.process_file(str(path))
        assert not result.success
        assert (outbox / ".invalid" / "incomplete-001.md").exists()

    def test_nonexistent_file(self, importer, outbox):
        result = importer.process_file(str(outbox / "ghost.md"))
        assert not result.success
        assert result.action == "parse_failed"


class TestImporterScanOutbox:
    def test_scan_processes_all_md_files(self, importer, outbox, cowork_repo):
        for i in range(3):
            text = f"""---
research_id: "scan-{i:03d}"
type: stock_analysis
date: 2026-05-0{i+1}
ai_generated: true
model: test
status: draft
disclaimer: d.
sources: []
watchlist_candidates: []
---
Body.
"""
            (outbox / f"scan-{i:03d}.md").write_text(text, encoding="utf-8")

        results = importer.scan_outbox()
        assert len(results) == 3
        entries = cowork_repo.list_entries()
        assert len(entries) == 3

    def test_scan_empty_outbox(self, importer):
        results = importer.scan_outbox()
        assert results == []

    def test_scan_ignores_nonexistent_outbox(self, cowork_repo, mock_positions_repo, tmp_path):
        imp = CoworkImporter(
            cowork_repo=cowork_repo,
            positions_repo=mock_positions_repo,
            outbox_path=str(tmp_path / "does_not_exist"),
        )
        results = imp.scan_outbox()
        assert results == []
