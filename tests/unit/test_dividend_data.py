"""
Unit tests for dividend data fetching and calculation.
"""

import sqlite3
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from agents.market_data_agent import MarketDataAgent, PortfolioValuation
from core.storage.base import get_connection, init_db, migrate_db
from core.storage.market_data import MarketDataRepository
from core.storage.models import DividendRecord, Position, PriceRecord
from core.storage.positions import PositionsRepository


@pytest.fixture
def memory_db():
    """Create an in-memory SQLite database with all tables."""
    conn = get_connection(":memory:")
    init_db(conn)
    migrate_db(conn)
    conn.row_factory = sqlite3.Row
    return conn


class TestDividendRecord:
    """Tests for DividendRecord model validation."""

    def test_dividend_record_valid(self):
        """Create a valid DividendRecord."""
        record = DividendRecord(
            symbol="AAPL",
            rate_eur=2.5,
            yield_pct=0.015,
            currency="USD",
            fetched_at=datetime.now(timezone.utc),
        )
        assert record.symbol == "AAPL"
        assert record.rate_eur == 2.5
        assert record.yield_pct == 0.015

    def test_dividend_record_no_data(self):
        """Create a DividendRecord with no dividend data (accumulators)."""
        record = DividendRecord(
            symbol="VWCE",
            rate_eur=None,
            yield_pct=None,
            currency="EUR",
            fetched_at=datetime.now(timezone.utc),
        )
        assert record.rate_eur is None
        assert record.yield_pct is None

    def test_symbol_uppercase(self):
        """Symbol is normalized to uppercase."""
        record = DividendRecord(
            symbol="aapl",
            rate_eur=2.5,
            yield_pct=0.015,
            currency="USD",
            fetched_at=datetime.now(timezone.utc),
        )
        assert record.symbol == "AAPL"

    def test_negative_rate_rejected(self):
        """Negative rates are rejected."""
        with pytest.raises(ValueError):
            DividendRecord(
                symbol="AAPL",
                rate_eur=-1.0,
                yield_pct=0.015,
                currency="USD",
                fetched_at=datetime.now(timezone.utc),
            )


