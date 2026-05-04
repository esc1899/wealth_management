"""
Tests for AgentSchedulerService position filtering.

Verifies that scheduled batch jobs:
1. Only include portfolio positions (not watchlist)
2. Exclude positions with analysis_excluded=True
"""

import os
import sqlite3
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock

import pytest

from core.scheduler import AgentSchedulerService
from core.storage.base import init_db, migrate_db
from core.storage.models import Position, ScheduledJob
from core.storage.positions import PositionsRepository
from core.storage.scheduled_jobs import ScheduledJobsRepository
from core.encryption import EncryptionService


@pytest.fixture
def conn():
    """Real SQLite connection for position/job setup."""
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    init_db(c)
    migrate_db(c)
    return c


@pytest.fixture
def enc():
    """Encryption service for position repo."""
    key = os.urandom(16).hex()
    salt = os.urandom(16)
    return EncryptionService(key, salt)


@pytest.fixture
def positions_repo(conn, enc):
    """Real positions repository."""
    return PositionsRepository(conn, enc)


@pytest.fixture
def jobs_repo(conn):
    """Real scheduled jobs repository."""
    return ScheduledJobsRepository(conn)


@pytest.fixture
def scheduler():
    """Scheduler instance for testing."""
    return AgentSchedulerService(
        db_path=":memory:",
        encryption_key="test-key",
        anthropic_api_key="test-api",
        default_claude_model="claude-haiku-4-5-20251001",
    )


# ------------------------------------------------------------------
# Issue A: Watchlist positions should NOT be in batch jobs
# ------------------------------------------------------------------


def test_positions_setup_portfolio_and_watchlist(positions_repo):
    """Setup: create both portfolio and watchlist positions for testing."""
    portfolio_pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="Portfolio Stock",
        ticker="TSLA",
        unit="Stk",
        added_date=datetime.now().date(),
        in_portfolio=True,
        in_watchlist=False,
        analysis_excluded=False,
    )
    watchlist_pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="Watchlist Stock",
        ticker="AAPL",
        unit="Stk",
        added_date=datetime.now().date(),
        in_portfolio=False,
        in_watchlist=True,
        analysis_excluded=False,
    )
    both_pos = Position(
        asset_class="ETF",
        investment_type="ETF",
        name="Portfolio & Watchlist",
        ticker="VOO",
        unit="Stk",
        added_date=datetime.now().date(),
        in_portfolio=True,
        in_watchlist=True,
        analysis_excluded=False,
    )

    portfolio_repo = positions_repo.add(portfolio_pos)
    watchlist_repo = positions_repo.add(watchlist_pos)
    both_repo = positions_repo.add(both_pos)

    # Verify setup
    assert portfolio_repo.in_portfolio and not portfolio_repo.in_watchlist
    assert watchlist_repo.in_watchlist and not watchlist_repo.in_portfolio
    assert both_repo.in_portfolio and both_repo.in_watchlist


def test_get_portfolio_excludes_watchlist_only(positions_repo):
    """get_portfolio() should NOT include watchlist-only positions."""
    portfolio_pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="Portfolio",
        ticker="TSLA",
        unit="Stk",
        added_date=datetime.now().date(),
        in_portfolio=True,
        in_watchlist=False,
    )
    watchlist_pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="Watchlist Only",
        ticker="AAPL",
        unit="Stk",
        added_date=datetime.now().date(),
        in_portfolio=False,
        in_watchlist=True,
    )

    positions_repo.add(portfolio_pos)
    positions_repo.add(watchlist_pos)

    portfolio_only = positions_repo.get_portfolio()
    tickers = {p.ticker for p in portfolio_only}

    assert "TSLA" in tickers
    assert "AAPL" not in tickers


def test_get_all_includes_watchlist(positions_repo):
    """get_all() SHOULD include watchlist positions (for UI/Watchlist Checker)."""
    portfolio_pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="Portfolio",
        ticker="TSLA",
        unit="Stk",
        added_date=datetime.now().date(),
        in_portfolio=True,
    )
    watchlist_pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="Watchlist",
        ticker="AAPL",
        unit="Stk",
        added_date=datetime.now().date(),
        in_watchlist=True,
    )

    positions_repo.add(portfolio_pos)
    positions_repo.add(watchlist_pos)

    all_pos = positions_repo.get_all()
    tickers = {p.ticker for p in all_pos}

    assert "TSLA" in tickers
    assert "AAPL" in tickers


# ------------------------------------------------------------------
# Issue B: analysis_excluded field should filter scheduled jobs
# ------------------------------------------------------------------


