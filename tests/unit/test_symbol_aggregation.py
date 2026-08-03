"""Aggregation of per-position valuations into one row per symbol.

Regression: the same ticker in two depots produced two chart rows; the bar was
sorted by the first position's value and the second stacked on top afterwards.
"""

from dataclasses import dataclass
from typing import Optional

import pytest

from core.symbol_aggregation import (
    aggregate_contributions,
    aggregate_day_pnl,
    aggregate_pnl,
    make_start_qty_resolver,
)


@dataclass
class FakeValuation:
    symbol: str
    day_pnl_eur: Optional[float] = None
    day_pnl_pct: Optional[float] = None
    pnl_eur: Optional[float] = None
    pnl_pct: Optional[float] = None
    cost_basis_eur: Optional[float] = None
    current_value_eur: Optional[float] = None
    quantity: Optional[float] = None


@dataclass
class FakeAttributionRow:
    symbol: str
    contribution_eur: float
    start_value_eur: Optional[float] = None


class TestAggregateDayPnL:
    def test_same_symbol_in_two_depots_is_one_row(self):
        vals = [
            FakeValuation("SAP.DE", day_pnl_eur=10.0, current_value_eur=110.0),
            FakeValuation("SAP.DE", day_pnl_eur=30.0, current_value_eur=330.0),
        ]
        result = aggregate_day_pnl(vals)
        assert len(result) == 1
        assert result[0].symbol == "SAP.DE"
        assert result[0].day_pnl_eur == 40.0

    def test_percentage_uses_summed_previous_value(self):
        # prev values 100 + 300 = 400, gain 40 -> 10 %
        vals = [
            FakeValuation("SAP.DE", day_pnl_eur=10.0, current_value_eur=110.0),
            FakeValuation("SAP.DE", day_pnl_eur=30.0, current_value_eur=330.0),
        ]
        assert aggregate_day_pnl(vals)[0].day_pnl_pct == 10.0

    def test_single_position_percentage_matches_agent_value(self):
        v = FakeValuation("AAPL", day_pnl_eur=5.0, day_pnl_pct=5.0, current_value_eur=105.0)
        assert aggregate_day_pnl([v])[0].day_pnl_pct == 5.0

    def test_sorting_by_aggregate_puts_merged_symbol_in_right_place(self):
        vals = [
            FakeValuation("SPLIT", day_pnl_eur=30.0, current_value_eur=130.0),
            FakeValuation("BIG", day_pnl_eur=50.0, current_value_eur=150.0),
            FakeValuation("SPLIT", day_pnl_eur=40.0, current_value_eur=140.0),
        ]
        ordered = sorted(aggregate_day_pnl(vals), key=lambda s: s.day_pnl_eur)
        # SPLIT totals 70 and must outrank BIG, not sit at its first row's 30
        assert [s.symbol for s in ordered] == ["BIG", "SPLIT"]

    def test_skips_positions_without_day_pnl(self):
        vals = [
            FakeValuation("NOPRICE"),
            FakeValuation("AAPL", day_pnl_eur=1.0, current_value_eur=11.0),
        ]
        assert [s.symbol for s in aggregate_day_pnl(vals)] == ["AAPL"]

    def test_zero_previous_value_yields_none_percentage(self):
        vals = [FakeValuation("X", day_pnl_eur=5.0, current_value_eur=5.0)]
        assert aggregate_day_pnl(vals)[0].day_pnl_pct is None

    def test_empty_input(self):
        assert aggregate_day_pnl([]) == []


