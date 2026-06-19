"""Unit tests for storychecker prompt building — asset-class fairness + format invariants."""

from datetime import date

from core.storage.models import Position
from agents.storychecker_agent import _build_system_prompt, _build_initial_message


def _pos(asset_class: str, name: str = "Test", ticker: str = "T", story: str = "These") -> Position:
    return Position(
        name=name, ticker=ticker, asset_class=asset_class,
        investment_type="Wertpapiere", quantity=1.0, unit="Stück",
        purchase_price=100.0, purchase_date=date(2020, 1, 1), added_date=date.today(),
        in_portfolio=True, story=story,
    )


class TestBuildSystemPrompt:
    def test_fund_class_gets_fund_framing(self):
        p = _build_system_prompt("Infrastrukturfonds", "de")
        assert "Fonds-Analyst" in p
        # explicit guard against the unfair cross-category comparison
        assert "Aktienfonds" in p and "NICHT" in p
        # company-only signals must NOT drive a fund analysis
        assert "Quartalszahlen" not in p

    def test_rentenfonds_also_fund(self):
        assert "Fonds-Analyst" in _build_system_prompt("Rentenfonds", "de")

    def test_stock_class_gets_company_framing(self):
        p = _build_system_prompt("Aktie", "de")
        assert "Quartalszahlen" in p
        assert "Fonds-Analyst" not in p

    def test_none_falls_back_to_company(self):
        assert "Quartalszahlen" in _build_system_prompt(None, "de")

    def test_format_markers_present_in_both(self):
        # _extract_verdict / _extract_summary depend on these — must survive in both variants.
        for ac in ("Aktie", "Infrastrukturfonds"):
            p = _build_system_prompt(ac, "de")
            assert "## Story-Check" in p
            assert "🟢" in p and "🟡" in p and "🔴" in p
            assert "> {EIN-SATZ-FAZIT}" in p


class TestBuildInitialMessage:
    def test_fund_labelled_as_fonds(self):
        msg = _build_initial_message(_pos("Infrastrukturfonds"))
        assert "**Fonds:**" in msg
        assert "**Unternehmen:**" not in msg

    def test_stock_labelled_as_unternehmen(self):
        msg = _build_initial_message(_pos("Aktie"))
        assert "**Unternehmen:**" in msg
        assert "**Fonds:**" not in msg

    def test_metrics_block_appended_when_present(self):
        msg = _build_initial_message(_pos("Aktie"), metrics_block="**Verifizierte Kennzahlen ...**")
        assert "Verifizierte Kennzahlen" in msg

    def test_no_metrics_block_by_default(self):
        assert "Verifizierte Kennzahlen" not in _build_initial_message(_pos("Aktie"))
