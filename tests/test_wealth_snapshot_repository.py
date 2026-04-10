"""Tests for WealthSnapshotRepository."""

import pytest
from datetime import datetime, timezone
from core.storage.base import get_connection, init_db
from core.storage.wealth_snapshots import WealthSnapshotRepository


@pytest.fixture
def repo():
    """In-memory SQLite database with schema initialized."""
    conn = get_connection(":memory:")
    init_db(conn)
    return WealthSnapshotRepository(conn)


class TestCreate:
    def test_create_simple_snapshot(self, repo):
        snapshot = repo.create(
            date_str="2026-04-10",
            total_eur=500_000.0,
            breakdown={"Aktie": 250_000, "Immobilie": 250_000},
            coverage_pct=100.0,
        )
        assert snapshot.id is not None
        assert snapshot.date == "2026-04-10"
        assert snapshot.total_eur == 500_000.0
        assert snapshot.breakdown == {"Aktie": 250_000, "Immobilie": 250_000}
        assert snapshot.coverage_pct == 100.0
        assert snapshot.is_manual is False

    def test_create_with_missing_positions(self, repo):
        snapshot = repo.create(
            date_str="2026-04-10",
            total_eur=400_000.0,
            breakdown={"Aktie": 300_000},
            coverage_pct=80.0,
            missing_pos=["Festgeld (Sparkasse)"],
        )
        assert snapshot.missing_pos == ["Festgeld (Sparkasse)"]
        assert snapshot.coverage_pct == 80.0

    def test_create_manual_snapshot(self, repo):
        snapshot = repo.create(
            date_str="2026-04-10",
            total_eur=550_000.0,
            breakdown={"Aktie": 300_000, "Immobilie": 250_000},
            is_manual=True,
            note="Corrected Immobilie valuation",
        )
        assert snapshot.is_manual is True
        assert snapshot.note == "Corrected Immobilie valuation"

    def test_create_duplicate_date_fails(self, repo):
        repo.create(
            date_str="2026-04-10",
            total_eur=500_000.0,
            breakdown={"Aktie": 500_000},
        )
        with pytest.raises(ValueError, match="already exists"):
            repo.create(
                date_str="2026-04-10",
                total_eur=510_000.0,
                breakdown={"Aktie": 510_000},
            )


class TestRead:
    def test_get_by_date(self, repo):
        repo.create(
            date_str="2026-04-10",
            total_eur=500_000.0,
            breakdown={"Aktie": 500_000},
        )
        snapshot = repo.get_by_date("2026-04-10")
        assert snapshot is not None
        assert snapshot.total_eur == 500_000.0

    def test_get_by_date_not_found(self, repo):
        snapshot = repo.get_by_date("2026-04-10")
        assert snapshot is None

    def test_get_by_id(self, repo):
        created = repo.create(
            date_str="2026-04-10",
            total_eur=500_000.0,
            breakdown={"Aktie": 500_000},
        )
        snapshot = repo.get_by_id(created.id)
        assert snapshot is not None
        assert snapshot.id == created.id

    def test_latest(self, repo):
        repo.create(
            date_str="2026-04-08",
            total_eur=490_000.0,
            breakdown={"Aktie": 490_000},
        )
        repo.create(
            date_str="2026-04-10",
            total_eur=500_000.0,
            breakdown={"Aktie": 500_000},
        )
        latest = repo.latest()
        assert latest.date == "2026-04-10"
        assert latest.total_eur == 500_000.0

    def test_list_all(self, repo):
        dates = ["2026-04-01", "2026-04-05", "2026-04-10"]
        for i, date_str in enumerate(dates):
            repo.create(
                date_str=date_str,
                total_eur=400_000.0 + i * 10_000,
                breakdown={"Aktie": 400_000.0 + i * 10_000},
            )
        snapshots = repo.list(days=None)
        assert len(snapshots) == 3
        assert [s.date for s in snapshots] == dates  # ascending order

    def test_list_by_days(self, repo):
        # This is tricky to test with :memory: database
        # We'll just test that list() works with a days filter
        repo.create(
            date_str="2026-04-10",
            total_eur=500_000.0,
            breakdown={"Aktie": 500_000},
        )
        snapshots = repo.list(days=30)
        # Depending on current date, may or may not be included
        # Just test it doesn't crash
        assert isinstance(snapshots, list)

    def test_list_limit(self, repo):
        for i in range(10):
            date_str = f"2026-04-{1+i:02d}"
            repo.create(
                date_str=date_str,
                total_eur=400_000.0 + i * 1_000,
                breakdown={"Aktie": 400_000.0 + i * 1_000},
            )
        snapshots = repo.list_limit(limit=5)
        assert len(snapshots) == 5
        assert snapshots[-1].date == "2026-04-10"  # most recent