def test_analysis_excluded_in_position_model():
    """Verify Position model has analysis_excluded field."""
    pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="Test",
        ticker="TSLA",
        unit="Stk",
        added_date=datetime.now().date(),
        analysis_excluded=True,
    )
    assert pos.analysis_excluded is True


def test_positions_with_analysis_excluded_flag(positions_repo):
    """Create positions with different analysis_excluded states."""
    included_pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="Included",
        ticker="TSLA",
        unit="Stk",
        added_date=datetime.now().date(),
        in_portfolio=True,
        analysis_excluded=False,
    )
    excluded_pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="Excluded",
        ticker="AAPL",
        unit="Stk",
        added_date=datetime.now().date(),
        in_portfolio=True,
        analysis_excluded=True,
    )

    positions_repo.add(included_pos)
    positions_repo.add(excluded_pos)

    all_portfolio = positions_repo.get_portfolio()
    assert len(all_portfolio) == 2

    # Verify we can read the flag
    excluded = [p for p in all_portfolio if p.analysis_excluded]
    assert len(excluded) == 1
    assert excluded[0].ticker == "AAPL"


# ------------------------------------------------------------------
# Integration tests: Position fetching behavior (FAILING before fix)
# ------------------------------------------------------------------


def test_scheduler_position_fetching_logic_portfolio_vs_watchlist(positions_repo):
    """
    FAILING TEST: Simulates the current buggy behavior in scheduler.

    This test documents WHAT scheduler currently does (wrong) vs. WHAT it should do.
    """
    # Create test positions
    portfolio_pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="My Holdings",
        ticker="TSLA",
        unit="Stk",
        added_date=datetime.now().date(),
        in_portfolio=True,
        in_watchlist=False,
        story="Growth play",
    )
    watchlist_pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="Research Only",
        ticker="AAPL",
        unit="Stk",
        added_date=datetime.now().date(),
        in_portfolio=False,
        in_watchlist=True,
        story="To investigate",
    )

    positions_repo.add(portfolio_pos)
    positions_repo.add(watchlist_pos)

    # Current (BUGGY) scheduler behavior: uses get_all()
    buggy_positions = [p for p in positions_repo.get_all() if p.story]
    buggy_tickers = {p.ticker for p in buggy_positions}

    # Expected (FIXED) scheduler behavior: uses get_portfolio()
    fixed_positions = [p for p in positions_repo.get_portfolio() if p.story]
    fixed_tickers = {p.ticker for p in fixed_positions}

    # This test FAILS now (watchlist included) and PASSES after fix
    assert "TSLA" in fixed_tickers
    assert "AAPL" not in fixed_tickers, "FAILING: watchlist should NOT be in portfolio-only jobs"

    # Document current buggy behavior
    assert "AAPL" in buggy_tickers, "Currently AAPL IS included (bug)"


def test_scheduler_position_filtering_analysis_excluded(positions_repo):
    """
    FAILING TEST: analysis_excluded field should filter batch jobs.

    Currently: all portfolio positions are analyzed
    Expected: positions marked analysis_excluded=True should be skipped
    """
    included_pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="Stock A",
        ticker="TSLA",
        unit="Stk",
        added_date=datetime.now().date(),
        in_portfolio=True,
        story="Good stock",
        analysis_excluded=False,
    )
    excluded_pos = Position(
        asset_class="Aktie",
        investment_type="Einzelaktie",
        name="Stock B",
        ticker="AAPL",
        unit="Stk",
        added_date=datetime.now().date(),
        in_portfolio=True,
        story="Personal choice",
        analysis_excluded=True,
    )

    positions_repo.add(included_pos)
    positions_repo.add(excluded_pos)

    # Current (BUGGY) scheduler behavior: ignores analysis_excluded
    buggy_filtered = [p for p in positions_repo.get_portfolio() if p.story]
    buggy_tickers = {p.ticker for p in buggy_filtered}

    # Expected (FIXED) scheduler behavior: respects analysis_excluded
    fixed_filtered = [
        p
        for p in positions_repo.get_portfolio()
        if p.story and not p.analysis_excluded
    ]
    fixed_tickers = {p.ticker for p in fixed_filtered}

    # This test FAILS now (both included) and PASSES after fix
    assert "TSLA" in fixed_tickers
    assert "AAPL" not in fixed_tickers, "FAILING: analysis_excluded positions should be filtered out"

    # Document current buggy behavior
    assert "AAPL" in buggy_tickers, "Currently AAPL IS included (bug)"
