"""Tests for WatchlistCheckerAgent — parsing and data flow."""

import pytest
from datetime import date
from agents.watchlist_checker_agent import (
    WatchlistFit,
    WatchlistCheckResult,
    _parse_watchlist_results,
)
from core.storage.models import Position


def make_position(**kwargs):
    """Helper to create Position with all required fields."""
    defaults = {
        "id": 1,
        "asset_class": "Aktie",
        "investment_type": "Stock",
        "name": "Test",
        "ticker": "TST",
        "unit": "EUR",
        "added_date": date.today(),
        "in_portfolio": False,
        "in_watchlist": True,
    }
    defaults.update(kwargs)
    return Position(**defaults)


class TestParseWatchlistResults:
    """Test parsing of LLM responses into structured verdicts."""

    def test_parse_single_position(self):
        """Parse single position with verdict."""
        positions = [
            make_position(
                id=1,
                name="Apple",
                ticker="AAPL",
            )
        ]

        response = """## Apple (AAPL)
**Fit:** 🟢 Sehr passend

> Füllt Lücke im Tech-Portfolio

Gute Fundamentals und passt zur Story."""

        fits = _parse_watchlist_results(positions, response)

        assert len(fits) == 1
        assert fits[0].position_id == 1
        assert fits[0].verdict == "sehr_passend"
        assert "Lücke" in fits[0].summary

    def test_parse_multiple_positions(self):
        """Parse multiple positions."""
        positions = [
            make_position(id=1, name="Apple", ticker="AAPL"),
            make_position(id=2, asset_class="Anleihe", name="German Bund", ticker="BU100"),
        ]

        response = """## Apple (AAPL)
**Fit:** 🟢 Sehr passend

> Tech exposure needed

Details here.

---

## German Bund (BU100)
**Fit:** 🟡 Passend

> Stabilisierung des Portfolios

Aber nicht dringend."""

        fits = _parse_watchlist_results(positions, response)

        assert len(fits) == 2
        assert fits[0].position_id == 1
        assert fits[0].verdict == "sehr_passend"
        assert fits[1].position_id == 2
        assert fits[1].verdict == "passend"

    def test_parse_all_verdicts(self):
        """Parse all four verdict types."""
        positions = [
            make_position(id=i, name=f"Stock{i}", ticker=f"STK{i}")
            for i in range(1, 5)
        ]

        response = """## Stock1 (STK1)
**Fit:** 🟢 Sehr passend
> Very good

## Stock2 (STK2)
**Fit:** 🟡 Passend
> OK

## Stock3 (STK3)
**Fit:** ⚪ Neutral
> Neither good nor bad

## Stock4 (STK4)
**Fit:** 🔴 Nicht passend
> Doesn't fit"""

        fits = _parse_watchlist_results(positions, response)

        assert len(fits) == 4
        verdicts = [f.verdict for f in fits]
        assert "sehr_passend" in verdicts
        assert "passend" in verdicts
        assert "neutral" in verdicts
        assert "nicht_passend" in verdicts

    def test_parse_empty_response(self):
        """Parse empty response returns empty list."""
        positions = [make_position()]

        fits = _parse_watchlist_results(positions, "")
        assert fits == []

    def test_parse_no_matching_positions(self):
        """Parse response with no matching position headers."""
        positions = [make_position(name="Apple", ticker="AAPL")]

        response = """## Unknown Stock (UNK)
**Fit:** 🟢 Sehr passend
> Some text"""

        fits = _parse_watchlist_results(positions, response)
        # Position not in lookup, so no match
        assert len(fits) == 0
