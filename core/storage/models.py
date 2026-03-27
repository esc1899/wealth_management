"""
Pydantic models for portfolio and watchlist entries.
"""

from datetime import date
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator


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
    purchase_price: float
    purchase_date: date
    asset_type: AssetType
    notes: Optional[str] = None

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("quantity", "purchase_price")
    @classmethod
    def positive_number(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Must be greater than zero")
        return v


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
