"""Unit tests for core/position_metrics.py — pure, deterministic, no DB/network."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from core.position_metrics import compute_return_metrics, build_metrics_block


def _hist(start: date, days: int, start_price: float, daily: float = 0.0):
    """Build `days` consecutive daily points starting at start_price, +daily each day."""
    return [
        SimpleNamespace(date=start + timedelta(days=i), close_eur=start_price + daily * i)
        for i in range(days)
    ]


class TestComputeReturnMetrics:
    def test_empty_history(self):
        m = compute_return_metrics([], date(2026, 6, 18))
        assert m["current_price"] is None
        assert all(m[k] is None for k in m)

    def test_current_price_is_last_close(self):
        hist = _hist(date(2025, 4, 1), 60, 100.0, daily=1.0)
        m = compute_return_metrics(hist)
        assert m["current_price"] == pytest.approx(100.0 + 59.0)

    def test_ytd_from_prior_year_close(self):
        # Dec 31 2025 close = 100, last close (Jan 2026) = 110 → YTD +10%
        hist = [
            SimpleNamespace(date=date(2025, 12, 31), close_eur=100.0),
            SimpleNamespace(date=date(2026, 1, 15), close_eur=110.0),
        ]
        m = compute_return_metrics(hist, date(2026, 1, 15))
        assert m["ytd"] == pytest.approx(10.0)

    def test_trailing_window_within_tolerance(self):
        # ~14 months of flat-then-up data: 1y window available, 3y/5y not.
        hist = _hist(date(2025, 4, 1), 440, 100.0, daily=0.0)
        # bump last price to +20%
        hist[-1] = SimpleNamespace(date=hist[-1].date, close_eur=120.0)
        m = compute_return_metrics(hist)
        assert m["r1y"] == pytest.approx(20.0)   # 100 → 120
        assert m["r3y"] is None
        assert m["r5y"] is None

    def test_short_history_no_long_windows(self):
        hist = _hist(date(2026, 5, 1), 20, 100.0)
        m = compute_return_metrics(hist)
        assert m["r3m"] is None and m["r6m"] is None and m["r1y"] is None


class TestBuildMetricsBlock:
    def test_empty_history_returns_empty(self):
        assert build_metrics_block([], date(2026, 6, 18)) == ""

    def test_block_marks_unavailable_windows(self):
        hist = _hist(date(2025, 4, 1), 440, 100.0, daily=0.0)
        block = build_metrics_block(hist, language="de")
        assert "Verifizierte Kennzahlen" in block
        assert "3J: nicht verfügbar" in block
        assert "5J: nicht verfügbar" in block
        # the explicit anti-confabulation note
        assert "nicht als 0" in block

    def test_block_english(self):
        hist = _hist(date(2025, 4, 1), 440, 100.0, daily=0.0)
        block = build_metrics_block(hist, language="en")
        assert "Verified metrics" in block
        assert "3Y: not available" in block
        assert "current price" in block.lower()
