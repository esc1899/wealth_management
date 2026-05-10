"""
Unit tests for core/macro_context.py — stale-check logic and serialization.
yfinance calls are not made; tests use mock AppConfigRepository.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from core.macro_context import (
    MacroIndicators,
    _from_dict,
    load_or_refresh_macro,
)


def _make_indicators(age_hours: float = 0.0) -> dict:
    ts = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    return {
        "vix": 18.5,
        "eur_usd": 1.082,
        "gold_eur": 3100.0,
        "dax_change_pct": -0.3,
        "fetched_at": ts,
    }


def _mock_repo(cached: dict | None) -> MagicMock:
    repo = MagicMock()
    repo.get_json.return_value = cached
    return repo


class TestFromDict:
    def test_round_trip(self):
        d = _make_indicators()
        m = _from_dict(d)
        assert m.vix == 18.5
        assert m.eur_usd == 1.082
        assert m.gold_eur == 3100.0
        assert m.dax_change_pct == -0.3

    def test_none_fields(self):
        d = {"vix": None, "eur_usd": None, "gold_eur": None, "dax_change_pct": None, "fetched_at": datetime.now(timezone.utc).isoformat()}
        m = _from_dict(d)
        assert m.vix is None
        assert m.eur_usd is None


class TestLoadOrRefreshMacro:
    def test_returns_cached_when_fresh(self):
        cached = _make_indicators(age_hours=1.0)
        repo = _mock_repo(cached)
        result = load_or_refresh_macro(repo, max_age_hours=4.0)
        assert result is not None
        assert result.vix == 18.5
        repo.set_json.assert_not_called()

    def test_fetches_when_stale(self):
        cached = _make_indicators(age_hours=5.0)
        repo = _mock_repo(cached)
        fresh = MacroIndicators(vix=20.0, eur_usd=1.09, gold_eur=3200.0, dax_change_pct=0.5, fetched_at=datetime.now(timezone.utc).isoformat())
        with patch("core.macro_context.fetch_macro_indicators", return_value=fresh):
            result = load_or_refresh_macro(repo, max_age_hours=4.0)
        assert result is not None
        assert result.vix == 20.0
        repo.set_json.assert_called_once()

    def test_fetches_when_no_cache(self):
        repo = _mock_repo(None)
        fresh = MacroIndicators(vix=15.0, eur_usd=1.07, gold_eur=2900.0, dax_change_pct=1.2, fetched_at=datetime.now(timezone.utc).isoformat())
        with patch("core.macro_context.fetch_macro_indicators", return_value=fresh):
            result = load_or_refresh_macro(repo, max_age_hours=4.0)
        assert result is not None
        assert result.vix == 15.0

    def test_returns_stale_cache_on_fetch_failure(self):
        cached = _make_indicators(age_hours=10.0)
        repo = _mock_repo(cached)
        with patch("core.macro_context.fetch_macro_indicators", side_effect=Exception("network error")):
            result = load_or_refresh_macro(repo, max_age_hours=4.0)
        assert result is not None
        assert result.vix == 18.5

    def test_returns_none_when_no_cache_and_fetch_fails(self):
        repo = _mock_repo(None)
        with patch("core.macro_context.fetch_macro_indicators", side_effect=Exception("network error")):
            result = load_or_refresh_macro(repo, max_age_hours=4.0)
        assert result is None
