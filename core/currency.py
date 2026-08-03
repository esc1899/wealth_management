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


def fmt_amount(value: float, decimals: int = 0, signed: bool = False) -> str:
    """Format an amount in German notation with the currency symbol as suffix.

    ``fmt()`` puts the symbol in front and leaves Python's ``1,234.56`` grouping in
    place; chart labels and captions need the German ``1.234,56 €`` form, which is
    why the swap was open-coded all over the pages.

    Args:
        value: The numeric value to format
        decimals: Number of decimal places (default 0)
        signed: Prefix a ``+`` for positive values (for gains/losses)
    """
    spec = f"{'+' if signed else ''},.{decimals}f"
    formatted = format(value, spec).replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} {symbol()}"


def fmt_pct(value: float, decimals: int = 2, signed: bool = True) -> str:
    """Format a percentage in German notation, e.g. ``+2,15 %``."""
    spec = f"{'+' if signed else ''}.{decimals}f"
    return f"{format(value, spec).replace('.', ',')} %"


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
