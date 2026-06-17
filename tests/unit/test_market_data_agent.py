"""
Unit tests for MarketDataAgent — repos and fetcher are mocked.
"""

import threading
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from agents.market_data_agent import MarketDataAgent
from core.storage.models import PriceRecord, Position

# CEST = Berlin summer time (UTC+2), matches June (the user's scenario)
CEST = timezone(timedelta(hours=2))


def _make_position(ticker: str = "AAPL", quantity: float = 10.0, price: float = 150.0) -> Position:
    return Position(
        id=1,
        ticker=ticker,
        name=ticker,
        asset_class="Aktie",
        investment_type="Wertpapiere",
        quantity=quantity,
        unit="Stück",
        purchase_price=price,
        purchase_date=date(2024, 1, 1),
        added_date=date(2024, 1, 1),
        in_portfolio=True,
    )


def _make_price_record(symbol: str = "AAPL", price_eur: float = 180.0) -> PriceRecord:
    return PriceRecord(
        symbol=symbol,
        price_eur=price_eur,
        currency_original="USD",
        price_original=195.0,
        exchange_rate=0.923,
        fetched_at=datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def agent():
    positions_repo = MagicMock()
    market_repo = MagicMock()
    market_repo.get_prev_close.return_value = None  # daily P&L off by default
    fetcher = MagicMock()
    return MarketDataAgent(
        positions_repo=positions_repo,
        market_repo=market_repo,
        fetcher=fetcher,
        db_path=":memory:",
        encryption_key="test_key",
    )


class TestFetchAllNow:
    def test_empty_portfolio_returns_zero_fetched(self, agent):
        agent._positions.get_portfolio.return_value = []
        agent._positions.get_watchlist.return_value = []
        result = agent.fetch_all_now()
        assert result.fetched == 0
        agent._fetcher.fetch_current_prices.assert_not_called()

    def test_collects_symbols_from_portfolio(self, agent):
        agent._positions.get_portfolio.return_value = [
            _make_position("AAPL"), _make_position("MSFT"),
        ]
        agent._positions.get_watchlist.return_value = []
        agent._fetcher.fetch_current_prices.return_value = ([], [])
        agent.fetch_all_now()
        called_symbols = agent._fetcher.fetch_current_prices.call_args[0][0]
        assert set(called_symbols) == {"AAPL", "MSFT"}

    def test_deduplicates_symbols(self, agent):
        # Same ticker in portfolio and watchlist → deduplicated
        agent._positions.get_portfolio.return_value = [_make_position("AAPL")]
        agent._positions.get_watchlist.return_value = [_make_position("AAPL")]
        agent._fetcher.fetch_current_prices.return_value = ([], [])
        agent.fetch_all_now()
        called_symbols = agent._fetcher.fetch_current_prices.call_args[0][0]
        assert called_symbols.count("AAPL") == 1

    def test_stores_fetched_prices(self, agent):
        agent._positions.get_portfolio.return_value = [_make_position("AAPL")]
        agent._positions.get_watchlist.return_value = []
        record = _make_price_record("AAPL")
        agent._fetcher.fetch_current_prices.return_value = ([record], [])
        result = agent.fetch_all_now()
        agent._market.upsert_price.assert_called_once_with(record)
        assert result.fetched == 1

    def test_failed_symbols_in_result(self, agent):
        agent._positions.get_portfolio.return_value = [_make_position("AAPL")]
        agent._positions.get_watchlist.return_value = []
        agent._fetcher.fetch_current_prices.return_value = ([], ["AAPL"])
        result = agent.fetch_all_now()
        assert "AAPL" in result.failed
        assert result.fetched == 0

    def test_fetch_history_when_requested(self, agent):
        agent._positions.get_portfolio.return_value = [_make_position("AAPL")]
        agent._positions.get_watchlist.return_value = []
        agent._fetcher.fetch_current_prices.return_value = ([], [])
        agent._fetcher.fetch_historical.return_value = []
        agent.fetch_all_now(fetch_history=True)
        agent._fetcher.fetch_historical.assert_called_once_with("AAPL", period="1y")

    def test_no_history_fetch_by_default(self, agent):
        agent._positions.get_portfolio.return_value = [_make_position("AAPL")]
        agent._positions.get_watchlist.return_value = []
        agent._fetcher.fetch_current_prices.return_value = ([], [])
        agent.fetch_all_now(fetch_history=False)
        agent._fetcher.fetch_historical.assert_not_called()

    def test_manual_types_excluded_from_fetch(self, agent):
        """Positions with auto_fetch=False (Immobilie, Festgeld) must not be fetched."""
        immobilie = Position(
            id=2, ticker=None, name="Wohnung",
            asset_class="Immobilie", investment_type="Immobilien",
            quantity=1.0, unit="Stück",
            purchase_price=300000.0, purchase_date=date(2020, 1, 1),
            added_date=date(2020, 1, 1), in_portfolio=True,
        )
        agent._positions.get_portfolio.return_value = [immobilie]
        agent._positions.get_watchlist.return_value = []
        result = agent.fetch_all_now()
        agent._fetcher.fetch_current_prices.assert_not_called()
        assert result.fetched == 0


class TestGetPortfolioValuation:
    def test_returns_valuation_with_price(self, agent):
        pos = _make_position("AAPL", quantity=10, price=150.0)
        agent._positions.get_portfolio.return_value = [pos]
        agent._market.get_price.return_value = _make_price_record("AAPL", price_eur=180.0)

        valuations = agent.get_portfolio_valuation()
        assert len(valuations) == 1
        v = valuations[0]
        assert v.current_price_eur == 180.0
        assert v.current_value_eur == 1800.0
        assert v.cost_basis_eur == 1500.0
        assert v.pnl_eur == 300.0
        assert abs(v.pnl_pct - 20.0) < 0.01

    def test_recomputes_dividend_yield_when_unreliable(self, agent):
        # Cross-currency listing: DividendRecord has rate_eur but yield_pct=None →
        # valuation derives the yield from rate_eur / price_eur (both EUR per share).
        from core.storage.models import DividendRecord
        pos = _make_position("AAPL", quantity=10, price=150.0)
        agent._positions.get_portfolio.return_value = [pos]
        agent._market.get_price.return_value = _make_price_record("AAPL", price_eur=200.0)
        agent._market.get_all_dividends.return_value = {
            "AAPL": DividendRecord(
                symbol="AAPL", rate_eur=2.0, yield_pct=None, currency="USD",
                fetched_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )
        }
        v = agent.get_portfolio_valuation()[0]
        assert v.annual_dividend_eur == pytest.approx(20.0)   # 2.0 × 10
        assert v.dividend_yield_pct == pytest.approx(0.01)    # 2.0 / 200, recomputed

    def test_returns_none_values_when_no_price(self, agent):
        agent._positions.get_portfolio.return_value = [_make_position("AAPL")]
        agent._market.get_price.return_value = None

        v = agent.get_portfolio_valuation()[0]
        assert v.current_price_eur is None
        assert v.current_value_eur is None
        assert v.pnl_eur is None

    def test_negative_pnl(self, agent):
        pos = _make_position("AAPL", quantity=10, price=200.0)
        agent._positions.get_portfolio.return_value = [pos]
        agent._market.get_price.return_value = _make_price_record("AAPL", price_eur=150.0)

        v = agent.get_portfolio_valuation()[0]
        assert v.pnl_eur == -500.0
        assert v.pnl_pct < 0

    def test_skips_positions_without_ticker(self, agent):
        pos = _make_position(ticker="AAPL")
        pos_no_ticker = Position(
            ticker=None, name="Unknown", asset_class="Aktie",
            investment_type="Wertpapiere", quantity=5, unit="Stück",
            added_date=date(2024, 1, 1), in_portfolio=True,
        )
        agent._positions.get_portfolio.return_value = [pos, pos_no_ticker]
        agent._market.get_price.return_value = _make_price_record("AAPL", price_eur=100.0)

        valuations = agent.get_portfolio_valuation()
        assert len(valuations) == 1
        assert valuations[0].symbol == "AAPL"

    def test_valuation_includes_asset_class_and_investment_type(self, agent):
        agent._positions.get_portfolio.return_value = [_make_position("AAPL")]
        agent._market.get_price.return_value = _make_price_record("AAPL")

        v = agent.get_portfolio_valuation()[0]
        assert v.asset_class == "Aktie"
        assert v.investment_type == "Wertpapiere"

    def test_get_total_value_eur(self, agent):
        agent._positions.get_portfolio.return_value = [
            _make_position("AAPL", quantity=10),
            _make_position("MSFT", quantity=5),
        ]
        agent._market.get_price.side_effect = lambda s: _make_price_record(s, price_eur=100.0)

        total = agent.get_total_value_eur()
        assert total == 1500.0

    def test_get_total_value_none_when_no_prices(self, agent):
        agent._positions.get_portfolio.return_value = [_make_position("AAPL")]
        agent._market.get_price.return_value = None
        assert agent.get_total_value_eur() is None


class TestGetPortfolioValuationIncludeWatchlist:
    def test_excludes_watchlist_by_default(self, agent):
        portfolio_pos = _make_position("AAPL")
        watchlist_pos = _make_position("MSFT")
        watchlist_pos = Position(**{**watchlist_pos.__dict__, "in_portfolio": False, "ticker": "MSFT", "name": "MSFT", "id": 2})
        agent._positions.get_portfolio.return_value = [portfolio_pos]
        agent._positions.get_watchlist.return_value = [watchlist_pos]
        agent._market.get_price.return_value = _make_price_record("AAPL")

        valuations = agent.get_portfolio_valuation()
        assert len(valuations) == 1
        assert valuations[0].symbol == "AAPL"

    def test_includes_watchlist_when_requested(self, agent):
        portfolio_pos = _make_position("AAPL")
        watchlist_pos = Position(
            id=2, ticker="MSFT", name="MSFT",
            asset_class="Aktie", investment_type="Wertpapiere",
            quantity=5, unit="Stück",
            added_date=date(2024, 1, 1), in_portfolio=False,
        )
        agent._positions.get_portfolio.return_value = [portfolio_pos]
        agent._positions.get_watchlist.return_value = [watchlist_pos]
        agent._market.get_price.side_effect = lambda s: _make_price_record(s, price_eur=100.0)

        valuations = agent.get_portfolio_valuation(include_watchlist=True)
        assert len(valuations) == 2
        symbols = {v.symbol for v in valuations}
        assert symbols == {"AAPL", "MSFT"}

    def test_in_portfolio_flag_set_correctly(self, agent):
        portfolio_pos = _make_position("AAPL")
        watchlist_pos = Position(
            id=2, ticker="MSFT", name="MSFT",
            asset_class="Aktie", investment_type="Wertpapiere",
            quantity=5, unit="Stück",
            added_date=date(2024, 1, 1), in_portfolio=False,
        )
        agent._positions.get_portfolio.return_value = [portfolio_pos]
        agent._positions.get_watchlist.return_value = [watchlist_pos]
        agent._market.get_price.side_effect = lambda s: _make_price_record(s, price_eur=100.0)

        valuations = agent.get_portfolio_valuation(include_watchlist=True)
        by_symbol = {v.symbol: v for v in valuations}
        assert by_symbol["AAPL"].in_portfolio is True
        assert by_symbol["MSFT"].in_portfolio is False


class TestDailyPnL:
    def test_day_pnl_none_when_no_prev_close(self, agent):
        pos = _make_position("AAPL", quantity=10, price=150.0)
        agent._positions.get_portfolio.return_value = [pos]
        # previous_close_eur is None by default → no day_pnl
        agent._market.get_price.return_value = _make_price_record("AAPL", price_eur=180.0)

        v = agent.get_portfolio_valuation()[0]
        assert v.day_pnl_eur is None
        assert v.day_pnl_pct is None

    def test_day_pnl_computed_when_prev_close_available(self, agent):
        pos = _make_position("AAPL", quantity=10, price=150.0)
        agent._positions.get_portfolio.return_value = [pos]
        record = _make_price_record("AAPL", price_eur=180.0)
        record = record.model_copy(update={"previous_close_eur": 175.0})
        agent._market.get_price.return_value = record

        v = agent.get_portfolio_valuation()[0]
        # current: 10 * 180 = 1800, prev: 10 * 175 = 1750 → day_pnl = +50
        assert v.day_pnl_eur == pytest.approx(50.0)
        assert v.day_pnl_pct == pytest.approx(50.0 / 1750.0 * 100)

    def test_day_pnl_negative(self, agent):
        pos = _make_position("AAPL", quantity=10, price=150.0)
        agent._positions.get_portfolio.return_value = [pos]
        record = _make_price_record("AAPL", price_eur=165.0)
        record = record.model_copy(update={"previous_close_eur": 170.0})
        agent._market.get_price.return_value = record

        v = agent.get_portfolio_valuation()[0]
        # current: 1650, prev: 1700 → -50
        assert v.day_pnl_eur == pytest.approx(-50.0)

    def test_day_pnl_none_without_previous_close(self, agent):
        pos = _make_position("AAPL", quantity=10, price=150.0)
        agent._positions.get_portfolio.return_value = [pos]
        agent._market.get_price.return_value = _make_price_record("AAPL", price_eur=180.0)
        # previous_close_eur is None by default in _make_price_record

        v = agent.get_portfolio_valuation()[0]
        assert v.day_pnl_eur is None
        assert v.day_pnl_pct is None

class TestSetupScheduler:
    def test_returns_scheduler(self, agent):
        scheduler = agent.setup_scheduler(fetch_hour=18)
        assert scheduler is not None
        jobs = scheduler.get_jobs()
        assert any(j.id == "daily_market_fetch" for j in jobs)


class TestFetchOverdue:
    """Pure decision logic for the daily-fetch catchup (no threads, no tz lookup)."""

    def test_before_fire_hour_not_overdue(self):
        now = datetime(2026, 6, 17, 17, 30, tzinfo=CEST)  # 17:30, before 18:00
        last = datetime(2026, 6, 16, 16, 42, tzinfo=timezone.utc)
        assert MarketDataAgent._is_fetch_overdue(now, last, 18) is False

    def test_last_fetch_yesterday_is_overdue(self):
        # Exactly the Samsung scenario: last fetch was yesterday 18:42 Berlin.
        now = datetime(2026, 6, 17, 19, 0, tzinfo=CEST)
        last = datetime(2026, 6, 16, 16, 42, tzinfo=timezone.utc)
        assert MarketDataAgent._is_fetch_overdue(now, last, 18) is True

    def test_already_fetched_after_fire_today_not_overdue(self):
        now = datetime(2026, 6, 17, 19, 0, tzinfo=CEST)
        last = datetime(2026, 6, 17, 16, 30, tzinfo=timezone.utc)  # 18:30 Berlin today
        assert MarketDataAgent._is_fetch_overdue(now, last, 18) is False

    def test_manual_fetch_before_fire_is_still_overdue(self):
        # A manual refresh at 15:32 Berlin is not the EOD fetch.
        now = datetime(2026, 6, 17, 19, 0, tzinfo=CEST)
        last = datetime(2026, 6, 17, 13, 32, tzinfo=timezone.utc)  # 15:32 Berlin today
        assert MarketDataAgent._is_fetch_overdue(now, last, 18) is True

    def test_no_prior_fetch_after_fire_is_overdue(self):
        now = datetime(2026, 6, 17, 19, 0, tzinfo=CEST)
        assert MarketDataAgent._is_fetch_overdue(now, None, 18) is True

    def test_no_prior_fetch_before_fire_not_overdue(self):
        now = datetime(2026, 6, 17, 8, 0, tzinfo=CEST)
        assert MarketDataAgent._is_fetch_overdue(now, None, 18) is False


class TestCatchupFetch:
    def test_triggers_scheduled_fetch_when_overdue(self, agent):
        agent.get_latest_fetch_time = MagicMock(
            return_value=datetime(2026, 6, 16, 16, 42, tzinfo=timezone.utc)
        )
        done = threading.Event()
        agent._scheduled_fetch = MagicMock(side_effect=lambda: done.set())
        now = datetime(2026, 6, 17, 19, 0, tzinfo=ZoneInfo("Europe/Berlin"))

        assert agent.catchup_fetch_if_missed(fetch_hour=18, now=now) is True
        assert done.wait(timeout=2)
        agent._scheduled_fetch.assert_called_once()

    def test_no_trigger_when_already_fetched_today(self, agent):
        agent.get_latest_fetch_time = MagicMock(
            return_value=datetime(2026, 6, 17, 16, 30, tzinfo=timezone.utc)
        )
        agent._scheduled_fetch = MagicMock()
        now = datetime(2026, 6, 17, 19, 0, tzinfo=ZoneInfo("Europe/Berlin"))

        assert agent.catchup_fetch_if_missed(fetch_hour=18, now=now) is False
        agent._scheduled_fetch.assert_not_called()
