"""
Unit tests for core/storage/yearly_digest.py and core/yearly_digest_generator.py
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from core.storage.yearly_digest import YearlyDigestRepository
from core.yearly_digest_generator import generate_yearly_digest


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE yearly_digests (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            year          TEXT NOT NULL UNIQUE,
            body_markdown TEXT NOT NULL,
            generated_at  TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


class TestYearlyDigestRepository:
    def test_save_and_get(self):
        repo = YearlyDigestRepository(_make_conn())
        repo.save("2025", "# Jahresdigest 2025")
        result = repo.get("2025")
        assert result is not None
        assert result.year == "2025"
        assert "Jahresdigest" in result.body_markdown

    def test_get_missing(self):
        repo = YearlyDigestRepository(_make_conn())
        assert repo.get("2020") is None

    def test_upsert(self):
        repo = YearlyDigestRepository(_make_conn())
        repo.save("2025", "original")
        repo.save("2025", "updated")
        result = repo.get("2025")
        assert result.body_markdown == "updated"

    def test_get_recent(self):
        repo = YearlyDigestRepository(_make_conn())
        for y in ["2023", "2024", "2025"]:
            repo.save(y, f"digest {y}")
        recent = repo.get_recent(2)
        assert len(recent) == 2
        assert recent[0].year == "2025"  # sorted DESC

    def test_generated_at_is_datetime(self):
        repo = YearlyDigestRepository(_make_conn())
        repo.save("2026", "test")
        result = repo.get("2026")
        assert isinstance(result.generated_at, datetime)


class TestGenerateYearlyDigest:
    def _make_valuation(self, symbol, current_value=1000.0, delta_pct=5.0):
        v = MagicMock()
        v.symbol = symbol
        v.investment_type = "Wertpapiere"
        v.in_portfolio = True
        v.analysis_excluded = False
        v.current_value_eur = current_value
        v.current_price_eur = 110.0
        v.quantity = 10.0
        v.unit = "Stk"
        return v

    def _make_analyses_repo(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE position_analyses (
                id INTEGER PRIMARY KEY,
                agent TEXT NOT NULL,
                verdict TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO position_analyses (agent, verdict, created_at) VALUES ('storychecker', 'intact', '2026-03-15T10:00:00')")
        conn.execute("INSERT INTO position_analyses (agent, verdict, created_at) VALUES ('fundamental', 'unterbewertet', '2026-07-20T10:00:00')")
        conn.commit()
        repo = MagicMock()
        repo._conn = conn
        return repo

    def test_contains_year_header(self):
        analyses_repo = self._make_analyses_repo()
        app_config_repo = MagicMock()
        app_config_repo.get_json.return_value = None
        md = generate_yearly_digest([], analyses_repo, app_config_repo, 2026)
        assert "# Jahresdigest 2026" in md

    def test_contains_performance_section(self):
        analyses_repo = self._make_analyses_repo()
        app_config_repo = MagicMock()
        app_config_repo.get_json.return_value = None
        md = generate_yearly_digest([], analyses_repo, app_config_repo, 2026)
        assert "## Performance" in md

    def test_contains_checker_section(self):
        analyses_repo = self._make_analyses_repo()
        app_config_repo = MagicMock()
        app_config_repo.get_json.return_value = None
        md = generate_yearly_digest([], analyses_repo, app_config_repo, 2026)
        assert "## Checker-Verdicts" in md
        assert "Storychecker" in md

    def test_contains_macro_section(self):
        analyses_repo = self._make_analyses_repo()
        app_config_repo = MagicMock()
        app_config_repo.get_json.return_value = {
            "vix": 18.5,
            "eur_usd": 1.082,
            "gold_eur": 3100.0,
            "dax_change_pct": -0.3,
            "fetched_at": "2026-05-10T10:00:00+00:00",
        }
        md = generate_yearly_digest([], analyses_repo, app_config_repo, 2026)
        assert "## Makro-Snapshot" in md
        assert "VIX" in md

    def test_monthly_overview_section(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE monthly_digests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL UNIQUE,
                body_markdown TEXT NOT NULL,
                generated_at TEXT NOT NULL
            )
        """)
        conn.execute("INSERT INTO monthly_digests (month, body_markdown, generated_at) VALUES ('2026-03', 'März digest', '2026-04-01T06:00:00+00:00')")
        conn.commit()
        from core.storage.monthly_digest import MonthlyDigestRepository
        monthly_repo = MonthlyDigestRepository(conn)

        analyses_repo = self._make_analyses_repo()
        app_config_repo = MagicMock()
        app_config_repo.get_json.return_value = None
        md = generate_yearly_digest([], analyses_repo, app_config_repo, 2026, monthly_digest_repo=monthly_repo)
        assert "## Monatsübersicht" in md
        assert "Mär" in md
