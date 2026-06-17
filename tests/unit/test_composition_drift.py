"""Unit tests for core/composition_drift.py — pure, no DB/network."""

from types import SimpleNamespace

import pytest

from core.composition_drift import concentration_series, asset_class_mix_series


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
