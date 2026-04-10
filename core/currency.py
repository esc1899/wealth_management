"""
Currency configuration and formatting helpers.

Supports EUR, CHF, GBP, USD, JPY. Configured via BASE_CURRENCY env var.
"""

from config import config

# Currency symbols
SYMBOLS = {
    "EUR": "€",
    "CHF": "Fr.",
    "GBP": "£",
    "USD": "$",
    "JPY": "¥",
}

# Currency units that represent monetary values (used in pos.unit for cash)
CASH_UNITS = {"€", "CHF", "Fr.", "$", "£", "GBP", "USD", "JPY", "¥"}


def symbol() -> str:
    """Get the currency symbol for BASE_CURRENCY."""
    return SYMBOLS.get(config.BASE_CURRENCY, config.BASE_CURRENCY)


def fmt(value: float, decimals: int = 2) -> str:
    """Format a value with currency symbol and thousands separator.

    Args:
        value: The numeric value to format
        decimals: Number of decimal places (default 2)

    Returns:
        Formatted string, e.g. "€ 1.234,56" (German locale format)
    """
    sym = symbol()
    return f"{sym} {value:,.{decimals}f}"


def is_cash_unit(unit: str) -> bool:
    """Check if a unit represents a monetary value (currency).

    True for monetary units like €, CHF, $, etc.
    False for quantity units like "Stück", "Troy Oz", etc.

    Args:
        unit: The unit string to check

    Returns:
        True if the unit is a currency, False otherwise
    """
    return unit in CASH_UNITS
