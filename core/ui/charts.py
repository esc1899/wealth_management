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
