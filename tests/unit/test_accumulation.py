"""Unit tests for core/accumulation.py — pure, deterministic, no DB/network."""

from types import SimpleNamespace

import pytest

from core.accumulation import (
    compute_accumulation,
    accumulation_for_position,
    YIELD_SOLID,
    YIELD_WEAK,
    GREEN,
    YELLOW,
    RED,
    GREY,
)


def _ratings(result):
    return {c.name.split(".")[-1].replace("comp_", ""): c.rating for c in result.components}


class TestVerdictPaths:
    def test_akkumulieren_intact_solid_cheap(self):
        r = compute_accumulation(0.03, "intact", "unterbewertet")
        assert r.verdict == "akkumulieren"
        assert r.binding is None

    def test_akkumulieren_intact_solid_fair(self):
        assert compute_accumulation(0.03, "intact", "fair").verdict == "akkumulieren"

    def test_akkumulieren_intact_solid_unknown_valuation(self):
        assert compute_accumulation(0.03, "intact", None).verdict == "akkumulieren"

    def test_halten_when_overvalued(self):
        r = compute_accumulation(0.03, "intact", "überbewertet")
        assert r.verdict == "halten"
        assert r.binding == "accumulation.binding_valuation"

    def test_halten_weak_yield_but_intact(self):
        r = compute_accumulation(0.005, "intact", "fair")
        assert r.verdict == "halten"
        assert r.binding == "accumulation.binding_engine"

    def test_fallen_verdacht_broken_story_with_yield(self):
        r = compute_accumulation(0.04, "gefährdet", "fair")
        assert r.verdict == "fallen_verdacht"
        assert r.binding == "accumulation.binding_survival"

    def test_ungeeignet_broken_story_weak_yield(self):
        r = compute_accumulation(0.005, "gefährdet", "fair")
        assert r.verdict == "ungeeignet"
        assert r.binding == "accumulation.binding_survival"

    def test_na_takes_precedence_over_broken_story(self):
        # No dividend → indicator n/a regardless of story (story risk shown by other checkers).
        r = compute_accumulation(None, "gefährdet", None)
        assert r.verdict == "nicht_anwendbar"
        assert r.binding == "accumulation.binding_no_dividend"

    def test_na_for_non_payer(self):
        for y in (None, 0.0):
            r = compute_accumulation(y, "intact", "fair")
            assert r.verdict == "nicht_anwendbar"
            assert r.binding == "accumulation.binding_no_dividend"

    def test_pruefen_no_verdicts(self):
        r = compute_accumulation(0.03, None, None)
        assert r.verdict == "prüfen"
        assert r.binding == "accumulation.binding_verdicts"

    def test_pruefen_mixed_story(self):
        r = compute_accumulation(0.03, "gemischt", "fair")
        assert r.verdict == "prüfen"
        assert r.binding == "accumulation.binding_survival"

    def test_pruefen_moderate_yield(self):
        r = compute_accumulation(0.02, "intact", "fair")
        assert r.verdict == "prüfen"
        assert r.binding == "accumulation.binding_engine"


class TestEngineBands:
    def test_solid_boundary_inclusive(self):
        assert _ratings(compute_accumulation(YIELD_SOLID, "intact", "fair"))["engine"] == GREEN

    def test_moderate_band(self):
        assert _ratings(compute_accumulation(YIELD_WEAK, "intact", "fair"))["engine"] == YELLOW

    def test_weak_below_threshold(self):
        assert _ratings(compute_accumulation(YIELD_WEAK - 0.001, "intact", "fair"))["engine"] == RED

    def test_none_yield_is_grey(self):
        assert _ratings(compute_accumulation(None, "intact", "fair"))["engine"] == GREY


class TestComponentRatings:
    def test_survival_and_valuation_mapping(self):
        r = compute_accumulation(0.03, "gemischt", "überbewertet")
        ratings = _ratings(r)
        assert ratings["survival"] == YELLOW
        assert ratings["valuation"] == RED

    def test_unknown_inputs_are_grey(self):
        ratings = _ratings(compute_accumulation(0.03, None, None))
        assert ratings["survival"] == GREY
        assert ratings["valuation"] == GREY

    def test_engine_value_formatted_as_percent(self):
        comp = compute_accumulation(0.0284, "intact", "fair").components[0]
        assert comp.value == "2.8 %"

    def test_missing_yield_value_dash(self):
        assert compute_accumulation(None, "intact", "fair").components[0].value == "—"


class TestAccumulationForPosition:
    def test_resolves_yield_and_verdicts(self):
        yield_map = {"AAPL": 0.03}
        sc = SimpleNamespace(verdict="intact")
        fa = SimpleNamespace(verdict="unterbewertet")
        r = accumulation_for_position("aapl", sc, fa, yield_map)  # lowercase ticker → upper lookup
        assert r.verdict == "akkumulieren"

    def test_missing_ticker_and_verdicts_graceful(self):
        # no ticker → no yield → dividend indicator not applicable
        r = accumulation_for_position(None, None, None, {})
        assert r.verdict == "nicht_anwendbar"

    def test_ticker_not_in_yield_map(self):
        r = accumulation_for_position("XYZ", SimpleNamespace(verdict="intact"), None, {})
        # no yield → non-payer → n/a, not a low score
        assert r.verdict == "nicht_anwendbar"

    def test_none_yield_in_map(self):
        r = accumulation_for_position("ALV.DE", SimpleNamespace(verdict="intact"), None, {"ALV.DE": None})
        assert r.verdict == "nicht_anwendbar"

    def test_override_yield_makes_accumulate(self):
        # the bug fix: yield from valuation layer (0.045) flows through
        r = accumulation_for_position(
            "ALV.DE", SimpleNamespace(verdict="intact"), SimpleNamespace(verdict="fair"),
            {"ALV.DE": 0.045},
        )
        assert r.verdict == "akkumulieren"
