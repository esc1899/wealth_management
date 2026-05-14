"""
Unit tests for:
- MonthlyDigestRepository (core/storage/monthly_digest.py)
- generate_monthly_digest (core/monthly_digest_generator.py)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from core.storage.base import init_db, migrate_db
from core.storage.monthly_digest import MonthlyDigestRepository
from core.monthly_digest_generator import generate_monthly_digest


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    init_db(c)
    migrate_db(c)
    return c


@pytest.fixture
def repo(conn):
    return MonthlyDigestRepository(conn)


# ---------------------------------------------------------------------------
# MonthlyDigestRepository
# ---------------------------------------------------------------------------

class TestMonthlyDigestRepository:
    def test_save_and_get(self, repo):
        d = repo.save("2026-05", "# Test\n\nHello")
        assert d.month == "2026-05"
        assert d.body_markdown == "# Test\n\nHello"
        assert d.id is not None

        fetched = repo.get("2026-05")
        assert fetched is not None
        assert fetched.body_markdown == "# Test\n\nHello"

    def test_upsert_overwrites(self, repo):
        repo.save("2026-05", "v1")
        repo.save("2026-05", "v2")
        fetched = repo.get("2026-05")
        assert fetched.body_markdown == "v2"

    def test_get_missing_returns_none(self, repo):
        assert repo.get("2026-01") is None

    def test_get_recent(self, repo):
        repo.save("2026-03", "march")
        repo.save("2026-04", "april")
        repo.save("2026-05", "may")
        recent = repo.get_recent(limit=2)
        assert len(recent) == 2
        assert recent[0].month == "2026-05"
        assert recent[1].month == "2026-04"


# ---------------------------------------------------------------------------
# generate_monthly_digest
# ---------------------------------------------------------------------------

def _make_valuation(symbol, current_price=100.0, quantity=10.0, in_portfolio=True):
    v = MagicMock()
    v.symbol = symbol
    v.investment_type = "Wertpapiere"
    v.current_price_eur = current_price
    v.quantity = quantity
    v.current_value_eur = current_price * quantity
    v.in_portfolio = in_portfolio
    v.analysis_excluded = False
    v.purchase_date = None
    v.annual_dividend_eur = None
    v.cost_basis_eur = None
    return v


def _make_analyses_repo(rows: list[dict]) -> MagicMock:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE position_analyses (
            id INTEGER PRIMARY KEY,
            agent TEXT,
            verdict TEXT,
            created_at TEXT
        )
    """)
    for r in rows:
        conn.execute(
            "INSERT INTO position_analyses (agent, verdict, created_at) VALUES (?, ?, ?)",
            (r["agent"], r["verdict"], r["created_at"]),
        )
    conn.commit()
    repo = MagicMock()
    repo._conn = conn
    return repo


class TestGenerateMonthlyDigest:
    def test_contains_month_header(self):
        analyses_repo = _make_analyses_repo([])
        app_config = MagicMock()
        app_config.get_json.return_value = None
        result = generate_monthly_digest([], analyses_repo, app_config, 2026, 5)
        assert "Monatsdigest Mai 2026" in result

    def test_contains_performance_section(self):
        result = generate_monthly_digest([], MagicMock(), MagicMock(), 2026, 5)
        assert "## Performance" in result

    def test_contains_verdicts_section(self):
        analyses_repo = _make_analyses_repo([
            {"agent": "storychecker", "verdict": "intact", "created_at": "2026-05-05T10:00:00"},
            {"agent": "storychecker", "verdict": "gemischt", "created_at": "2026-05-06T10:00:00"},
        ])
        app_config = MagicMock()
        app_config.get_json.return_value = None
        result = generate_monthly_digest([], analyses_repo, app_config, 2026, 5)
        assert "## Checker-Verdicts" in result
        assert "Storychecker" in result
        assert "intact" in result

    def test_contains_macro_section(self):
        app_config = MagicMock()
        app_config.get_json.return_value = {
            "vix": 18.5,
            "eur_usd": 1.082,
            "gold_eur": 3100.0,
            "dax_change_pct": -0.3,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        result = generate_monthly_digest([], MagicMock(), app_config, 2026, 5)
        assert "## Makro-Snapshot" in result
        assert "VIX" in result
        assert "EUR/USD" in result

    def test_performance_with_attribution(self):
        import sqlite3 as sq
        conn = sq.connect(":memory:")
        conn.row_factory = sq.Row
        conn.execute("""
            CREATE TABLE historical_prices (
                id INTEGER PRIMARY KEY,
                symbol TEXT,
                date TEXT,
                close_eur REAL,
                volume INTEGER
            )
        """)
        conn.execute("INSERT INTO historical_prices VALUES (1, 'AAPL', '2026-05-02', 100.0, NULL)")
        conn.commit()
        market_repo = MagicMock()
        market_repo._conn = conn

        vals = [_make_valuation("AAPL", current_price=110.0, quantity=10.0)]
        app_config = MagicMock()
        app_config.get_json.return_value = None
        analyses_repo = _make_analyses_repo([])

        result = generate_monthly_digest(vals, analyses_repo, app_config, 2026, 5, market_repo=market_repo)
        assert "Portfolio gesamt" in result
        assert "AAPL" in result
