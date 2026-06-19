"""
Accumulation indicator (FEAT-68 B1) — deterministic, pure, no LLM / no network.

Per position it derives an *accumulation expectation* verdict from data that already exists:
the current dividend yield (the income engine) gated by the stored LLM verdicts as a
quality/survival proxy — Storychecker ("is the thesis intact?") and Fundamental Analyzer
("cheap / fair / expensive?"). The indicator only *reads* verdict codes + yield and applies
a fixed rule; it never calls a model, so it is cheap, reproducible and carries no privacy or
prompt-injection surface.

Transparency is the design principle: every input is exposed as a component (raw value +
traffic-light rating), and ``binding`` names the component that caps the verdict ("what holds
it back?"). Honest limit: backward-looking — a screen, not a verdict; B2 (realised share
ratchet, dividend growth, fundamentals) adds the ex-post axis later without changing B1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

# Engine bands — yield_pct is a decimal (0.015 = 1.5 %), see core/storage/models.py.
YIELD_SOLID = 0.025
YIELD_WEAK = 0.012

# Ratings
GREEN = "🟢"
YELLOW = "🟡"
RED = "🔴"
GREY = "⚪"


@dataclass
class AccumulationComponent:
    """One transparent input to the indicator: i18n label key + raw value + rating."""

    name: str          # i18n key, e.g. "accumulation.comp_engine"
    value: str         # human-readable raw value, e.g. "2.8 %" / "intakt" / "—"
    rating: str        # GREEN / YELLOW / RED / GREY


@dataclass
class AccumulationResult:
    """The verdict plus its transparent breakdown."""

    verdict: str                          # akkumulieren/halten/prüfen/fallen_verdacht/ungeeignet
    components: List[AccumulationComponent]
    binding: Optional[str]                # i18n key of the limiting factor, or None


def _engine(yield_pct: Optional[float]) -> tuple[str, str]:
    """Return (value_str, rating) for the income engine."""
    if yield_pct is None:
        return ("—", GREY)
    value = f"{yield_pct * 100:.1f} %"
    if yield_pct >= YIELD_SOLID:
        return (value, GREEN)
    if yield_pct >= YIELD_WEAK:
        return (value, YELLOW)
    return (value, RED)


def _survival(story_verdict: Optional[str]) -> tuple[str, str]:
    return {
        "intact": ("intakt", GREEN),
        "gemischt": ("gemischt", YELLOW),
        "gefährdet": ("gefährdet", RED),
    }.get(story_verdict, ("unbekannt", GREY))


def _valuation(fa_verdict: Optional[str]) -> tuple[str, str]:
    return {
        "unterbewertet": ("günstig", GREEN),
        "fair": ("fair", YELLOW),
        "überbewertet": ("teuer", RED),
    }.get(fa_verdict, ("unbekannt", GREY))


def compute_accumulation(
    yield_pct: Optional[float],
    story_verdict: Optional[str],
    fa_verdict: Optional[str],
) -> AccumulationResult:
    """Derive the accumulation-expectation verdict from yield + Story + FA verdicts.

    Deterministic rule (order = priority):
        survival gefährdet            → fallen_verdacht (engine not weak) | ungeeignet
        Story None AND FA None        → prüfen
        valuation teuer               → halten
        engine schwach                → halten (survival intakt) | prüfen
        survival intakt AND engine solide (valuation günstig/fair/unbekannt) → akkumulieren
        else (gemischt / engine mäßig / valuation unbekannt)                 → prüfen
    """
    eng_val, eng_rating = _engine(yield_pct)
    surv_val, surv_rating = _survival(story_verdict)
    val_val, val_rating = _valuation(fa_verdict)

    components = [
        AccumulationComponent("accumulation.comp_engine", eng_val, eng_rating),
        AccumulationComponent("accumulation.comp_survival", surv_val, surv_rating),
        AccumulationComponent("accumulation.comp_valuation", val_val, val_rating),
    ]

    # No (meaningful) dividend → this is a dividend-accumulation indicator, so it simply does
    # not apply (e.g. Amazon). Mark n/a instead of scoring it low — the position's story risk,
    # if any, is surfaced by the other checkers.
    if yield_pct is None or yield_pct <= 0:
        return AccumulationResult(
            verdict="nicht_anwendbar",
            components=components,
            binding="accumulation.binding_no_dividend",
        )

    engine_present = eng_rating in (GREEN, YELLOW)

    if surv_rating == RED:  # thesis gefährdet — the iteration may not survive
        verdict = "fallen_verdacht" if engine_present else "ungeeignet"
        binding = "accumulation.binding_survival"
    elif story_verdict is None and fa_verdict is None:
        verdict = "prüfen"
        binding = "accumulation.binding_verdicts"
    elif val_rating == RED:  # gute Substanz, aber teuer
        verdict = "halten"
        binding = "accumulation.binding_valuation"
    elif eng_rating == RED:  # kein nennenswerter Income-Motor
        verdict = "halten" if surv_rating == GREEN else "prüfen"
        binding = "accumulation.binding_engine"
    elif surv_rating == GREEN and eng_rating == GREEN:
        verdict = "akkumulieren"
        binding = None
    else:  # gemischtes Survival, mäßige Rendite oder unbekannte Bewertung
        verdict = "prüfen"
        # Schwächstes nicht-grünes Glied benennen
        if surv_rating in (YELLOW, GREY):
            binding = "accumulation.binding_survival"
        elif eng_rating == YELLOW:
            binding = "accumulation.binding_engine"
        else:
            binding = "accumulation.binding_valuation"

    return AccumulationResult(verdict=verdict, components=components, binding=binding)


def accumulation_for_position(ticker, sc_verdict_obj, fa_verdict_obj, yield_map) -> AccumulationResult:
    """Convenience wrapper for pages: resolve yield + verdict codes, then compute.

    ``yield_map`` is a dict {symbol(upper) -> dividend_yield_pct (decimal) or None}. Build it
    from the *valuation* layer (``get_portfolio_valuation`` → ``v.dividend_yield_pct``), which
    applies overrides and cross-currency derivation — NOT from the raw ``dividend_data`` table,
    whose ``yield_pct`` is often None even when a dividend exists. ``sc_verdict_obj`` /
    ``fa_verdict_obj`` are PositionAnalysis-like (with .verdict) or None.
    """
    yield_pct = yield_map.get(ticker.upper()) if ticker else None
    sc = sc_verdict_obj.verdict if sc_verdict_obj else None
    fa = fa_verdict_obj.verdict if fa_verdict_obj else None
    return compute_accumulation(yield_pct, sc, fa)
