"""
Tests for core/portfolio_snapshot.py — the text handed to the local LLM
for the Portfolio Checker and Portfolio Robustness analyses.

Fixtures are synthetic. Never paste real position names or values in here.
"""

from types import SimpleNamespace

from core.portfolio_snapshot import build_portfolio_snapshot


def _pos(pid, name, ticker, asset_class="Aktie"):
    return SimpleNamespace(id=pid, name=name, ticker=ticker, asset_class=asset_class)


def _val(position_id, symbol, value, dividend=None):
    return SimpleNamespace(
        position_id=position_id,
        symbol=symbol,
        current_value_eur=value,
        annual_dividend_eur=dividend,
    )


class TestBuildPortfolioSnapshot:

    def test_tickerless_position_keeps_its_value(self):
        """Regression: a position without a ticker was rendered as 0€."""
        positions = [_pos(1, "Beispielimmobilie", None, "Immobilie")]
        # MarketDataAgent derives a pseudo-symbol from the name for tickerless positions
        valuations = [_val(1, "Beispielim", 1_000.0)]

        result = build_portfolio_snapshot(positions, valuations)

        assert "1,000€" in result
        assert "Wert unbekannt" not in result

    def test_pseudo_symbol_collision_does_not_merge_positions(self):
        """Names sharing a 10-char prefix collapse to one pseudo-symbol."""
        positions = [
            _pos(1, "Musterbank - Konto", None, "Bargeld"),
            _pos(2, "Musterbank - Festgeld", None, "Festgeld"),
            _pos(3, "Musterbank - Tagesgeld", None, "Bargeld"),
        ]
        valuations = [
            _val(1, "Musterbank", 100.0),
            _val(2, "Musterbank", 200.0),
            _val(3, "Musterbank", 300.0),
        ]

        result = build_portfolio_snapshot(positions, valuations)

        assert "100€" in result
        assert "200€" in result
        assert "300€" in result
        assert "Gesamtwert: 600€" in result

    def test_same_ticker_in_two_depots_valued_separately(self):
        positions = [
            _pos(1, "Depot A Rohstoff", "XX=F", "Edelmetall"),
            _pos(2, "Depot B Rohstoff", "XX=F", "Edelmetall"),
        ]
        valuations = [_val(1, "XX=F", 800.0), _val(2, "XX=F", 200.0)]

        result = build_portfolio_snapshot(positions, valuations)

        assert "800€" in result
        assert "200€" in result

    def test_weights_sum_over_all_positions(self):
        positions = [_pos(1, "A", "A.DE"), _pos(2, "B", None, "Immobilie")]
        valuations = [_val(1, "A.DE", 250.0), _val(2, "B", 750.0)]

        result = build_portfolio_snapshot(positions, valuations)

        assert "25.0%" in result
        assert "75.0%" in result
        assert "Gesamtwert: 1,000€ (2 Positionen)" in result

    def test_dividend_total_is_computed_not_left_to_the_model(self):
        positions = [_pos(1, "A", "A.DE"), _pos(2, "B", "B.DE"), _pos(3, "C", "C.DE")]
        valuations = [
            _val(1, "A.DE", 1_000.0, dividend=20.0),
            _val(2, "B.DE", 1_000.0, dividend=15.0),
            _val(3, "C.DE", 1_000.0, dividend=None),
        ]

        result = build_portfolio_snapshot(positions, valuations)

        assert "Dividende/Zins p.a.: 20€" in result
        assert "Erwartete Ausschüttungen gesamt: 35€ p.a." in result

    def test_dividends_can_be_omitted(self):
        positions = [_pos(1, "A", "A.DE")]
        valuations = [_val(1, "A.DE", 1_000.0, dividend=20.0)]

        result = build_portfolio_snapshot(positions, valuations, with_dividends=False)

        assert "Dividende" not in result
        assert "Ausschüttungen" not in result

    def test_position_without_valuation_is_marked_unknown(self):
        positions = [_pos(1, "A", "A.DE"), _pos(2, "Neu", None, "Immobilie")]
        valuations = [_val(1, "A.DE", 1_000.0)]

        result = build_portfolio_snapshot(positions, valuations)

        assert "Neu (kein Ticker, Immobilie): Wert unbekannt" in result
        assert "Gesamtwert: 1,000€" in result

    def test_empty_portfolio_does_not_divide_by_zero(self):
        assert "Gesamtwert: 0€ (0 Positionen)" in build_portfolio_snapshot([], [])
