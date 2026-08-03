"""Bar-chart labels and German amount formatting.

All four bar charts on the analysis page share one label format: amount on the
first line, percentage on the second.
"""

from core.currency import fmt_amount, fmt_pct
from core.ui.charts import bar_label, style_bar_chart


class TestFmtAmount:
    def test_german_grouping_and_decimal_separator(self):
        assert fmt_amount(1234567.0) == "1.234.567 €"

    def test_decimals(self):
        assert fmt_amount(1234.56, decimals=2) == "1.234,56 €"

    def test_signed_positive_gets_plus(self):
        assert fmt_amount(1234.0, signed=True) == "+1.234 €"

    def test_signed_negative_keeps_minus(self):
        assert fmt_amount(-1234.0, signed=True) == "-1.234 €"

    def test_unsigned_positive_has_no_plus(self):
        assert fmt_amount(1234.0) == "1.234 €"


class TestFmtPct:
    def test_german_decimal_separator_and_sign(self):
        assert fmt_pct(2.153) == "+2,15 %"

    def test_negative(self):
        assert fmt_pct(-0.5) == "-0,50 %"

    def test_decimals_configurable(self):
        assert fmt_pct(12.345, decimals=1) == "+12,3 %"


class TestBarLabel:
    def test_amount_first_percentage_second(self):
        assert bar_label(1234.0, 2.15) == "+1.234 €<br>+2,15 %"

    def test_negative_values(self):
        assert bar_label(-980.0, -1.4) == "-980 €<br>-1,40 %"

    def test_without_percentage_only_the_amount_line(self):
        assert bar_label(1234.0, None) == "+1.234 €"

    def test_missing_amount_gives_empty_label(self):
        assert bar_label(None, 2.0) == ""

    def test_nan_is_treated_as_missing(self):
        """DataFrame columns turn None into NaN — that must not reach the label."""
        assert bar_label(float("nan"), 2.0) == ""
        assert bar_label(1234.0, float("nan")) == "+1.234 €"

    def test_zero_amount_still_labelled(self):
        assert bar_label(0.0, 0.0) == "+0 €<br>+0,00 %"

    def test_line_break_is_the_only_markup(self):
        label = bar_label(1234.0, 2.15)
        assert label.count("<br>") == 1
        assert "<" not in label.replace("<br>", "")


class TestLabelConsistencyAcrossCharts:
    def test_same_input_yields_identical_label_shape(self):
        """Day, P&L, month and year charts must not drift apart again."""
        labels = [bar_label(v, p) for v, p in [(100.0, 1.0), (2500.0, 12.5), (-30.0, -0.4)]]
        for label in labels:
            amount_line, pct_line = label.split("<br>")
            assert amount_line.endswith(" €")
            assert pct_line.endswith(" %")
            assert amount_line[0] in "+-"


class TestStyleBarChart:
    """The two-line labels of the outermost bars were getting cut off — the charts
    are sorted by value, so the first and last bar carry the extremes."""

    def _fig(self, values):
        import plotly.express as px
        return px.bar(x=[f"S{i}" for i in range(len(values))], y=values)

    def test_y_range_leaves_headroom_above_the_tallest_bar(self):
        fig = self._fig([10.0, 500.0, 120.0])
        style_bar_chart(fig)
        low, high = fig.layout.yaxis.range
        assert high > 500.0
        assert low < 0.0  # baseline stays visible

    def test_headroom_below_the_deepest_negative_bar(self):
        fig = self._fig([-400.0, -20.0, 50.0])
        style_bar_chart(fig)
        low, high = fig.layout.yaxis.range
        assert low < -400.0
        assert high > 50.0

    def test_labels_are_not_clipped_at_the_axis(self):
        fig = self._fig([10.0, 20.0])
        style_bar_chart(fig)
        assert all(trace.cliponaxis is False for trace in fig.data)
        assert all(trace.textposition == "outside" for trace in fig.data)

    def test_all_zero_values_still_give_a_usable_range(self):
        fig = self._fig([0.0, 0.0])
        style_bar_chart(fig)
        low, high = fig.layout.yaxis.range
        assert low < high

    def test_empty_chart_does_not_raise(self):
        import plotly.graph_objects as go
        fig = go.Figure(go.Bar(x=[], y=[]))  # px.bar rejects empty input
        style_bar_chart(fig)  # no data → no explicit range, autorange stays
        assert fig.layout.yaxis.range is None

    def test_colorbar_is_hidden(self):
        fig = self._fig([1.0, 2.0])
        style_bar_chart(fig)
        assert fig.layout.coloraxis.showscale is False
