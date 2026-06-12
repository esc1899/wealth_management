"""Unit tests for core/cowork/parser.py."""

from datetime import date
from pathlib import Path
from typing import Optional

import pytest

from core.cowork.parser import (
    ParseError,
    parse_research_string,
    parse_research_file,
    VALID_TYPES,
    VALID_STATUSES,
)


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "sample_research.md"

_BASE_FM = {
    "research_id": "test-001",
    "type": "stock_analysis",
    "date": "2026-05-08",
    "ai_generated": True,
    "model": "test-model",
    "status": "ready_for_import",
    "disclaimer": "Test disclaimer.",
    "sources": ["https://example.com"],
    "watchlist_candidates": [],
}

_MINIMAL_CANDIDATE = {
    "ticker": "AAPL",
    "name": "Apple",
    "exchange": "NASDAQ",
    "rationale": "Test rationale.",
    "conviction": "high",
    "suggested_action": "add",
}


def _make_minimal(overrides: Optional[dict] = None) -> str:
    """Return a minimal valid research file string with optional field overrides."""
    import yaml as _yaml
    fm = dict(_BASE_FM)
    if overrides:
        fm.update(overrides)
    fm_text = _yaml.dump(fm, allow_unicode=True, sort_keys=False)
    return f"---\n{fm_text}---\n\nBody text here.\n"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestValidParse:
    def test_fixture_file_parses(self):
        result = parse_research_file(str(FIXTURE_PATH))
        assert result.research_id == "2026-05-08-aapl-001"
        assert result.type == "stock_analysis"
        assert result.date == date(2026, 5, 8)
        assert result.status == "ready_for_import"
        assert result.model == "claude-sonnet-4-6"
        assert result.ai_generated is True
        assert result.disclaimer != ""
        assert len(result.sources) == 2

    def test_fixture_primary(self):
        result = parse_research_file(str(FIXTURE_PATH))
        assert result.primary is not None
        assert result.primary.ticker == "AAPL"
        assert result.primary.exchange == "NASDAQ"
        assert result.primary.sentiment == "positive"
        assert result.primary.confidence == "high"

    def test_fixture_candidates(self):
        result = parse_research_file(str(FIXTURE_PATH))
        assert len(result.watchlist_candidates) == 2
        aapl = result.watchlist_candidates[0]
        assert aapl.ticker == "AAPL"
        assert aapl.conviction == "high"
        assert aapl.suggested_action == "add"
        assert aapl.price_at_research == 189.50
        assert aapl.target_price == 220.00
        assert len(aapl.triggers) == 2

    def test_fixture_body(self):
        result = parse_research_file(str(FIXTURE_PATH))
        assert "# Summary" in result.body_markdown
        assert "Apple" in result.body_markdown

    def test_empty_candidates_list(self):
        text = _make_minimal()
        result = parse_research_string(text)
        assert result.watchlist_candidates == []

    def test_no_primary_is_optional(self):
        text = _make_minimal()
        result = parse_research_string(text)
        assert result.primary is None

    def test_ticker_normalized_to_uppercase(self):
        text = _make_minimal({
            "watchlist_candidates": [dict(_MINIMAL_CANDIDATE, ticker="aapl", exchange="nasdaq")],
        })
        result = parse_research_string(text)
        cand = result.watchlist_candidates[0]
        assert cand.ticker == "AAPL"
        assert cand.exchange == "NASDAQ"

    def test_date_as_date_object(self):
        text = _make_minimal()
        result = parse_research_string(text)
        assert isinstance(result.date, date)

    def test_all_valid_types(self):
        for rtype in VALID_TYPES:
            text = _make_minimal({"type": rtype})
            result = parse_research_string(text)
            assert result.type == rtype

    def test_all_valid_statuses(self):
        for status in VALID_STATUSES:
            text = _make_minimal({"status": status})
            result = parse_research_string(text)
            assert result.status == status


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------

