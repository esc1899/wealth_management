"""
Accumulation indicator (FEAT-68 B1) — deterministic, pure, no LLM / no network.

Per position it derives an *accumulation expectation* verdict from data that already exists:
the income engine — Total Shareholder Yield = dividend yield + net buyback yield (FEAT-71) —
gated by the stored LLM verdicts as a quality/survival proxy — Storychecker ("is the thesis
intact?") and Fundamental Analyzer ("cheap / fair / expensive?"). The indicator only *reads*
yields + verdict codes and applies a fixed rule; it never calls a model, so it is cheap,
reproducible and carries no privacy or prompt-injection surface. The buyback half makes
buyback-driven compounders (Amazon, much of US-tech) measurable instead of "not applicable".

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
    # Decomposition of the income engine into dividend + buyback (FEAT-71). Populated only
    # when buyback data is available; informational rows (no own traffic light) so the user
    # sees what makes up the rated Total Shareholder Yield. Empty when dividend-only.
    engine_parts: List[AccumulationComponent] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.engine_parts is None:
            self.engine_parts = []


def _rate_yield(value: Optional[float]) -> str:
    """Band a yield decimal to a traffic light (no string formatting)."""
    if value is None:
        return GREY
    if value >= YIELD_SOLID:
        return GREEN
    if value >= YIELD_WEAK:
        return YELLOW
    return RED


def _fmt_pct(value: Optional[float], dash: str = "—") -> str:
    return dash if value is None else f"{value * 100:.1f} %"


def _engine(total_yield: Optional[float]) -> tuple[str, str]:
    """Return (value_str, rating) for the Total Shareholder Yield income engine."""
    return (_fmt_pct(total_yield), _rate_yield(total_yield))


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
    buyback_pct: Optional[float] = None,
) -> AccumulationResult:
    """Derive the accumulation-expectation verdict from Total Shareholder Yield + verdicts.

    The engine is ``yield_pct`` (dividend) + ``buyback_pct`` (net buyback yield); either may
    be ``None``. When ``buyback_pct`` is given, the engine is exposed as a Total Shareholder
    Yield row plus dividend/buyback breakdown rows in ``engine_parts``; otherwise it stays a
    plain dividend row (backward compatible).

    Deterministic rule (order = priority):
        survival gefährdet            → fallen_verdacht (engine not weak) | ungeeignet
        Story None AND FA None        → prüfen
        valuation teuer               → halten
        engine schwach                → halten (survival intakt) | prüfen
        survival intakt AND engine solide (valuation günstig/fair/unbekannt) → akkumulieren
        else (gemischt / engine mäßig / valuation unbekannt)                 → prüfen
    """
    # Total Shareholder Yield = sum of the present parts; None only if both are absent.
    total = None if (yield_pct is None and buyback_pct is None) else (yield_pct or 0.0) + (buyback_pct or 0.0)

    eng_val, eng_rating = _engine(total)
    surv_val, surv_rating = _survival(story_verdict)
    val_val, val_rating = _valuation(fa_verdict)

    # Engine label: Total Shareholder Yield once a buyback figure exists, else plain dividend.
    eng_key = "accumulation.comp_tsy" if buyback_pct is not None else "accumulation.comp_engine"
    components = [
        AccumulationComponent(eng_key, eng_val, eng_rating),
        AccumulationComponent("accumulation.comp_survival", surv_val, surv_rating),
        AccumulationComponent("accumulation.comp_valuation", val_val, val_rating),
    ]
    # Informational breakdown rows (no own light) — only when we actually have buyback data.
    engine_parts: List[AccumulationComponent] = []
    if buyback_pct is not None:
        engine_parts = [
            AccumulationComponent("accumulation.comp_dividend", _fmt_pct(yield_pct, dash="n/a"), ""),
            AccumulationComponent("accumulation.comp_buyback", _fmt_pct(buyback_pct, dash="n/a"), ""),
        ]

    # No capital return at all (no dividend, no buyback, or it nets to zero) → the indicator
    # does not apply. Mark n/a instead of scoring it low — story risk, if any, is surfaced by
    # the other checkers.
    if total is None or total <= 0:
        return AccumulationResult(
            verdict="nicht_anwendbar",
            components=components,
            binding="accumulation.binding_no_dividend",
            engine_parts=engine_parts,
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

    return AccumulationResult(
        verdict=verdict, components=components, binding=binding, engine_parts=engine_parts
    )


def accumulation_for_position(
    ticker, sc_verdict_obj, fa_verdict_obj, yield_map, buyback_map=None
) -> AccumulationResult:
    """Convenience wrapper for pages: resolve yield + verdict codes, then compute.

    ``yield_map`` is a dict {symbol(upper) -> dividend_yield_pct (decimal) or None}. Build it
    from the *valuation* layer (``get_portfolio_valuation`` → ``v.dividend_yield_pct``), which
    applies overrides and cross-currency derivation — NOT from the raw ``dividend_data`` table,
    whose ``yield_pct`` is often None even when a dividend exists. ``buyback_map`` (optional)
    is {symbol(upper) -> net buyback yield (decimal) or None} from ``core.shareholder_yield``;
    when absent the engine is dividend-only. ``sc_verdict_obj`` / ``fa_verdict_obj`` are
    PositionAnalysis-like (with .verdict) or None.
    """
    key = ticker.upper() if ticker else None
    yield_pct = yield_map.get(key) if key else None
    buyback_pct = buyback_map.get(key) if (buyback_map and key) else None
    sc = sc_verdict_obj.verdict if sc_verdict_obj else None
    fa = fa_verdict_obj.verdict if fa_verdict_obj else None
    return compute_accumulation(yield_pct, sc, fa, buyback_pct)
