"""Unit tests for core/composition_drift.py — pure, no DB/network."""

from types import SimpleNamespace

import pytest

from core.composition_drift import (
    concentration_series,
    asset_class_mix_series,
    dividend_history_series,
    sold_positions_summary,
    share_count_series,
    portfolio_income_series,
    value_decomposition_series,
)


def _snap(date_str, breakdown=None, holdings=None):
    return SimpleNamespace(date=date_str, breakdown=breakdown or {}, holdings=holdings)


def _h(ticker, value):
    return {"ticker": ticker, "value_eur": value}


class TestConcentrationSeries:
    def test_equal_weight_four_positions(self):
        snap = _snap("2026-01-02", holdings=[_h("A", 25), _h("B", 25), _h("C", 25), _h("D", 25)])
        out = concentration_series([snap])
        assert len(out) == 1
        row = out[0]
        assert row["top1_pct"] == pytest.approx(25.0)
        assert row["top3_pct"] == pytest.approx(75.0)
        assert row["top5_pct"] == pytest.approx(100.0)  # only 4 → all
        assert row["hhi"] == pytest.approx(0.25)
        assert row["effective_n"] == pytest.approx(4.0)
        assert row["n"] == 4

    def test_concentrated_portfolio(self):
        snap = _snap("2026-01-02", holdings=[_h("A", 90), _h("B", 10)])
        row = concentration_series([snap])[0]
        assert row["top1_pct"] == pytest.approx(90.0)
        assert row["hhi"] == pytest.approx(0.81 + 0.01)  # 0.9² + 0.1²
        assert row["effective_n"] == pytest.approx(1 / 0.82)

    def test_skips_snapshots_without_holdings(self):
        snaps = [_snap("2026-01-01", holdings=None), _snap("2026-01-02", holdings=[_h("A", 100)])]
        out = concentration_series(snaps)
        assert [r["date"] for r in out] == ["2026-01-02"]

    def test_ignores_nonpositive_values(self):
        snap = _snap("2026-01-02", holdings=[_h("A", 100), _h("B", 0), _h("C", None)])
        row = concentration_series([snap])[0]
        assert row["n"] == 1
        assert row["top1_pct"] == pytest.approx(100.0)

    def test_empty_input(self):
        assert concentration_series([]) == []


class TestAssetClassMixSeries:
    def test_percentages_sum_to_100(self):
        snaps = [
            _snap("2026-01-01", breakdown={"Aktie": 75.0, "Anleihe": 25.0}),
            _snap("2026-01-02", breakdown={"Aktie": 50.0, "Anleihe": 50.0}),
        ]
        dates, mix = asset_class_mix_series(snaps)
        assert dates == ["2026-01-01", "2026-01-02"]
        assert mix["Aktie"] == pytest.approx([75.0, 50.0])
        assert mix["Anleihe"] == pytest.approx([25.0, 50.0])
        for i in range(len(dates)):
            assert sum(series[i] for series in mix.values()) == pytest.approx(100.0)

    def test_absent_class_is_zero(self):
        snaps = [
            _snap("2026-01-01", breakdown={"Aktie": 100.0}),
            _snap("2026-01-02", breakdown={"Aktie": 50.0, "Gold": 50.0}),
        ]
        _, mix = asset_class_mix_series(snaps)
        assert mix["Gold"] == pytest.approx([0.0, 50.0])

    def test_zero_total_yields_zero(self):
        snaps = [_snap("2026-01-01", breakdown={"Aktie": 0.0})]
        _, mix = asset_class_mix_series(snaps)
        assert mix["Aktie"] == pytest.approx([0.0])


class TestDividendHistorySeries:
    def _div_h(self, ticker, name, div, yld=None):
        return {"ticker": ticker, "name": name, "annual_dividend_eur": div, "dividend_yield_pct": yld}

    def test_builds_per_ticker_series_in_order(self):
        snaps = [
            _snap("2026-01-01", holdings=[self._div_h("AAPL", "Apple", 100.0, 0.02)]),
            _snap("2026-02-01", holdings=[self._div_h("AAPL", "Apple", 110.0, 0.021)]),
        ]
        out = dividend_history_series(snaps)
        assert set(out.keys()) == {"AAPL"}
        assert out["AAPL"]["name"] == "Apple"
        pts = out["AAPL"]["points"]
        assert [p["date"] for p in pts] == ["2026-01-01", "2026-02-01"]
        assert [p["annual_dividend_eur"] for p in pts] == [100.0, 110.0]
        assert pts[0]["dividend_yield_pct"] == 0.02

    def test_skips_snapshots_without_holdings_and_none_dividends(self):
        snaps = [
            _snap("2026-01-01", holdings=None),
            _snap("2026-02-01", holdings=[
                self._div_h("AAPL", "Apple", 100.0),
                self._div_h("BRK", "Berkshire", None),  # no dividend → omitted
            ]),
        ]
        out = dividend_history_series(snaps)
        assert set(out.keys()) == {"AAPL"}

    def test_empty_input(self):
        assert dividend_history_series([]) == {}


