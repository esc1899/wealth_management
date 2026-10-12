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
    value_decomposition_by_ticker,
    flows_by_period,
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

    def test_sold_ticker_reduces_shares(self):
        # Ein Verkauf ist negativer Anteilszuwachs -- sonst zaehlte jeder Wiederkauf voll,
        # jeder Verkauf aber gar nicht, und die Summe passte nicht mehr zur Wertaenderung.
        snaps = [
            _snap("2026-01-01", holdings=[_hp("A", 1.0, 10.0), _hp("B", 1.0, 10.0)]),
            _snap("2026-02-01", holdings=[_hp("A", 1.0, 12.0)]),
        ]
        last = value_decomposition_series(snaps)[-1]
        assert last["cum_price_effect"] == pytest.approx(2.0)  # only A: 1*(12-10)
        assert last["cum_quantity_effect"] == pytest.approx(-10.0)  # B sold at 10

    def test_partial_outflow_reduces_shares(self):
        # Teilverkauf eines Tagesgeld-Fonds: Abfluss ist negativer Anteilszuwachs.
        snaps = [
            _snap("2026-01-01", holdings=[_hp("XEON", 100.0, 140.0)]),
            _snap("2026-02-01", holdings=[_hp("XEON", 40.0, 140.5)]),
        ]
        last = value_decomposition_series(snaps)[-1]
        assert last["cum_quantity_effect"] == pytest.approx(-60.0 * 140.5)
        assert last["cum_price_effect"] == pytest.approx(100.0 * 0.5)

    def test_umschichtung_from_money_market_fund_nets_out(self):
        # Tagesgeld-Fonds ganz verkauft, dafuer eine Aktie gekauft: kein Geld kam hinzu, also
        # (fast) kein Anteilszuwachs -- nur die Kursbewegung bleibt.
        snaps = [
            _snap("2026-01-01", holdings=[_hp("XEON", 100.0, 140.0)]),
            _snap("2026-02-01", holdings=[_hp("AAPL", 70.0, 200.0)]),
        ]
        last = value_decomposition_series(snaps)[-1]
        assert last["cum_quantity_effect"] == pytest.approx(70.0 * 200.0 - 100.0 * 140.0)  # 0
        assert last["cum_price_effect"] == pytest.approx(0.0)

    def test_data_gap_is_not_a_new_position(self):
        # Ein Snapshot ohne Preis fuer A darf A danach nicht noch einmal voll als Zukauf zaehlen.
        snaps = [
            _snap("2026-01-01", holdings=[_hp("A", 10.0, 100.0)]),
            _snap("2026-02-01", holdings=[_hp("A", 10.0, None)]),
            _snap("2026-03-01", holdings=[_hp("A", 10.0, 110.0)]),
        ]
        last = value_decomposition_series(snaps)[-1]
        assert last["cum_quantity_effect"] == pytest.approx(0.0)
        assert last["cum_price_effect"] == pytest.approx(100.0)

    def test_duplicate_ticker_lots_are_summed(self):
        # Zwei Tranchen desselben Titels: nicht die eine durch die andere ersetzen.
        snaps = [
            _snap("2026-01-01", holdings=[_hp("A", 10.0, 100.0), _hp("A", 1.0, 100.0)]),
            _snap("2026-02-01", holdings=[_hp("A", 1.0, 100.0), _hp("A", 10.0, 100.0)]),
        ]
        last = value_decomposition_series(snaps)[-1]
        assert last["cum_quantity_effect"] == pytest.approx(0.0)
        assert last["cum_price_effect"] == pytest.approx(0.0)

    def test_gram_positions_use_stored_value(self):
        # Gold in Gramm, Preis je Feinunze: q*p waere 31-mal zu viel. Der gespeicherte Wert stimmt.
        gold = lambda q, p, v: {"ticker": "GC=F", "quantity": q, "price_eur": p, "value_eur": v, "unit": "g"}
        snaps = [
            _snap("2026-01-01", holdings=[_hp("A", 1.0, 10.0)]),
            _snap("2026-02-01", holdings=[_hp("A", 1.0, 10.0), gold(31.1035, 2500.0, 2500.0)]),
        ]
        last = value_decomposition_series(snaps)[-1]
        assert last["cum_quantity_effect"] == pytest.approx(2500.0)

    def test_only_market_priced_classes(self):
        # Bargeld und Festgeld haben keine "Anteile": eine Einzahlung ist kein Anteilszuwachs.
        cash = lambda v: {"ticker": "Tagesgeld", "quantity": v, "price_eur": 1.0, "value_eur": v,
                          "asset_class": "Bargeld"}
        aktie = lambda q, p: {**_hp("A", q, p), "asset_class": "Aktie"}
        snaps = [
            _snap("2026-01-01", holdings=[aktie(1.0, 10.0), cash(5000.0)]),
            _snap("2026-02-01", holdings=[aktie(1.0, 11.0), cash(9000.0)]),
        ]
        last = value_decomposition_series(snaps, classes={"Aktie"})[-1]
        assert last["cum_quantity_effect"] == pytest.approx(0.0)
        assert last["cum_price_effect"] == pytest.approx(1.0)

    def test_fewer_than_two_holdings_snapshots(self):
        assert value_decomposition_series([_snap("2026-01-01", holdings=[_hp("A", 1.0, 10.0)])]) == []
        assert value_decomposition_series([]) == []


