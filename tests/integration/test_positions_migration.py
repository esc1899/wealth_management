"""
Integration tests for the migration script.
Seeds an in-memory DB with legacy portfolio + watchlist tables,
runs the migration logic, and verifies the positions table.
"""

import json
import os
import sqlite3
from datetime import date

import pytest

from core.encryption import EncryptionService
from core.storage.base import init_db
from core.storage.positions import PositionsRepository
from scripts.migrate_to_positions import migrate


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def enc():
    key = os.urandom(16).hex()
    salt = os.urandom(16)
    return EncryptionService(key, salt)


@pytest.fixture
def conn(enc):
    """In-memory DB with both old and new tables."""
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    init_db(c)  # creates positions table

    # Legacy tables (mirror the old schema exactly)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            name            TEXT NOT NULL,
            quantity        TEXT NOT NULL,
            purchase_price  TEXT,
            purchase_date   TEXT NOT NULL,
            asset_type      TEXT NOT NULL,
            notes           TEXT
        );
        CREATE TABLE IF NOT EXISTS watchlist (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol       TEXT NOT NULL,
            name         TEXT NOT NULL,
            notes        TEXT,
            target_price TEXT,
            added_date   TEXT NOT NULL,
            source       TEXT NOT NULL,
            asset_type   TEXT NOT NULL
        );
    """)
    return c


def seed_portfolio(conn, enc, symbol, name, asset_type, quantity, purchase_price, purchase_date, notes=None):
    conn.execute(
        """INSERT INTO portfolio (symbol, name, quantity, purchase_price, purchase_date, asset_type, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            symbol, name,
            enc.encrypt(str(quantity)),
            enc.encrypt(str(purchase_price)) if purchase_price else None,
            purchase_date,
            asset_type,
            enc.encrypt(notes) if notes else None,
        ),
    )
    conn.commit()


