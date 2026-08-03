"""Shared chart presentation helpers.

The analysis page draws four bar charts of the same kind (daily P&L, total P&L,
monthly and yearly attribution). They used to carry three different label formats
— amount only, percentage only, and percentage-first-with-amount-in-parentheses —
which made the same information read differently per chart.
"""

import math
from typing import Optional

from core.currency import fmt_amount, fmt_pct


def _missing(value: Optional[float]) -> bool:
    """None or NaN — a DataFrame column turns missing values into NaN, so a plain
    ``is None`` check would let ``nan`` through into the label."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def style_bar_chart(fig, pad: float = 0.18) -> None:
    """Apply the shared look of the analysis bar charts, in place.

    Two-line labels need more room than the one-liners they replaced. The charts are
    sorted by value, so the outermost bars are the extremes — their labels sit right
    at the edge of the plotting area and were getting cut off:

    * vertically, because Plotly's autorange leaves only enough headroom for a single
      line above the tallest bar → the y-range is padded on both ends
    * horizontally, because outside labels are clipped at the axis boundary by
      default → ``cliponaxis=False`` lets the first and last label reach into the margin
    """
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(coloraxis_showscale=False, margin=dict(t=40, b=40))

    # trace.y is a numpy array — `or []` would evaluate its truth value and raise
    values = [
        v
        for trace in fig.data
        for v in (trace.y if getattr(trace, "y", None) is not None else [])
        if v is not None and not math.isnan(v)
    ]
    if values:
        low, high = min(min(values), 0.0), max(max(values), 0.0)
        span = (high - low) or abs(high) or 1.0
        fig.update_yaxes(range=[low - span * pad, high + span * pad])


def bar_label(amount_eur: Optional[float], pct: Optional[float]) -> str:
    """Two-line bar label: amount on the first line, percentage on the second.

    The amount is the primary signal and stays on top in the same format across all
    charts; the percentage is secondary context. Returns an empty label when there is
    no amount, and drops the second line when no percentage is known.
    """
    if _missing(amount_eur):
        return ""
    label = fmt_amount(amount_eur, decimals=0, signed=True)
    if not _missing(pct):
        label += f"<br>{fmt_pct(pct)}"
    return label
