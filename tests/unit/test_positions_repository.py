"""
Unit tests for PositionsRepository.
Uses real SQLite in-memory DB — no mocking of storage.
"""

import os
import sqlite3
from datetime import date
import pytest

from core.encryption import EncryptionService
from core.storage.base import init_db
from core.storage.models import Position
from core.storage.positions import PositionsRepository


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    init_db(c)
    return c


@pytest.fixture
def enc():
    key = os.urandom(16).hex()
    salt = os.urandom(16)
    return EncryptionService(key, salt)


@pytest.fixture
def repo(conn, enc):
    return PositionsRepository(conn, enc)


def portfolio_position(**kwargs) -> Position:
    defaults = dict(
        asset_class="Aktie",
        investment_type="Wertpapiere",
        name="Apple Inc.",
        ticker="AAPL",
        quantity=10.0,
        unit="Stück",
        purchase_price=150.0,
        purchase_date=date(2024, 1, 15),
        added_date=date(2024, 1, 15),
        in_portfolio=True,
    )
    defaults.update(kwargs)
    return Position(**defaults)


def watchlist_position(**kwargs) -> Position:
    defaults = dict(
        asset_class="Aktie",
        investment_type="Wertpapiere",
        name="Tesla Inc.",
        ticker="TSLA",
        quantity=None,
        unit="Stück",
        added_date=date(2024, 1, 15),
        in_portfolio=False,
        in_watchlist=True,
    )
    defaults.update(kwargs)
    return Position(**defaults)


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

class TestCRUD:
    def test_add_and_get(self, repo):
        p = repo.add(portfolio_position())
        assert p.id is not None
        fetched = repo.get(p.id)
        assert fetched.name == "Apple Inc."
        assert fetched.ticker == "AAPL"
        assert fetched.quantity == 10.0
        assert fetched.purchase_price == 150.0
        assert fetched.in_portfolio is True

    def test_get_nonexistent_returns_none(self, repo):
        assert repo.get(9999) is None

    def test_get_all_returns_both_types(self, repo):
        repo.add(portfolio_position())
        repo.add(watchlist_position())
        all_positions = repo.get_all()
        assert len(all_positions) == 2

    def test_get_portfolio_filters_correctly(self, repo):
        repo.add(portfolio_position())
        repo.add(watchlist_position())
        portfolio = repo.get_portfolio()
        assert len(portfolio) == 1
        assert portfolio[0].in_portfolio is True

    def test_get_watchlist_filters_correctly(self, repo):
        repo.add(portfolio_position())
        repo.add(watchlist_position())
        watchlist = repo.get_watchlist()
        assert len(watchlist) == 1
        assert watchlist[0].in_portfolio is False

    def test_update(self, repo):
        p = repo.add(portfolio_position())
        updated = p.model_copy(update={"name": "Apple Inc. (Updated)", "quantity": 20.0})
        assert repo.update(updated) is True
        fetched = repo.get(p.id)
        assert fetched.name == "Apple Inc. (Updated)"
        assert fetched.quantity == 20.0

    def test_update_without_id_raises(self, repo):
        with pytest.raises(ValueError):
            repo.update(portfolio_position())

    def test_delete(self, repo):
        p = repo.add(portfolio_position())
        assert repo.delete(p.id) is True
        assert repo.get(p.id) is None

    def test_delete_nonexistent_returns_false(self, repo):
        assert repo.delete(9999) is False


# ------------------------------------------------------------------
# Encryption
# ------------------------------------------------------------------