def seed_watchlist(conn, enc, symbol, name, asset_type, source="user", target_price=None, notes=None):
    conn.execute(
        """INSERT INTO watchlist (symbol, name, notes, target_price, added_date, source, asset_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            symbol, name,
            enc.encrypt(notes) if notes else None,
            enc.encrypt(str(target_price)) if target_price else None,
            date.today().isoformat(),
            source,
            asset_type,
        ),
    )
    conn.commit()


# ------------------------------------------------------------------
# Row count invariants
# ------------------------------------------------------------------

class TestRowCounts:
    def test_two_portfolio_one_watchlist(self, conn, enc):
        seed_portfolio(conn, enc, "SAP", "SAP SE", "stock", 10, 150.0, "2024-01-15")
        seed_portfolio(conn, enc, "MSFT", "Microsoft", "stock", 5, 300.0, "2024-02-01")
        seed_watchlist(conn, enc, "NVDA", "Nvidia", "stock")

        result = migrate(conn, enc, dry_run=False)

        assert result["portfolio_rows"] == 2
        assert result["watchlist_rows"] == 1
        assert result["inserted_portfolio"] == 2
        assert result["inserted_watchlist"] == 1

    def test_empty_tables_migrate_cleanly(self, conn, enc):
        result = migrate(conn, enc, dry_run=False)
        assert result["positions_to_insert"] == 0
        assert result["inserted_portfolio"] == 0
        assert result["inserted_watchlist"] == 0

    def test_dry_run_inserts_nothing(self, conn, enc):
        seed_portfolio(conn, enc, "SAP", "SAP SE", "stock", 10, 150.0, "2024-01-15")
        result = migrate(conn, enc, dry_run=True)
        assert result["dry_run"] is True
        count = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        assert count == 0


# ------------------------------------------------------------------
# Field mapping correctness
# ------------------------------------------------------------------

class TestFieldMapping:
    def test_stock_maps_to_aktie(self, conn, enc):
        seed_portfolio(conn, enc, "SAP", "SAP SE", "stock", 10, 150.0, "2024-01-15")
        migrate(conn, enc, dry_run=False)
        repo = PositionsRepository(conn, enc)
        positions = repo.get_portfolio()
        assert positions[0].asset_class == "Aktie"
        assert positions[0].investment_type == "Wertpapiere"

    def test_etf_maps_to_aktienfonds(self, conn, enc):
        seed_portfolio(conn, enc, "IWDA", "iShares MSCI World", "etf", 5, 80.0, "2024-01-15")
        migrate(conn, enc, dry_run=False)
        repo = PositionsRepository(conn, enc)
        positions = repo.get_portfolio()
        assert positions[0].asset_class == "Aktienfonds"

    def test_ticker_set_from_symbol(self, conn, enc):
        seed_portfolio(conn, enc, "SAP", "SAP SE", "stock", 10, 150.0, "2024-01-15")
        migrate(conn, enc, dry_run=False)
        repo = PositionsRepository(conn, enc)
        assert repo.get_portfolio()[0].ticker == "SAP"

    def test_portfolio_in_portfolio_flag(self, conn, enc):
        seed_portfolio(conn, enc, "SAP", "SAP SE", "stock", 10, 150.0, "2024-01-15")
        migrate(conn, enc, dry_run=False)
        repo = PositionsRepository(conn, enc)
        assert repo.get_portfolio()[0].in_portfolio is True

    def test_watchlist_not_in_portfolio(self, conn, enc):
        seed_watchlist(conn, enc, "NVDA", "Nvidia", "stock")
        migrate(conn, enc, dry_run=False)
        repo = PositionsRepository(conn, enc)
        assert repo.get_watchlist()[0].in_portfolio is False

    def test_watchlist_quantity_is_none(self, conn, enc):
        seed_watchlist(conn, enc, "NVDA", "Nvidia", "stock")
        migrate(conn, enc, dry_run=False)
        repo = PositionsRepository(conn, enc)
        assert repo.get_watchlist()[0].quantity is None

    def test_watchlist_source_becomes_recommendation_source(self, conn, enc):
        seed_watchlist(conn, enc, "NVDA", "Nvidia", "stock", source="agent")
        migrate(conn, enc, dry_run=False)
        repo = PositionsRepository(conn, enc)
        assert repo.get_watchlist()[0].recommendation_source == "agent"

    def test_watchlist_target_price_in_extra_data(self, conn, enc):
        seed_watchlist(conn, enc, "NVDA", "Nvidia", "stock", target_price=500.0)
        migrate(conn, enc, dry_run=False)
        repo = PositionsRepository(conn, enc)
        extra = repo.get_watchlist()[0].extra_data
        assert extra is not None
        assert extra["target_price"] == 500.0

    def test_purchase_price_decrypted_correctly(self, conn, enc):
        seed_portfolio(conn, enc, "SAP", "SAP SE", "stock", 10, 185.50, "2024-01-15")
        migrate(conn, enc, dry_run=False)
        repo = PositionsRepository(conn, enc)
        assert repo.get_portfolio()[0].purchase_price == 185.50

    def test_quantity_decrypted_correctly(self, conn, enc):
        seed_portfolio(conn, enc, "SAP", "SAP SE", "stock", 42, 100.0, "2024-01-15")
        migrate(conn, enc, dry_run=False)
        repo = PositionsRepository(conn, enc)
        assert repo.get_portfolio()[0].quantity == 42.0

    def test_notes_preserved(self, conn, enc):
        seed_portfolio(conn, enc, "SAP", "SAP SE", "stock", 10, 100.0, "2024-01-15", notes="Langfristig halten")
        migrate(conn, enc, dry_run=False)
        repo = PositionsRepository(conn, enc)
        assert repo.get_portfolio()[0].notes == "Langfristig halten"

    def test_null_purchase_price_stays_null(self, conn, enc):
        seed_portfolio(conn, enc, "SAP", "SAP SE", "stock", 10, None, "2024-01-15")
        migrate(conn, enc, dry_run=False)
        repo = PositionsRepository(conn, enc)
        assert repo.get_portfolio()[0].purchase_price is None


# ------------------------------------------------------------------
# Warning generation
# ------------------------------------------------------------------

class TestWarnings:
    def test_other_asset_type_generates_warning(self, conn, enc):
        seed_portfolio(conn, enc, "KRUGER", "Krugerrand", "other", 10, None, "2024-01-15")
        result = migrate(conn, enc, dry_run=False)
        assert any("other" in w for w in result["warnings"])

    def test_stock_generates_no_warning(self, conn, enc):
        seed_portfolio(conn, enc, "SAP", "SAP SE", "stock", 10, 150.0, "2024-01-15")
        result = migrate(conn, enc, dry_run=False)
        assert len(result["warnings"]) == 0
