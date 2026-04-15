"""
Unit tests for portfolio stability calculations — Josef's Regel.
"""

from datetime import date
from unittest.mock import MagicMock, AsyncMock

import pytest

from core.portfolio_stability import JOSEF_CATEGORY, _JOSEF_CATEGORY, compute_josef_allocation
from core.storage.models import Position


# ------------------------------------------------------------------
# Josef's Regel Category Mapping Tests
# ------------------------------------------------------------------

class TestJosefCategorization:
    """Unit tests for Josef's Regel category mapping."""

    def test_josef_category_mapping_is_correct(self):
        """Verify that JOSEF_CATEGORY maps investment types to correct categories."""
        assert JOSEF_CATEGORY["Wertpapiere"] == "Aktien"
        assert JOSEF_CATEGORY["Edelmetalle"] == "Rohstoffe"
        assert JOSEF_CATEGORY["Renten"] == "Renten/Geld"
        assert JOSEF_CATEGORY["Geld"] == "Renten/Geld"
        assert JOSEF_CATEGORY["Immobilien"] == "Rohstoffe", \
            "Immobilien must map to Rohstoffe (not separate category)"

    def test_josef_only_has_3_categories_not_4(self):
        """Verify that Immobilien is combined with Rohstoffe, not a separate category."""
        # Extract unique category values
        categories = set(JOSEF_CATEGORY.values())
        assert len(categories) == 3, \
            f"Expected 3 categories (Aktien, Renten/Geld, Rohstoffe), got {len(categories)}: {categories}"
        assert categories == {"Aktien", "Renten/Geld", "Rohstoffe"}

    def test_legacy_josef_category_alias(self):
        """Test that _JOSEF_CATEGORY is an alias for backward compatibility."""
        assert _JOSEF_CATEGORY == JOSEF_CATEGORY
        assert _JOSEF_CATEGORY["Wertpapiere"] == "Aktien"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def make_position(ticker: str, quantity: float, purchase_price: float,
                  investment_type: str = "Wertpapiere", asset_class: str = "Aktie") -> Position:
    """Helper to create a Position for testing."""
    return Position(
        id=1,
        ticker=ticker,
        name=f"{ticker} Corp",
        asset_class=asset_class,
        investment_type=investment_type,
        quantity=quantity,
        unit="Stück" if investment_type != "Edelmetalle" else "g",
        purchase_price=purchase_price,
        purchase_date=date(2022, 1, 1),
        added_date=date.today(),
        in_portfolio=True,
    )


class MockValuation:
    """Mock object for PortfolioValuation-like objects."""
    def __init__(self, investment_type: str, current_value_eur: float):
        self.investment_type = investment_type
        self.current_value_eur = current_value_eur


# ------------------------------------------------------------------
# Allocation Computation Tests
# ------------------------------------------------------------------

class TestJosefAllocationComputation:
    """Tests for compute_josef_allocation function."""

    def test_simple_three_pillar_portfolio(self):
        """Test basic allocation with one asset per pillar."""
        valuations = [
            MockValuation("Wertpapiere", 1000.0),  # Aktien
            MockValuation("Renten", 1000.0),       # Renten/Geld
            MockValuation("Edelmetalle", 1000.0),  # Rohstoffe
        ]
        result = compute_josef_allocation(valuations)

        assert abs(result["Aktien"] - 33.33) < 1.0
        assert abs(result["Renten/Geld"] - 33.33) < 1.0
        assert abs(result["Rohstoffe"] - 33.33) < 1.0
        assert abs(sum(result.values()) - 100.0) < 0.1

    def test_rohstoffe_combines_edelmetalle_and_immobilien(self):
        """Test that Edelmetalle and Immobilien both map to Rohstoffe."""
        valuations = [
            MockValuation("Wertpapiere", 3000.0),  # Aktien: 37.5%
            MockValuation("Geld", 2000.0),         # Renten/Geld: 25%
            MockValuation("Edelmetalle", 1500.0),  # Rohstoffe (combined): 37.5%
            MockValuation("Immobilien", 1500.0),   # Also Rohstoffe
        ]
        result = compute_josef_allocation(valuations)

        assert abs(result["Aktien"] - 37.5) < 1.0
        assert abs(result["Renten/Geld"] - 25.0) < 1.0
        assert abs(result["Rohstoffe"] - 37.5) < 1.0  # Combined Edelmetalle + Immobilien

    def test_empty_portfolio(self):
        """Test with no valuations."""
        valuations = []
        result = compute_josef_allocation(valuations)

        assert result["Aktien"] == 0.0
        assert result["Renten/Geld"] == 0.0
        assert result["Rohstoffe"] == 0.0

    def test_zero_value_portfolio(self):
        """Test with all zero or negative valuations."""
        valuations = [
            MockValuation("Wertpapiere", 0.0),
            MockValuation("Renten", -100.0),
            MockValuation("Edelmetalle", None),
        ]
        result = compute_josef_allocation(valuations)

        assert result["Aktien"] == 0.0
        assert result["Renten/Geld"] == 0.0
        assert result["Rohstoffe"] == 0.0

    def test_skewed_portfolio_deviation(self):
        """Test with one pillar heavily overweighted."""
        valuations = [
            MockValuation("Wertpapiere", 7000.0),   # Aktien: 70%
            MockValuation("Renten", 1500.0),        # Renten/Geld: 15%
            MockValuation("Edelmetalle", 1500.0),   # Rohstoffe: 15%
        ]
        result = compute_josef_allocation(valuations)

        assert abs(result["Aktien"] - 70.0) < 1.0
        assert abs(result["Renten/Geld"] - 15.0) < 1.0
        assert abs(result["Rohstoffe"] - 15.0) < 1.0
        assert abs(sum(result.values()) - 100.0) < 0.1

    def test_none_values_are_skipped(self):
        """Test that None current_value_eur is handled gracefully."""
        valuations = [
            MockValuation("Wertpapiere", 1000.0),
            MockValuation("Renten", None),          # Should be skipped
            MockValuation("Edelmetalle", 1000.0),
        ]
        result = compute_josef_allocation(valuations)

        assert abs(result["Aktien"] - 50.0) < 1.0
        assert abs(result["Renten/Geld"] - 0.0) < 0.1
        assert abs(result["Rohstoffe"] - 50.0) < 1.0