class TestEncryption:
    def test_quantity_encrypted_at_rest(self, repo, conn):
        repo.add(portfolio_position(quantity=42.0))
        raw = conn.execute("SELECT quantity FROM positions").fetchone()[0]
        assert raw != "42.0"
        assert "42" not in raw

    def test_purchase_price_encrypted_at_rest(self, repo, conn):
        repo.add(portfolio_position(purchase_price=185.0))
        raw = conn.execute("SELECT purchase_price FROM positions").fetchone()[0]
        assert "185" not in raw

    def test_notes_encrypted_at_rest(self, repo, conn):
        repo.add(portfolio_position(notes="geheime Notiz"))
        raw = conn.execute("SELECT notes FROM positions").fetchone()[0]
        assert "geheime" not in raw

    def test_extra_data_encrypted_at_rest(self, repo, conn):
        repo.add(portfolio_position(extra_data={"purity": "999.9"}))
        raw = conn.execute("SELECT extra_data FROM positions").fetchone()[0]
        assert "999.9" not in raw

    def test_extra_data_roundtrip(self, repo):
        data = {"purity": "999.9", "storage": "Zürich"}
        p = repo.add(portfolio_position(extra_data=data))
        fetched = repo.get(p.id)
        assert fetched.extra_data == data

    def test_null_encrypted_fields_stay_null(self, repo):
        p = repo.add(watchlist_position())
        fetched = repo.get(p.id)
        assert fetched.quantity is None
        assert fetched.purchase_price is None
        assert fetched.notes is None
        assert fetched.extra_data is None


# ------------------------------------------------------------------
# Optional fields
# ------------------------------------------------------------------

class TestOptionalFields:
    def test_isin_wkn_stored_and_retrieved(self, repo):
        p = repo.add(portfolio_position(isin="US0378331005", wkn="865985"))
        fetched = repo.get(p.id)
        assert fetched.isin == "US0378331005"
        assert fetched.wkn == "865985"

    def test_recommendation_source_and_strategy(self, repo):
        p = repo.add(portfolio_position(
            recommendation_source="Börsenbrief XY",
            strategy="10 Jahre Halten",
        ))
        fetched = repo.get(p.id)
        assert fetched.recommendation_source == "Börsenbrief XY"
        assert fetched.strategy == "10 Jahre Halten"

    def test_purchase_date_optional(self, repo):
        p = repo.add(portfolio_position(purchase_date=None))
        fetched = repo.get(p.id)
        assert fetched.purchase_date is None


# ------------------------------------------------------------------
# Domain operations
# ------------------------------------------------------------------

class TestPromoteToPortfolio:
    def test_promote_sets_in_portfolio(self, repo):
        w = repo.add(watchlist_position())
        promoted = repo.promote_to_portfolio(w.id, quantity=5.0, purchase_price=200.0)
        assert promoted.in_portfolio is True
        assert promoted.quantity == 5.0
        assert promoted.purchase_price == 200.0

    def test_promote_persists_to_db(self, repo):
        w = repo.add(watchlist_position())
        repo.promote_to_portfolio(w.id, quantity=5.0)
        fetched = repo.get(w.id)
        assert fetched.in_portfolio is True
        assert fetched.quantity == 5.0

    def test_promote_nonexistent_returns_none(self, repo):
        assert repo.promote_to_portfolio(9999, quantity=1.0) is None

    def test_promote_already_portfolio_raises(self, repo):
        p = repo.add(portfolio_position())
        with pytest.raises(ValueError, match="already in the portfolio"):
            repo.promote_to_portfolio(p.id, quantity=5.0)


# ------------------------------------------------------------------
# Ticker queries
# ------------------------------------------------------------------

class TestTickerQueries:
    def test_get_by_ticker(self, repo):
        repo.add(portfolio_position(ticker="AAPL"))
        repo.add(portfolio_position(name="Another", ticker="MSFT"))
        results = repo.get_by_ticker("AAPL")
        assert len(results) == 1
        assert results[0].ticker == "AAPL"

    def test_get_by_ticker_case_insensitive(self, repo):
        repo.add(portfolio_position(ticker="AAPL"))
        assert len(repo.get_by_ticker("aapl")) == 1

    def test_get_tickers_for_price_fetch_deduplicates(self, repo):
        repo.add(portfolio_position(ticker="AAPL"))
        repo.add(portfolio_position(name="AAPL2", ticker="AAPL"))
        repo.add(portfolio_position(name="MSFT", ticker="MSFT"))
        tickers = repo.get_tickers_for_price_fetch()
        assert len(tickers) == 2
        assert "AAPL" in tickers
        assert "MSFT" in tickers

    def test_get_tickers_excludes_null_ticker(self, repo):
        repo.add(watchlist_position(ticker=None))
        repo.add(portfolio_position(ticker="AAPL"))
        tickers = repo.get_tickers_for_price_fetch()
        assert None not in tickers
        assert len(tickers) == 1
