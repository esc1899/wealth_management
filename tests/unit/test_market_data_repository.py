"""
Unit tests for MarketDataRepository — uses in-memory SQLite.
"""

import sqlite3
from datetime import date, datetime, timezone

import pytest

from core.storage.base import init_db, migrate_db
from core.storage.market_data import MarketDataRepository
from core.storage.models import DividendRecord, HistoricalPrice, PriceRecord


@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    migrate_db(conn)
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

    def test_previous_close_eur_stored_and_read_back(self, repo):
        record = make_price(price_eur=160.0)
        record = record.model_copy(update={"previous_close_eur": 155.0})
        repo.upsert_price(record)
        result = repo.get_price("AAPL")
        assert result.previous_close_eur == pytest.approx(155.0)

    def test_previous_close_eur_none_by_default(self, repo):
        repo.upsert_price(make_price())
        result = repo.get_price("AAPL")
        assert result.previous_close_eur is None

    def test_previous_close_eur_updated_on_upsert(self, repo):
        repo.upsert_price(make_price(price_eur=150.0))
        updated = make_price(price_eur=160.0).model_copy(update={"previous_close_eur": 148.0})
        repo.upsert_price(updated)
        result = repo.get_price("AAPL")
        assert result.previous_close_eur == pytest.approx(148.0)


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

    def test_duplicate_is_replaced(self, repo):
        from core.storage.models import HistoricalPrice
        repo.upsert_historical(make_history())
        updated = HistoricalPrice(symbol="AAPL", date=date.today(), close_eur=999.0)
        repo.upsert_historical(updated)
        history = repo.get_historical("AAPL")
        assert len(history) == 1
        assert history[0].close_eur == pytest.approx(999.0)

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


class TestGetPrevClose:
    def test_returns_most_recent_close_before_today(self, repo):
        from datetime import timedelta
        today = date.today()
        yesterday = today - timedelta(days=1)
        day_before = today - timedelta(days=2)
        repo.upsert_historical(make_history(d=yesterday, close=100.0))
        repo.upsert_historical(make_history(d=day_before, close=90.0))
        assert repo.get_prev_close("AAPL") == pytest.approx(100.0)

    def test_excludes_todays_entry(self, repo):
        from datetime import timedelta
        today = date.today()
        yesterday = today - timedelta(days=1)
        repo.upsert_historical(make_history(d=today, close=999.0))
        repo.upsert_historical(make_history(d=yesterday, close=50.0))
        assert repo.get_prev_close("AAPL") == pytest.approx(50.0)

    def test_returns_none_when_no_history_before_today(self, repo):
        repo.upsert_historical(make_history(d=date.today(), close=100.0))
        assert repo.get_prev_close("AAPL") is None

    def test_returns_none_when_empty(self, repo):
        assert repo.get_prev_close("AAPL") is None


class TestGetPriceForDate:
    def test_returns_price_for_existing_date(self, repo):
        repo.upsert_historical(make_history(d=date(2026, 5, 12), close=123.45))
        result = repo.get_price_for_date("AAPL", "2026-05-12")
        assert result == pytest.approx(123.45)

    def test_returns_none_for_missing_date(self, repo):
        repo.upsert_historical(make_history(d=date(2026, 5, 12), close=123.45))
        assert repo.get_price_for_date("AAPL", "2026-05-13") is None

    def test_returns_none_for_unknown_symbol(self, repo):
        assert repo.get_price_for_date("UNKNOWN", "2026-05-12") is None

    def test_case_insensitive(self, repo):
        repo.upsert_historical(make_history(symbol="AAPL", d=date(2026, 5, 12), close=50.0))
        assert repo.get_price_for_date("aapl", "2026-05-12") == pytest.approx(50.0)


class TestGetLastPriceInRange:
    def test_returns_last_close_within_range(self, repo):
        repo.upsert_historical(make_history(d=date(2026, 4, 28), close=95.0))
        repo.upsert_historical(make_history(d=date(2026, 4, 29), close=98.0))
        repo.upsert_historical(make_history(d=date(2026, 4, 30), close=100.0))
        result = repo.get_last_price_in_range("AAPL", "2026-04-01", "2026-04-30")
        assert result == pytest.approx(100.0)

    def test_returns_none_when_no_data_in_range(self, repo):
        repo.upsert_historical(make_history(d=date(2026, 3, 31), close=90.0))
        assert repo.get_last_price_in_range("AAPL", "2026-04-01", "2026-04-30") is None

    def test_excludes_data_outside_range(self, repo):
        repo.upsert_historical(make_history(d=date(2026, 3, 31), close=80.0))
        repo.upsert_historical(make_history(d=date(2026, 4, 15), close=90.0))
        repo.upsert_historical(make_history(d=date(2026, 5, 1), close=100.0))
        result = repo.get_last_price_in_range("AAPL", "2026-04-01", "2026-04-30")
        assert result == pytest.approx(90.0)

    def test_case_insensitive(self, repo):
        repo.upsert_historical(make_history(symbol="AAPL", d=date(2026, 4, 30), close=50.0))
        assert repo.get_last_price_in_range("aapl", "2026-04-01", "2026-04-30") == pytest.approx(50.0)

    def test_returns_none_for_unknown_symbol(self, repo):
        assert repo.get_last_price_in_range("UNKNOWN", "2026-04-01", "2026-04-30") is None


def make_dividend(symbol: str = "AAPL", rate_eur: float = 3.0, yield_pct: float = 0.02) -> DividendRecord:
    return DividendRecord(
        symbol=symbol,
        rate_eur=rate_eur,
        yield_pct=yield_pct,
        currency="USD",
        fetched_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


class TestDividendData:
    def test_upsert_creates_record(self, repo):
        repo.upsert_dividend(make_dividend())
        result = repo.get_dividend("AAPL")
        assert result is not None
        assert result.symbol == "AAPL"
        assert result.rate_eur == pytest.approx(3.0)
        assert result.yield_pct == pytest.approx(0.02)

    def test_upsert_updates_existing(self, repo):
        repo.upsert_dividend(make_dividend(rate_eur=3.0, yield_pct=0.02))
        repo.upsert_dividend(make_dividend(rate_eur=4.0, yield_pct=0.025))
        result = repo.get_dividend("AAPL")
        assert result.rate_eur == pytest.approx(4.0)
        assert result.yield_pct == pytest.approx(0.025)

    def test_get_dividend_unknown_symbol_returns_none(self, repo):
        assert repo.get_dividend("UNKNOWN") is None

    def test_get_all_dividends_empty(self, repo):
        assert repo.get_all_dividends() == {}

    def test_get_all_dividends_returns_dict_keyed_by_symbol(self, repo):
        repo.upsert_dividend(make_dividend("AAPL", rate_eur=3.0))
        repo.upsert_dividend(make_dividend("MSFT", rate_eur=5.0))
        all_divs = repo.get_all_dividends()
        assert set(all_divs.keys()) == {"AAPL", "MSFT"}
        assert all_divs["AAPL"].rate_eur == pytest.approx(3.0)
        assert all_divs["MSFT"].rate_eur == pytest.approx(5.0)

    def test_case_insensitive_lookup(self, repo):
        repo.upsert_dividend(make_dividend("AAPL"))
        assert repo.get_dividend("aapl") is not None
