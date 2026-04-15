"""
Unit tests for:
- AppConfigRepository
- migrate_db (new columns / tables on existing schema)
- empfehlung + story fields on Position
- New asset class types (Kryptowährung, Festgeld, Immobilie, Grundstück, etc.)
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date

import pytest

from core.encryption import EncryptionService
from core.storage.app_config import AppConfigRepository
from core.storage.base import init_db, migrate_db
from core.storage.models import Position
from core.storage.positions import PositionsRepository
from core.asset_class_config import load_asset_classes

YAML_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "asset_classes.yaml"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    init_db(c)
    migrate_db(c)
    return c


@pytest.fixture
def enc():
    key = os.urandom(16).hex()
    salt = os.urandom(16)
    return EncryptionService(key, salt)


@pytest.fixture
def repo(conn, enc):
    return PositionsRepository(conn, enc)


@pytest.fixture
def app_config_repo(conn):
    return AppConfigRepository(conn)


# ---------------------------------------------------------------------------
# AppConfigRepository
# ---------------------------------------------------------------------------

class TestAppConfigRepository:
    def test_set_and_get(self, app_config_repo):
        app_config_repo.set("test_key", "hello")
        assert app_config_repo.get("test_key") == "hello"

    def test_get_missing_returns_none(self, app_config_repo):
        assert app_config_repo.get("nonexistent") is None

    def test_upsert(self, app_config_repo):
        app_config_repo.set("k", "v1")
        app_config_repo.set("k", "v2")
        assert app_config_repo.get("k") == "v2"

    def test_delete(self, app_config_repo):
        app_config_repo.set("k", "v")
        app_config_repo.delete("k")
        assert app_config_repo.get("k") is None

    def test_get_json(self, app_config_repo):
        app_config_repo.set_json("labels", ["Kaufen", "Halten"])
        result = app_config_repo.get_json("labels")
        assert result == ["Kaufen", "Halten"]

    def test_get_json_missing_returns_default(self, app_config_repo):
        result = app_config_repo.get_json("nope", default={"a": 1})
        assert result == {"a": 1}

    def test_set_json_round_trip(self, app_config_repo):
        payload = {"model": "llama3", "temp": 0.7}
        app_config_repo.set_json("cfg", payload)
        assert app_config_repo.get_json("cfg") == payload


# ---------------------------------------------------------------------------
# migrate_db — idempotency
# ---------------------------------------------------------------------------

class TestMigrateDb:
    def test_migrate_twice_does_not_raise(self):
        c = sqlite3.connect(":memory:", check_same_thread=False)
        c.row_factory = sqlite3.Row
        init_db(c)
        migrate_db(c)
        migrate_db(c)  # should be idempotent

    def test_empfehlung_column_exists_after_migrate(self, conn):
        cols = [row[1] for row in conn.execute("PRAGMA table_info(positions)").fetchall()]
        assert "empfehlung" in cols

    def test_story_column_exists_after_migrate(self, conn):
        cols = [row[1] for row in conn.execute("PRAGMA table_info(positions)").fetchall()]
        assert "story" in cols

    def test_skills_hidden_column_exists_after_migrate(self, conn):
        cols = [row[1] for row in conn.execute("PRAGMA table_info(skills)").fetchall()]
        assert "hidden" in cols

    def test_analysis_excluded_column_exists_after_migrate(self, conn):
        cols = [row[1] for row in conn.execute("PRAGMA table_info(positions)").fetchall()]
        assert "analysis_excluded" in cols

    def test_app_config_table_exists_after_init(self, conn):
        # app_config is created in init_db
        tables = [
            row[0] for row in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        assert "app_config" in tables


# ---------------------------------------------------------------------------
# empfehlung + story on Position
# ---------------------------------------------------------------------------

def _make_position(**kwargs) -> Position:
    defaults = dict(
        asset_class="Aktie",
        investment_type="Wertpapiere",
        name="Test AG",
        ticker="TEST",
        quantity=10.0,
        unit="Stück",
        purchase_price=100.0,
        purchase_date=date(2024, 1, 15),
        added_date=date(2024, 1, 15),
        in_portfolio=True,
    )
    defaults.update(kwargs)
    return Position(**defaults)


class TestEmpfehlungAndStory:
    def test_empfehlung_saved_and_loaded(self, repo):
        pos = _make_position(empfehlung="Kaufen")
        saved = repo.add(pos)
        loaded = repo.get(saved.id)
        assert loaded.empfehlung == "Kaufen"

    def test_story_saved_and_loaded(self, repo):
        pos = _make_position(story="Langfristiger Wachstumswert im KI-Bereich.")
        saved = repo.add(pos)
        loaded = repo.get(saved.id)
        assert loaded.story == "Langfristiger Wachstumswert im KI-Bereich."

    def test_empfehlung_none_by_default(self, repo):
        saved = repo.add(_make_position())
        loaded = repo.get(saved.id)
        assert loaded.empfehlung is None

    def test_story_none_by_default(self, repo):
        saved = repo.add(_make_position())
        loaded = repo.get(saved.id)
        assert loaded.story is None

    def test_update_empfehlung(self, repo):
        saved = repo.add(_make_position(empfehlung="Beobachten"))
        updated = saved.model_copy(update={"empfehlung": "Verkaufen"})
        repo.update(updated)
        loaded = repo.get(saved.id)
        assert loaded.empfehlung == "Verkaufen"

    def test_analysis_excluded_default_false(self, repo):
        saved = repo.add(_make_position())
        loaded = repo.get(saved.id)
        assert loaded.analysis_excluded is False

    def test_analysis_excluded_saved_and_loaded(self, repo):
        saved = repo.add(_make_position(analysis_excluded=True))
        loaded = repo.get(saved.id)
        assert loaded.analysis_excluded is True

    def test_analysis_excluded_toggle_via_update(self, repo):
        saved = repo.add(_make_position())
        repo.update(saved.model_copy(update={"analysis_excluded": True}))
        loaded = repo.get(saved.id)
        assert loaded.analysis_excluded is True


# ---------------------------------------------------------------------------
# New asset class types
# ---------------------------------------------------------------------------

class TestNewAssetClasses:
    def setup_method(self):
        self.registry = load_asset_classes(YAML_PATH)

    def test_kryptowährung_present(self):
        assert "Kryptowährung" in self.registry.all_names()

    def test_anleihe_present(self):
        assert "Anleihe" in self.registry.all_names()

    def test_festgeld_present(self):
        assert "Festgeld" in self.registry.all_names()

    def test_bargeld_present(self):
        assert "Bargeld" in self.registry.all_names()

    def test_immobilie_present(self):
        assert "Immobilie" in self.registry.all_names()

    def test_grundstück_present(self):
        assert "Grundstück" in self.registry.all_names()

    def test_kryptowährung_auto_fetch(self):
        assert self.registry.get("Kryptowährung").auto_fetch is True

    def test_festgeld_not_auto_fetch(self):
        assert self.registry.get("Festgeld").auto_fetch is False

    def test_immobilie_not_watchlist_eligible(self):
        assert self.registry.get("Immobilie").watchlist_eligible is False

    def test_grundstück_manual_valuation(self):
        assert self.registry.get("Grundstück").manual_valuation is True

    def test_immobilie_manual_valuation(self):
        assert self.registry.get("Immobilie").manual_valuation is True

    def test_festgeld_extra_fields(self):
        cfg = self.registry.get("Festgeld")
        assert "interest_rate" in cfg.extra_fields
        assert "maturity_date" in cfg.extra_fields
        assert "bank" in cfg.extra_fields

    def test_watchlist_eligible_names_excludes_festgeld(self):
        eligible = self.registry.watchlist_eligible_names()
        assert "Festgeld" not in eligible

    def test_watchlist_eligible_names_includes_kryptowährung(self):
        eligible = self.registry.watchlist_eligible_names()
        assert "Kryptowährung" in eligible

    def test_auto_fetch_names_excludes_immobilie(self):
        auto_fetch = self.registry.auto_fetch_names()
        assert "Immobilie" not in auto_fetch

    def test_manual_valuation_names(self):
        manual = self.registry.manual_valuation_names()
        assert "Immobilie" in manual
        assert "Grundstück" in manual

    def test_investment_types_includes_krypto(self):
        types = self.registry.investment_types()
        assert "Krypto" in types

    def test_investment_types_includes_geld(self):
        types = self.registry.investment_types()
        assert "Geld" in types


# ---------------------------------------------------------------------------
# Manual positions (no ticker, no quantity for Grundstück)
# ---------------------------------------------------------------------------

class TestManualPositions:
    def test_immobilie_without_ticker(self, repo):
        pos = Position(
            asset_class="Immobilie",
            investment_type="Immobilien",
            name="Wohnung Berlin",
            ticker=None,
            quantity=1.0,
            unit="Stück",
            purchase_price=250000.0,
            purchase_date=date(2020, 6, 1),
            added_date=date(2020, 6, 1),
            in_portfolio=True,
            extra_data={"estimated_value": 310000.0, "valuation_date": "2024-01-01"},
        )
        saved = repo.add(pos)
        loaded = repo.get(saved.id)
        assert loaded.ticker is None
        assert loaded.extra_data["estimated_value"] == 310000.0

    def test_grundstück_without_quantity(self, repo):
        pos = Position(
            asset_class="Grundstück",
            investment_type="Immobilien",
            name="Grundstück Bayern",
            ticker=None,
            quantity=None,
            unit="Stück",
            purchase_price=80000.0,
            purchase_date=date(2021, 3, 15),
            added_date=date(2021, 3, 15),
            in_portfolio=True,
        )
        saved = repo.add(pos)
        loaded = repo.get(saved.id)
        assert loaded.quantity is None

    def test_festgeld_with_extra_data(self, repo):
        pos = Position(
            asset_class="Festgeld",
            investment_type="Geld",
            name="DKB Festgeld",
            ticker=None,
            quantity=5000.0,
            unit="Stück",
            purchase_price=5000.0,
            purchase_date=date(2023, 1, 1),
            added_date=date(2023, 1, 1),
            in_portfolio=True,
            extra_data={"interest_rate": 3.5, "maturity_date": "2026-01-01", "bank": "DKB"},
        )
        saved = repo.add(pos)
        loaded = repo.get(saved.id)
        assert loaded.extra_data["interest_rate"] == 3.5
        assert loaded.extra_data["bank"] == "DKB"
