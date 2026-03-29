"""
Pydantic models for portfolio and watchlist entries.

Position is the new unified model (replaces PortfolioEntry + WatchlistEntry).
The legacy models are kept until the migration to the positions table is complete.
"""

from datetime import date, datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, field_validator, model_validator


class AssetType(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    CRYPTO = "crypto"
    BOND = "bond"
    OTHER = "other"


class WatchlistSource(str, Enum):
    USER = "user"
    AGENT = "agent"


class PortfolioEntry(BaseModel):
    id: Optional[int] = None
    symbol: str
    name: str
    quantity: float
    purchase_price: Optional[float] = None
    purchase_date: date
    asset_type: AssetType
    notes: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("quantity")
    @classmethod
    def positive_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Must be greater than zero")
        return v

    @field_validator("purchase_price")
    @classmethod
    def non_negative_price(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("Must be zero or greater")
        return v if v != 0 else None  # treat 0 as "unknown"


class WatchlistEntry(BaseModel):
    id: Optional[int] = None
    symbol: str
    name: str
    notes: Optional[str] = None
    target_price: Optional[float] = None
    added_date: date
    source: WatchlistSource
    asset_type: AssetType

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("target_price")
    @classmethod
    def positive_target_price(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("Target price must be greater than zero")
        return v


class PriceRecord(BaseModel):
    """Current market price for a symbol — not encrypted (public data)."""

    id: Optional[int] = None
    symbol: str
    price_eur: float
    currency_original: str
    price_original: float
    exchange_rate: float
    fetched_at: datetime

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("price_eur", "price_original", "exchange_rate")
    @classmethod
    def positive_number(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Must be greater than zero")
        return v


class HistoricalPrice(BaseModel):
    """Daily closing price for a symbol — not encrypted (public data)."""

    id: Optional[int] = None
    symbol: str
    date: date
    close_eur: float
    volume: Optional[int] = None

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("close_eur")
    @classmethod
    def positive_close(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Must be greater than zero")
        return v


# ---------------------------------------------------------------------------
# New unified model — replaces PortfolioEntry + WatchlistEntry
# ---------------------------------------------------------------------------

class Position(BaseModel):
    """
    Unified model for both portfolio positions and watchlist entries.
    in_portfolio=False  → watchlist entry (quantity may be None)
    in_portfolio=True   → portfolio position (quantity required)

    Encrypted at rest: quantity, purchase_price, notes, extra_data.
    The repository handles encryption/decryption transparently.
    """

    id: Optional[int] = None

    # Classification — validated against AssetClassRegistry at service layer
    asset_class: str
    investment_type: str        # derived from asset_class via YAML, stored for fast reads

    # Identifiers
    name: str
    isin: Optional[str] = None
    wkn: Optional[str] = None
    ticker: Optional[str] = None   # None = pending resolution

    # Financials (encrypted at rest)
    quantity: Optional[float] = None
    unit: str
    purchase_price: Optional[float] = None
    purchase_date: Optional[date] = None

    # Metadata (encrypted at rest)
    notes: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None

    # Provenance
    recommendation_source: Optional[str] = None
    strategy: Optional[str] = None
    added_date: date

    # State
    in_portfolio: bool = False

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, v: Optional[str]) -> Optional[str]:
        return v.upper().strip() if v else None

    @field_validator("isin")
    @classmethod
    def isin_uppercase(cls, v: Optional[str]) -> Optional[str]:
        return v.upper().strip() if v else None

    @field_validator("wkn")
    @classmethod
    def wkn_uppercase(cls, v: Optional[str]) -> Optional[str]:
        return v.upper().strip() if v else None

    @field_validator("quantity")
    @classmethod
    def positive_quantity(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("Quantity must be greater than zero")
        return v

    @field_validator("purchase_price")
    @classmethod
    def non_negative_price(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("Purchase price must be zero or greater")
        return v if v != 0 else None  # treat 0 as "unknown"

    @model_validator(mode="after")
    def portfolio_requires_quantity(self) -> "Position":
        if self.in_portfolio and self.quantity is None:
            raise ValueError("Portfolio positions must have a quantity")
        return self


# ---------------------------------------------------------------------------
# Research models
# ---------------------------------------------------------------------------

class ResearchSession(BaseModel):
    """A research conversation about a specific ticker with a chosen strategy."""

    id: Optional[int] = None
    ticker: str
    company_name: Optional[str] = None
    strategy_name: str
    strategy_prompt: str      # stored so custom strategies survive YAML changes
    created_at: datetime
    summary: Optional[str] = None

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, v: str) -> str:
        return v.upper().strip()


class ResearchMessage(BaseModel):
    """A single message in a research session."""

    id: Optional[int] = None
    session_id: int
    role: str       # 'user', 'assistant', 'tool'
    content: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Skills model
# ---------------------------------------------------------------------------

class Skill(BaseModel):
    """A reusable prompt skill for a specific area (research, analysis, etc.)."""

    id: Optional[int] = None
    name: str
    area: str
    description: Optional[str] = None
    prompt: str
    created_at: Optional[str] = None
