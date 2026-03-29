"""
Unit tests for MarketDataRepository — uses in-memory SQLite.
"""

import sqlite3
from datetime import date, datetime, timezone

import pytest

from core.storage.base import init_db
from core.storage.market_data import MarketDataRepository
from core.storage.models import HistoricalPrice, PriceRecord


@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return MarketDataRepository(conn)


def make_price(symbol: str = "AAPL", price_eur: float = 150.0) -> PriceRecord:
    return PriceRecord(
        symbol=symbol,
        price_eur=price_eur,
        currency_original="USD",
        price_original=162.0,
        exchange_rate=0.9259,
        fetched_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


def make_history(symbol: str = "AAPL", d: date = None, close: float = 148.0) -> HistoricalPrice:
    if d is None:
        d = date.today()
    return HistoricalPrice(symbol=symbol, date=d, close_eur=close, volume=50_000_000)


class TestUpsertPrice:
    def test_insert_creates_record(self, repo):
        record = make_price()
        saved = repo.upsert_price(record)
        assert saved.symbol == "AAPL"

    def test_upsert_updates_existing(self, repo):
        repo.upsert_price(make_price(price_eur=150.0))
        repo.upsert_price(make_price(price_eur=160.0))
        result = repo.get_price("AAPL")
        assert result.price_eur == 160.0

    def test_upsert_multiple_symbols(self, repo):
        repo.upsert_price(make_price("AAPL"))
        repo.upsert_price(make_price("MSFT", 250.0))
        prices = repo.get_all_prices()
        assert len(prices) == 2


class TestGetPrice:
    def test_get_existing(self, repo):
        repo.upsert_price(make_price())
        result = repo.get_price("AAPL")
        assert result is not None
        assert result.price_eur == 150.0

    def test_get_not_found_returns_none(self, repo):
        assert repo.get_price("UNKNOWN") is None

    def test_get_is_case_insensitive(self, repo):
        repo.upsert_price(make_price("AAPL"))
        assert repo.get_price("aapl") is not None


class TestGetAllPrices:
    def test_returns_empty_list(self, repo):
        assert repo.get_all_prices() == []

    def test_returns_all_records(self, repo):
        repo.upsert_price(make_price("AAPL"))
        repo.upsert_price(make_price("MSFT"))
        repo.upsert_price(make_price("TSLA"))
        assert len(repo.get_all_prices()) == 3


class TestLatestFetchTime:
    def test_returns_none_when_empty(self, repo):
        assert repo.get_latest_fetch_time() is None

    def test_returns_max_timestamp(self, repo):
        repo.upsert_price(PriceRecord(
            symbol="A", price_eur=1.0, currency_original="USD",
            price_original=1.1, exchange_rate=0.9,
            fetched_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
        ))
        repo.upsert_price(PriceRecord(
            symbol="B", price_eur=2.0, currency_original="USD",
            price_original=2.2, exchange_rate=0.9,
            fetched_at=datetime(2024, 1, 20, tzinfo=timezone.utc),
        ))
        ts = repo.get_latest_fetch_time()
        assert ts.day == 20


class TestUpsertHistorical:
    def test_insert_creates_record(self, repo):
        repo.upsert_historical(make_history())
        history = repo.get_historical("AAPL")
        assert len(history) == 1

    def test_duplicate_is_ignored(self, repo):
        repo.upsert_historical(make_history())
        repo.upsert_historical(make_history())  # same symbol + date
        assert len(repo.get_historical("AAPL")) == 1

    def test_different_dates_stored(self, repo):
        from datetime import timedelta
        today = date.today()
        repo.upsert_historical(make_history(d=today - timedelta(days=2)))
        repo.upsert_historical(make_history(d=today - timedelta(days=1)))
        assert len(repo.get_historical("AAPL")) == 2


class TestGetHistorical:
    def test_returns_empty_for_unknown_symbol(self, repo):
        assert repo.get_historical("UNKNOWN") == []

    def test_ordered_by_date_ascending(self, repo):
        from datetime import timedelta
        today = date.today()
        repo.upsert_historical(make_history(d=today - timedelta(days=1)))
        repo.upsert_historical(make_history(d=today - timedelta(days=3)))
        repo.upsert_historical(make_history(d=today - timedelta(days=2)))
        history = repo.get_historical("AAPL")
        dates = [h.date for h in history]
        assert dates == sorted(dates)

    def test_respects_days_limit(self, repo):
        from datetime import timedelta
        today = date.today()
        # Insert 19 records: 1 older than 5 days, 18 within last 5 days
        repo.upsert_historical(make_history(d=today - timedelta(days=10)))
        for i in range(1, 6):
            repo.upsert_historical(make_history(d=today - timedelta(days=i)))
        history = repo.get_historical("AAPL", days=5)
        assert len(history) == 5