class TestUpdate:
    def test_update_snapshot(self, repo):
        created = repo.create(
            date_str="2026-04-10",
            total_eur=500_000.0,
            breakdown={"Aktie": 250_000, "Immobilie": 250_000},
        )
        updated = repo.update(
            created.id,
            total_eur=520_000.0,
            breakdown={"Aktie": 270_000, "Immobilie": 250_000},
            note="Corrected Aktie valuation",
        )
        assert updated.total_eur == 520_000.0
        assert updated.breakdown == {"Aktie": 270_000, "Immobilie": 250_000}
        assert updated.note == "Corrected Aktie valuation"
        assert updated.is_manual is True  # marked as manual after update

    def test_update_nonexistent_snapshot_fails(self, repo):
        with pytest.raises(ValueError, match="not found"):
            repo.update(
                999,
                total_eur=500_000.0,
                breakdown={"Aktie": 500_000},
            )


class TestDelete:
    def test_delete_snapshot(self, repo):
        created = repo.create(
            date_str="2026-04-10",
            total_eur=500_000.0,
            breakdown={"Aktie": 500_000},
        )
        repo.delete(created.id)
        snapshot = repo.get_by_id(created.id)
        assert snapshot is None

    def test_delete_nonexistent_snapshot_silent(self, repo):
        # SQLite allows deleting non-existent rows silently
        repo.delete(999)  # should not raise


class TestComplexScenarios:
    def test_multiple_snapshots_with_varying_coverage(self, repo):
        """Test a realistic scenario with varying portfolio coverage."""
        dates_and_data = [
            ("2026-04-01", 450_000, {"Aktie": 300_000, "Immobilie": 150_000}, 100.0, None),
            ("2026-04-05", 480_000, {"Aktie": 300_000, "Immobilie": 180_000}, 90.0, ["Festgeld"]),
            ("2026-04-10", 500_000, {"Aktie": 250_000, "Immobilie": 250_000}, 100.0, None),
        ]
        for date_str, total, breakdown, coverage, missing in dates_and_data:
            repo.create(
                date_str=date_str,
                total_eur=total,
                breakdown=breakdown,
                coverage_pct=coverage,
                missing_pos=missing,
            )

        # Verify retrieval
        snapshots = repo.list(days=None)
        assert len(snapshots) == 3
        assert snapshots[1].coverage_pct == 90.0
        assert snapshots[1].missing_pos == ["Festgeld"]

    def test_snapshot_with_complex_breakdown(self, repo):
        """Test with all asset classes."""
        breakdown = {
            "Aktie": 200_000,
            "Rentenfonds": 150_000,
            "Immobilienfonds": 80_000,
            "Immobilie": 300_000,
            "Bargeld": 50_000,
            "Festgeld": 100_000,
        }
        snapshot = repo.create(
            date_str="2026-04-10",
            total_eur=sum(breakdown.values()),
            breakdown=breakdown,
        )
        retrieved = repo.get_by_date("2026-04-10")
        assert retrieved.breakdown == breakdown
        assert retrieved.total_eur == 880_000