class TestAggregatePnL:
    def test_same_symbol_summed(self):
        vals = [
            FakeValuation("GC=F", pnl_eur=100.0, cost_basis_eur=1000.0, current_value_eur=1100.0),
            FakeValuation("GC=F", pnl_eur=50.0, cost_basis_eur=1000.0, current_value_eur=1050.0),
        ]
        result = aggregate_pnl(vals)
        assert len(result) == 1
        assert result[0].pnl_eur == 150.0
        assert result[0].value_eur == 2150.0

    def test_percentage_uses_summed_cost_basis(self):
        vals = [
            FakeValuation("GC=F", pnl_eur=100.0, cost_basis_eur=1000.0, current_value_eur=1100.0),
            FakeValuation("GC=F", pnl_eur=50.0, cost_basis_eur=1000.0, current_value_eur=1050.0),
        ]
        assert aggregate_pnl(vals)[0].pnl_pct == 7.5

    def test_missing_cost_basis_yields_none_percentage(self):
        vals = [FakeValuation("X", pnl_eur=10.0, current_value_eur=10.0)]
        assert aggregate_pnl(vals)[0].pnl_pct is None

    def test_skips_positions_without_pnl(self):
        vals = [FakeValuation("WATCH"), FakeValuation("A", pnl_eur=1.0, cost_basis_eur=10.0)]
        assert [s.symbol for s in aggregate_pnl(vals)] == ["A"]


class TestAggregateContributions:
    def test_duplicate_symbols_merged(self):
        rows = [
            FakeAttributionRow("SAP.DE", 100.0),
            FakeAttributionRow("AAPL", 500.0),
            FakeAttributionRow("SAP.DE", 200.0),
        ]
        result = {c.symbol: c.contribution_eur for c in aggregate_contributions(rows)}
        assert result == {"SAP.DE": 300.0, "AAPL": 500.0}

    def test_preserves_first_appearance_order(self):
        rows = [
            FakeAttributionRow("B", 1.0),
            FakeAttributionRow("A", 2.0),
            FakeAttributionRow("B", 3.0),
        ]
        assert [c.symbol for c in aggregate_contributions(rows)] == ["B", "A"]

    def test_percentage_uses_summed_start_value(self):
        # 300 gain on 2000 invested at period start -> 15 %
        rows = [
            FakeAttributionRow("SAP.DE", 100.0, start_value_eur=500.0),
            FakeAttributionRow("SAP.DE", 200.0, start_value_eur=1500.0),
        ]
        assert aggregate_contributions(rows)[0].delta_pct == pytest.approx(15.0)

    def test_percentage_none_without_start_value(self):
        rows = [FakeAttributionRow("X", 100.0)]
        assert aggregate_contributions(rows)[0].delta_pct is None

    def test_empty_input(self):
        assert aggregate_contributions([]) == []


class TestStartQtyResolver:
    """Snapshot holdings are keyed by ticker; the resolver splits a ticker held in
    several depots back across its positions."""

    def test_splits_ticker_total_proportionally(self):
        a = FakeValuation("SAP.DE", quantity=20.0)
        b = FakeValuation("SAP.DE", quantity=5.0)
        resolve = make_start_qty_resolver([a, b], {"SAP.DE": 25.0})
        assert resolve(a) == 20.0
        assert resolve(b) == 5.0

    def test_split_keeps_symbol_total_exact_after_quantity_change(self):
        # today 40 shares, snapshot says 20 were held entering the period
        a = FakeValuation("X", quantity=30.0)
        b = FakeValuation("X", quantity=10.0)
        resolve = make_start_qty_resolver([a, b], {"X": 20.0})
        assert resolve(a) + resolve(b) == 20.0

    def test_single_position_gets_full_snapshot_quantity(self):
        v = FakeValuation("AAPL", quantity=10.0)
        assert make_start_qty_resolver([v], {"AAPL": 5.0})(v) == 5.0

    def test_falls_back_to_today_quantity_without_snapshot_entry(self):
        v = FakeValuation("NEW", quantity=7.0)
        assert make_start_qty_resolver([v], {"AAPL": 5.0})(v) == 7.0
        assert make_start_qty_resolver([v], None)(v) == 7.0

    def test_position_without_quantity_gets_snapshot_value(self):
        v = FakeValuation("X", quantity=None)
        assert make_start_qty_resolver([v], {"X": 5.0})(v) == 5.0