class TestMarketDataRepository:
    """Tests for dividend CRUD in MarketDataRepository."""

    def test_upsert_dividend(self, memory_db):
        """Insert a dividend record."""
        repo = MarketDataRepository(memory_db)
        record = DividendRecord(
            symbol="AAPL",
            rate_eur=2.5,
            yield_pct=0.015,
            currency="USD",
            fetched_at=datetime.now(timezone.utc),
        )
        result = repo.upsert_dividend(record)
        assert result.symbol == "AAPL"
        assert result.rate_eur == 2.5

    def test_get_dividend(self, memory_db):
        """Retrieve a dividend record."""
        repo = MarketDataRepository(memory_db)
        record = DividendRecord(
            symbol="AAPL",
            rate_eur=2.5,
            yield_pct=0.015,
            currency="USD",
            fetched_at=datetime.now(timezone.utc),
        )
        repo.upsert_dividend(record)

        retrieved = repo.get_dividend("AAPL")
        assert retrieved is not None
        assert retrieved.symbol == "AAPL"
        assert retrieved.rate_eur == 2.5

    def test_get_dividend_not_found(self, memory_db):
        """Get non-existent dividend returns None."""
        repo = MarketDataRepository(memory_db)
        result = repo.get_dividend("NONEXIST")
        assert result is None

    def test_get_all_dividends(self, memory_db):
        """Retrieve all dividend records."""
        repo = MarketDataRepository(memory_db)
        records = [
            DividendRecord(
                symbol="AAPL",
                rate_eur=2.5,
                yield_pct=0.015,
                currency="USD",
                fetched_at=datetime.now(timezone.utc),
            ),
            DividendRecord(
                symbol="VUSA",
                rate_eur=3.2,
                yield_pct=0.025,
                currency="GBP",
                fetched_at=datetime.now(timezone.utc),
            ),
        ]
        for r in records:
            repo.upsert_dividend(r)

        all_divs = repo.get_all_dividends()
        assert len(all_divs) == 2
        assert "AAPL" in all_divs
        assert "VUSA" in all_divs

    def test_upsert_dividend_update(self, memory_db):
        """Upsert updates an existing record."""
        repo = MarketDataRepository(memory_db)
        record1 = DividendRecord(
            symbol="AAPL",
            rate_eur=2.5,
            yield_pct=0.015,
            currency="USD",
            fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        repo.upsert_dividend(record1)

        record2 = DividendRecord(
            symbol="AAPL",
            rate_eur=2.8,
            yield_pct=0.018,
            currency="USD",
            fetched_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        )
        repo.upsert_dividend(record2)

        all_divs = repo.get_all_dividends()
        assert len(all_divs) == 1  # Only one AAPL record
        assert all_divs["AAPL"].rate_eur == 2.8


class TestPortfolioValuationDividends:
    """Tests for dividend calculation in get_portfolio_valuation()."""

    def _make_position(self, ticker: str, quantity: float, asset_class: str, **kwargs) -> Position:
        """Helper to create a Position."""
        defaults = {
            "id": 1,
            "name": f"{ticker} Test",
            "investment_type": "Wertpapiere" if asset_class == "Aktie" else "Geld",
            "quantity": quantity,
            "unit": "Stück" if asset_class != "Festgeld" else "€",
            "purchase_price": 100.0,
            "purchase_date": date(2020, 1, 1),
            "added_date": date.today(),
            "in_portfolio": True,
        }
        defaults.update(kwargs)
        return Position(asset_class=asset_class, ticker=ticker, **defaults)

    def test_portfolio_valuation_yfinance_dividend(self, memory_db):
        """Calculate annual dividend from yfinance dividend data."""
        # Setup
        pos = self._make_position("AAPL", 10.0, "Aktie")
        positions_repo = MagicMock()
        positions_repo.get_portfolio.return_value = [pos]
        positions_repo.get_watchlist.return_value = []

        market_repo = MarketDataRepository(memory_db)

        # Add dividend data
        div_record = DividendRecord(
            symbol="AAPL",
            rate_eur=2.5,
            yield_pct=0.015,
            currency="USD",
            fetched_at=datetime.now(timezone.utc),
        )
        market_repo.upsert_dividend(div_record)

        # Create agent
        fetcher = MagicMock()
        agent = MarketDataAgent(
            positions_repo=positions_repo,
            market_repo=market_repo,
            fetcher=fetcher,
            db_path=":memory:",
            encryption_key="test",
        )

        # Get valuation
        valuations = agent.get_portfolio_valuation()
        assert len(valuations) == 1
        assert valuations[0].symbol == "AAPL"
        assert valuations[0].annual_dividend_eur == 25.0  # 10 × 2.5 EUR
        assert valuations[0].dividend_yield_pct == 0.015
        assert valuations[0].dividend_source == "yfinance"

    def test_portfolio_valuation_festgeld_interest(self, memory_db):
        """Calculate annual interest from Festgeld interest_rate."""
        pos = self._make_position(
            None,  # ticker
            100.0,
            "Festgeld",
            extra_data={
                "interest_rate": 3.5,
                "estimated_value": 10000.0,
            },
        )
        positions_repo = MagicMock()
        positions_repo.get_portfolio.return_value = [pos]
        positions_repo.get_watchlist.return_value = []

        market_repo = MarketDataRepository(memory_db)
        fetcher = MagicMock()

        agent = MarketDataAgent(
            positions_repo=positions_repo,
            market_repo=market_repo,
            fetcher=fetcher,
            db_path=":memory:",
            encryption_key="test",
        )

        valuations = agent.get_portfolio_valuation()
        assert len(valuations) == 1
        # 10000 × 3.5% = 350 EUR annual interest
        assert valuations[0].annual_dividend_eur == 350.0
        assert valuations[0].dividend_yield_pct == 0.035
        assert valuations[0].dividend_source == "festgeld"

    def test_portfolio_valuation_anleihe_interest(self, memory_db):
        """Calculate annual coupon from Anleihe interest_rate."""
        pos = self._make_position(
            None,  # ticker
            1.0,
            "Anleihe",
            extra_data={
                "interest_rate": 2.0,
                "estimated_value": 5000.0,
            },
        )
        positions_repo = MagicMock()
        positions_repo.get_portfolio.return_value = [pos]
        positions_repo.get_watchlist.return_value = []

        market_repo = MarketDataRepository(memory_db)
        fetcher = MagicMock()

        agent = MarketDataAgent(
            positions_repo=positions_repo,
            market_repo=market_repo,
            fetcher=fetcher,
            db_path=":memory:",
            encryption_key="test",
        )

        valuations = agent.get_portfolio_valuation()
        assert len(valuations) == 1
        # 5000 × 2.0% = 100 EUR annual coupon
        assert valuations[0].annual_dividend_eur == 100.0
        assert valuations[0].dividend_yield_pct == 0.02
        assert valuations[0].dividend_source == "anleihe"

    def test_portfolio_valuation_no_dividend_data(self, memory_db):
        """Position without dividend data has None dividend fields."""
        pos = self._make_position("VWCE", 5.0, "Aktienfonds")
        positions_repo = MagicMock()
        positions_repo.get_portfolio.return_value = [pos]
        positions_repo.get_watchlist.return_value = []

        market_repo = MarketDataRepository(memory_db)
        # Don't add any dividend data for VWCE

        fetcher = MagicMock()
        agent = MarketDataAgent(
            positions_repo=positions_repo,
            market_repo=market_repo,
            fetcher=fetcher,
            db_path=":memory:",
            encryption_key="test",
        )

        valuations = agent.get_portfolio_valuation()
        assert len(valuations) == 1
        assert valuations[0].annual_dividend_eur is None
        assert valuations[0].dividend_source is None