class TestMissingFields:
    @pytest.mark.parametrize("field", [
        "research_id", "type", "date", "model", "status", "disclaimer",
    ])
    def test_missing_top_level_field(self, field):
        text = _make_minimal({field: ""})
        with pytest.raises(ParseError, match=field):
            parse_research_string(text)

    def test_missing_watchlist_candidates_key(self):
        import yaml as _yaml
        fm = {k: v for k, v in _BASE_FM.items() if k != "watchlist_candidates"}
        fm_text = _yaml.dump(fm, allow_unicode=True)
        text = f"---\n{fm_text}---\nbody"
        with pytest.raises(ParseError, match="watchlist_candidates"):
            parse_research_string(text)

    def test_candidate_missing_ticker(self):
        cand = {k: v for k, v in _MINIMAL_CANDIDATE.items() if k != "ticker"}
        text = _make_minimal({"watchlist_candidates": [cand]})
        with pytest.raises(ParseError):
            parse_research_string(text)

    def test_candidate_missing_rationale(self):
        cand = {k: v for k, v in _MINIMAL_CANDIDATE.items() if k != "rationale"}
        text = _make_minimal({"watchlist_candidates": [cand]})
        with pytest.raises(ParseError):
            parse_research_string(text)


# ---------------------------------------------------------------------------
# Invalid enum values
# ---------------------------------------------------------------------------

class TestInvalidEnums:
    def test_invalid_type(self):
        with pytest.raises(ParseError, match="type"):
            parse_research_string(_make_minimal({"type": "unknown_type"}))

    def test_invalid_status(self):
        with pytest.raises(ParseError, match="status"):
            parse_research_string(_make_minimal({"status": "pending"}))

    def test_invalid_conviction(self):
        cand = dict(_MINIMAL_CANDIDATE, conviction="extreme")
        text = _make_minimal({"watchlist_candidates": [cand]})
        with pytest.raises(ParseError, match="conviction"):
            parse_research_string(text)

    def test_invalid_suggested_action(self):
        cand = dict(_MINIMAL_CANDIDATE, suggested_action="buy")
        text = _make_minimal({"watchlist_candidates": [cand]})
        with pytest.raises(ParseError, match="suggested_action"):
            parse_research_string(text)

    def test_invalid_primary_sentiment(self):
        text = _make_minimal({
            "primary": {
                "ticker": "AAPL",
                "name": "Apple",
                "exchange": "NASDAQ",
                "sentiment": "very_bullish",
            },
        })
        with pytest.raises(ParseError, match="sentiment"):
            parse_research_string(text)


# ---------------------------------------------------------------------------
# Structural errors
# ---------------------------------------------------------------------------

class TestStructuralErrors:
    def test_no_frontmatter_delimiter(self):
        with pytest.raises(ParseError, match="frontmatter"):
            parse_research_string("Just plain text without frontmatter")

    def test_invalid_yaml(self):
        bad = "---\nresearch_id: [\nbroken yaml\n---\nbody"
        with pytest.raises(ParseError):
            parse_research_string(bad)

    def test_empty_file(self):
        with pytest.raises(ParseError):
            parse_research_string("")

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ParseError, match="Cannot read"):
            parse_research_file(str(tmp_path / "nonexistent.md"))


# ---------------------------------------------------------------------------
# request_id (Verknüpfung zur Research-Queue)
# ---------------------------------------------------------------------------

class TestRequestId:
    def test_request_id_parsed(self):
        result = parse_research_string(_make_minimal({"request_id": 4}))
        assert result.request_id == 4

    def test_request_id_string_coerced(self):
        result = parse_research_string(_make_minimal({"request_id": "7"}))
        assert result.request_id == 7

    def test_request_id_absent_is_none(self):
        result = parse_research_string(_make_minimal())
        assert result.request_id is None

    def test_request_id_non_numeric_raises(self):
        with pytest.raises(ParseError, match="request_id"):
            parse_research_string(_make_minimal({"request_id": "abc"}))

    def test_request_id_zero_raises(self):
        with pytest.raises(ParseError, match="positive"):
            parse_research_string(_make_minimal({"request_id": 0}))

    def test_request_id_negative_raises(self):
        with pytest.raises(ParseError, match="positive"):
            parse_research_string(_make_minimal({"request_id": -3}))
