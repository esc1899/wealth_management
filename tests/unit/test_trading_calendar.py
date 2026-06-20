"""Unit tests for core/trading_calendar.py — pure date logic."""

from datetime import date

from core.trading_calendar import is_trading_day, last_trading_day


class TestIsTradingDay:
    def test_weekdays_are_trading_days(self):
        # 2026-06-15 is a Monday … 2026-06-19 a Friday
        for day in range(15, 20):
            assert is_trading_day(date(2026, 6, day)) is True

    def test_weekend_is_not_trading_day(self):
        assert is_trading_day(date(2026, 6, 20)) is False  # Saturday
        assert is_trading_day(date(2026, 6, 21)) is False  # Sunday


class TestLastTradingDay:
    def test_weekday_returns_itself(self):
        assert last_trading_day(date(2026, 6, 18)) == date(2026, 6, 18)  # Thursday

    def test_saturday_returns_friday(self):
        assert last_trading_day(date(2026, 6, 20)) == date(2026, 6, 19)

    def test_sunday_returns_friday(self):
        assert last_trading_day(date(2026, 6, 21)) == date(2026, 6, 19)
