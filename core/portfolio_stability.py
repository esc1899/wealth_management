"""
Portfolio stability rules and calculations — Josef's Regel and asset class categorization.

Josef's Regel: Target allocation of 1/3 each for Aktien, Renten/Geld, and Rohstoffe+Immobilien.
This module provides both the calculation logic and constants for portfolio stability analysis.
"""

# Asset classes that are not tradeable via exchanges — excluded from active rebalancing
# recommendations but still counted in total wealth.
NON_TRADEABLE_CLASSES = {"Festgeld", "Bargeld", "Immobilie", "Grundstück"}

# Josef's Regel: target 1/3 per category (Rohstoffe + Immobilien together = 1/3).
# Maps investment_type → Josef category
# Note: "Immobilien" investment_type maps to "Rohstoffe" category so they combine
JOSEF_CATEGORY = {
    "Wertpapiere": "Aktien",
    "Edelmetalle": "Rohstoffe",
    "Renten": "Renten/Geld",
    "Geld": "Renten/Geld",
    "Bargeld": "Renten/Geld",
    "Immobilien": "Rohstoffe",  # Combined with Edelmetalle, not separate
}

# Legacy name for backwards compatibility
_JOSEF_CATEGORY = JOSEF_CATEGORY


def compute_josef_allocation(valuations: list) -> dict[str, float]:
    """
    Compute Josef-Regel allocation percentages from portfolio valuations.

    Args:
        valuations: List of PortfolioValuation objects with investment_type and current_value_eur

    Returns:
        Dict with keys "Aktien", "Renten/Geld", "Rohstoffe" and percentage values
    """
    totals = {"Aktien": 0.0, "Renten/Geld": 0.0, "Rohstoffe": 0.0}
    grand_total = 0.0

    for v in valuations:
        value = v.current_value_eur or 0.0
        if value <= 0:
            continue
        category = JOSEF_CATEGORY.get(v.investment_type)
        if category:
            totals[category] += value
            grand_total += value

    if grand_total == 0:
        return {"Aktien": 0.0, "Renten/Geld": 0.0, "Rohstoffe": 0.0}

    return {k: (v / grand_total * 100) for k, v in totals.items()}