class TestSoldPositionsSummary:
    def _ph(self, ticker, name, price, value):
        return {"ticker": ticker, "name": name, "price_eur": price, "value_eur": value}

    def test_detects_position_no_longer_held(self):
        snaps = [
            _snap("2026-01-01", holdings=[self._ph("AAPL", "Apple", 100.0, 1000.0),
                                          self._ph("OLD", "OldCo", 50.0, 500.0)]),
            _snap("2026-02-01", holdings=[self._ph("AAPL", "Apple", 110.0, 1100.0),
                                          self._ph("OLD", "OldCo", 60.0, 600.0)]),
            _snap("2026-03-01", holdings=[self._ph("AAPL", "Apple", 120.0, 1200.0)]),  # OLD sold
        ]
        out = sold_positions_summary(snaps)
        assert len(out) == 1
        row = out[0]
        assert row["ticker"] == "OLD"
        assert row["first_date"] == "2026-01-01"
        assert row["last_date"] == "2026-02-01"
        assert row["last_value_eur"] == pytest.approx(600.0)
        assert row["price_change_pct"] == pytest.approx(20.0)  # 50 → 60

    def test_currently_held_not_listed(self):
        snaps = [
            _snap("2026-01-01", holdings=[self._ph("AAPL", "Apple", 100.0, 1000.0)]),
            _snap("2026-02-01", holdings=[self._ph("AAPL", "Apple", 110.0, 1100.0)]),
        ]
        assert sold_positions_summary(snaps) == []

    def test_ignores_snapshots_without_holdings(self):
        snaps = [
            _snap("2026-01-01", holdings=None),
            _snap("2026-02-01", holdings=[self._ph("OLD", "OldCo", 50.0, 500.0)]),
            _snap("2026-03-01", holdings=[self._ph("AAPL", "Apple", 100.0, 1000.0)]),
        ]
        out = sold_positions_summary(snaps)
        assert [r["ticker"] for r in out] == ["OLD"]

    def test_fewer_than_two_holdings_snapshots(self):
        snaps = [_snap("2026-01-01", holdings=[self._ph("OLD", "OldCo", 50.0, 500.0)])]
        assert sold_positions_summary(snaps) == []


def _hq(ticker, quantity, name=None):
    return {"ticker": ticker, "quantity": quantity, "name": name or ticker}


class TestShareCountSeries:
    def test_ratchet_grows(self):
        snaps = [
            _snap("2026-01-01", holdings=[_hq("AAPL", 10.0, "Apple")]),
            _snap("2026-02-01", holdings=[_hq("AAPL", 10.5, "Apple")]),
            _snap("2026-03-01", holdings=[_hq("AAPL", 11.2, "Apple")]),
        ]
        out = share_count_series(snaps)
        assert out["AAPL"]["name"] == "Apple"
        assert [p["quantity"] for p in out["AAPL"]["points"]] == [10.0, 10.5, 11.2]
        assert [p["date"] for p in out["AAPL"]["points"]] == ["2026-01-01", "2026-02-01", "2026-03-01"]

    def test_skips_snapshots_without_holdings(self):
        snaps = [
            _snap("2026-01-01", holdings=None),
            _snap("2026-02-01", holdings=[_hq("AAPL", 5.0)]),
        ]
        out = share_count_series(snaps)
        assert [p["date"] for p in out["AAPL"]["points"]] == ["2026-02-01"]

    def test_ignores_none_quantity_and_omits_empty_ticker(self):
        snaps = [_snap("2026-01-01", holdings=[
            {"ticker": "AAPL", "quantity": None},
            {"ticker": "MSFT", "quantity": 3.0},
        ])]
        out = share_count_series(snaps)
        assert "AAPL" not in out
        assert out["MSFT"]["points"][0]["quantity"] == 3.0

    def test_empty_input(self):
        assert share_count_series([]) == {}


