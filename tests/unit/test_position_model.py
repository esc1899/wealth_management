"""
Unit tests for the Position Pydantic model.
"""

from datetime import date
import pytest
from pydantic import ValidationError

from core.storage.models import Position


def make_position(**kwargs) -> Position:
    defaults = dict(
        asset_class="Aktie",
        investment_type="Wertpapiere",
        name="Apple Inc.",
        ticker="AAPL",
        quantity=10.0,
        unit="Stück",
        purchase_price=150.0,
        purchase_date=date(2024, 1, 15),
        added_date=date(2024, 1, 15),
        in_portfolio=True,
    )
    defaults.update(kwargs)
    return Position(**defaults)


class TestPositionModel:
    def test_valid_portfolio_position(self):
        p = make_position()
        assert p.ticker == "AAPL"
        assert p.in_portfolio is True

    def test_ticker_uppercased(self):
        p = make_position(ticker="aapl")
        assert p.ticker == "AAPL"

    def test_isin_uppercased(self):
        p = make_position(isin="us0378331005")
        assert p.isin == "US0378331005"

    def test_wkn_uppercased(self):
        p = make_position(wkn="865985")
        assert p.wkn == "865985"

    def test_zero_quantity_rejected(self):
        with pytest.raises(ValidationError, match="greater than zero"):
            make_position(quantity=0)

    def test_negative_quantity_rejected(self):
        with pytest.raises(ValidationError, match="greater than zero"):
            make_position(quantity=-1)

    def test_zero_purchase_price_becomes_none(self):
        p = make_position(purchase_price=0)
        assert p.purchase_price is None

    def test_negative_purchase_price_rejected(self):
        with pytest.raises(ValidationError, match="zero or greater"):
            make_position(purchase_price=-10)

    def test_portfolio_position_without_quantity_rejected(self):
        with pytest.raises(ValidationError, match="quantity"):
            make_position(quantity=None, in_portfolio=True)

    def test_watchlist_position_without_quantity_valid(self):
        p = make_position(quantity=None, in_portfolio=False)
        assert p.quantity is None
        assert p.in_portfolio is False

    def test_optional_fields_default_to_none(self):
        p = make_position()
        assert p.isin is None
        assert p.wkn is None
        assert p.notes is None
        assert p.extra_data is None
        assert p.recommendation_source is None
        assert p.strategy is None

    def test_extra_data_accepts_dict(self):
        p = make_position(extra_data={"purity": "999.9", "storage": "Zürich"})
        assert p.extra_data["purity"] == "999.9"

    def test_purchase_date_optional(self):
        p = make_position(purchase_date=None)
        assert p.purchase_date is None

    def test_ticker_none_allowed(self):
        p = make_position(ticker=None, in_portfolio=False, quantity=None)
        assert p.ticker is None