class TestValueDecompositionByTicker:
    def _gemischt(self):
        # Kursbewegung, Zukauf, neue Position, Verkauf und eine Datenluecke in einer Reihe.
        return [
            _snap("2026-01-01", holdings=[_hp("A", 10.0, 100.0), _hp("B", 5.0, 20.0)]),
            _snap("2026-02-01", holdings=[_hp("A", 12.0, 110.0), _hp("B", 5.0, None)]),
            _snap("2026-03-01", holdings=[_hp("A", 12.0, 105.0), _hp("B", 5.0, 22.0),
                                          _hp("C", 3.0, 50.0)]),
            _snap("2026-04-01", holdings=[_hp("A", 12.0, 108.0), _hp("C", 3.0, 55.0)]),
        ]

    def test_sums_equal_series(self):
        # Die Tabelle erklaert die Kurve: ihre Summen sind der letzte Punkt der Reihe.
        snaps = self._gemischt()
        zeilen = value_decomposition_by_ticker(snaps)
        last = value_decomposition_series(snaps)[-1]
        assert sum(z["quantity_effect"] for z in zeilen) == pytest.approx(last["cum_quantity_effect"])
        assert sum(z["price_effect"] for z in zeilen) == pytest.approx(last["cum_price_effect"])

    def test_per_ticker_values_and_order(self):
        zeilen = {z["ticker"]: z for z in value_decomposition_by_ticker(self._gemischt())}
        assert zeilen["A"]["quantity_effect"] == pytest.approx(2.0 * 110.0)
        assert zeilen["A"]["price_effect"] == pytest.approx(10 * 10.0 + 12 * -5.0 + 12 * 3.0)
        assert zeilen["B"]["quantity_effect"] == pytest.approx(-110.0)   # verkauft zu 5 * 22
        assert zeilen["B"]["price_effect"] == pytest.approx(10.0)        # Luecke ueberbrueckt
        assert zeilen["C"]["quantity_effect"] == pytest.approx(150.0)
        reihenfolge = [z["ticker"] for z in value_decomposition_by_ticker(self._gemischt())]
        assert reihenfolge == ["A", "C", "B"]   # nach Betrag: 220, 150, 110

    def test_largest_step_marks_new_and_sold(self):
        zeilen = {z["ticker"]: z for z in value_decomposition_by_ticker(self._gemischt())}
        assert zeilen["C"]["groesster_schritt"] == {
            "date": "2026-03-01", "q0": 0.0, "q1": 3.0, "quantity_effect": pytest.approx(150.0)}
        assert zeilen["B"]["groesster_schritt"]["q1"] == 0.0
        assert zeilen["B"]["groesster_schritt"]["date"] == "2026-04-01"

    def test_price_only_has_no_step(self):
        snaps = [
            _snap("2026-01-01", holdings=[_hp("A", 1.0, 10.0)]),
            _snap("2026-02-01", holdings=[_hp("A", 1.0, 12.0)]),
        ]
        (zeile,) = value_decomposition_by_ticker(snaps)
        assert zeile["groesster_schritt"] is None
        assert zeile["price_effect"] == pytest.approx(2.0)

    def test_name_class_and_filter(self):
        aktie = {**_hp("A", 1.0, 10.0), "asset_class": "Aktie", "name": "Alpha AG"}
        cash = {"ticker": "Tagesgeld", "quantity": 100.0, "price_eur": 1.0, "asset_class": "Bargeld"}
        snaps = [
            _snap("2026-01-01", holdings=[aktie, cash]),
            _snap("2026-02-01", holdings=[{**aktie, "quantity": 2.0}, {**cash, "quantity": 500.0}]),
        ]
        zeilen = value_decomposition_by_ticker(snaps, classes={"Aktie"})
        assert [(z["ticker"], z["name"], z["asset_class"]) for z in zeilen] == [("A", "Alpha AG", "Aktie")]

    def test_fewer_than_two_holdings_snapshots(self):
        assert value_decomposition_by_ticker([_snap("2026-01-01", holdings=[_hp("A", 1.0, 10.0)])]) == []


class TestFlowsByPeriod:
    def _reihe(self):
        return [
            _snap("2026-01-05", holdings=[_hp("A", 10.0, 100.0), _hp("B", 5.0, 20.0)]),
            _snap("2026-01-20", holdings=[_hp("A", 12.0, 100.0), _hp("B", 5.0, 20.0)]),  # +200
            _snap("2026-02-10", holdings=[_hp("A", 12.0, 110.0)]),                       # B weg -100
            _snap("2026-04-01", holdings=[_hp("A", 11.0, 110.0), _hp("C", 1.0, 50.0)]),  # -110 +50
        ]

    def test_month_buckets(self):
        out = flows_by_period(self._reihe())
        assert [z["period"] for z in out] == ["2026-01", "2026-02", "2026-04"]   # Maerz ungesehen
        assert out[0] == {"period": "2026-01", "zukaeufe": 200.0, "verkaeufe": 0.0, "saldo": 200.0}
        assert out[1]["verkaeufe"] == pytest.approx(-100.0)
        assert out[2]["zukaeufe"] == pytest.approx(50.0)
        assert out[2]["verkaeufe"] == pytest.approx(-110.0)

    def test_year_and_sum_equal_series(self):
        snaps = self._reihe()
        (jahr,) = flows_by_period(snaps, period="year")
        assert jahr["period"] == "2026"
        assert jahr["saldo"] == pytest.approx(value_decomposition_series(snaps)[-1]["cum_quantity_effect"])
        assert jahr["zukaeufe"] + jahr["verkaeufe"] == pytest.approx(jahr["saldo"])

    def test_price_only_month_shows_zero(self):
        snaps = [
            _snap("2026-01-01", holdings=[_hp("A", 1.0, 10.0)]),
            _snap("2026-02-01", holdings=[_hp("A", 1.0, 12.0)]),
        ]
        assert flows_by_period(snaps) == [
            {"period": "2026-02", "zukaeufe": 0.0, "verkaeufe": 0.0, "saldo": 0.0}]

    def test_fewer_than_two_holdings_snapshots(self):
        assert flows_by_period([]) == []