def _hd(ticker, value, div):
    return {"ticker": ticker, "value_eur": value, "annual_dividend_eur": div}


class TestPortfolioIncomeSeries:
    def test_sums_income_and_value(self):
        snaps = [_snap("2026-01-01", holdings=[_hd("A", 1000.0, 30.0), _hd("B", 1000.0, 10.0)])]
        row = portfolio_income_series(snaps)[0]
        assert row["total_annual_dividend_eur"] == pytest.approx(40.0)
        assert row["total_value_eur"] == pytest.approx(2000.0)
        assert row["yield_pct"] == pytest.approx(2.0)

    def test_zero_value_yields_zero(self):
        snaps = [_snap("2026-01-01", holdings=[_hd("A", 0.0, 0.0)])]
        assert portfolio_income_series(snaps)[0]["yield_pct"] == 0.0

    def test_missing_fields_treated_as_zero(self):
        snaps = [_snap("2026-01-01", holdings=[{"ticker": "A", "value_eur": 500.0}])]
        row = portfolio_income_series(snaps)[0]
        assert row["total_annual_dividend_eur"] == 0.0
        assert row["yield_pct"] == 0.0

    def test_skips_snapshots_without_holdings(self):
        snaps = [_snap("2026-01-01", holdings=None), _snap("2026-02-01", holdings=[_hd("A", 100.0, 5.0)])]
        out = portfolio_income_series(snaps)
        assert [r["date"] for r in out] == ["2026-02-01"]


def _hp(ticker, quantity, price):
    return {"ticker": ticker, "quantity": quantity, "price_eur": price}


class TestValueDecomposition:
    def test_invariant_sum_equals_value_change(self):
        # AAPL: qty 10→12 (accumulation), price 100→110 (market)
        snaps = [
            _snap("2026-01-01", holdings=[_hp("AAPL", 10.0, 100.0)]),
            _snap("2026-02-01", holdings=[_hp("AAPL", 12.0, 110.0)]),
        ]
        out = value_decomposition_series(snaps)
        last = out[-1]
        delta_value = 12.0 * 110.0 - 10.0 * 100.0  # 1320 - 1000 = 320
        assert last["cum_price_effect"] + last["cum_quantity_effect"] == pytest.approx(delta_value)
        # quantity_effect = (12-10)*110 = 220 ; price_effect = 10*(110-100) = 100
        assert last["cum_quantity_effect"] == pytest.approx(220.0)
        assert last["cum_price_effect"] == pytest.approx(100.0)

    def test_starts_at_zero(self):
        snaps = [
            _snap("2026-01-01", holdings=[_hp("A", 1.0, 10.0)]),
            _snap("2026-02-01", holdings=[_hp("A", 1.0, 11.0)]),
        ]
        out = value_decomposition_series(snaps)
        assert out[0] == {"date": "2026-01-01", "cum_price_effect": 0.0, "cum_quantity_effect": 0.0}

    def test_new_position_counts_as_accumulation(self):
        snaps = [
            _snap("2026-01-01", holdings=[_hp("A", 1.0, 10.0)]),
            _snap("2026-02-01", holdings=[_hp("A", 1.0, 10.0), _hp("B", 5.0, 20.0)]),
        ]
        last = value_decomposition_series(snaps)[-1]
        assert last["cum_quantity_effect"] == pytest.approx(100.0)  # B: 5*20 full value
        assert last["cum_price_effect"] == pytest.approx(0.0)

    def test_disappeared_ticker_dropped(self):
        snaps = [
            _snap("2026-01-01", holdings=[_hp("A", 1.0, 10.0), _hp("B", 1.0, 10.0)]),
            _snap("2026-02-01", holdings=[_hp("A", 1.0, 12.0)]),
        ]
        last = value_decomposition_series(snaps)[-1]
        assert last["cum_price_effect"] == pytest.approx(2.0)  # only A: 1*(12-10)
        assert last["cum_quantity_effect"] == pytest.approx(0.0)

    def test_fewer_than_two_holdings_snapshots(self):
        assert value_decomposition_series([_snap("2026-01-01", holdings=[_hp("A", 1.0, 10.0)])]) == []
        assert value_decomposition_series([]) == []
