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


class DividendRecord(BaseModel):
    """Annual dividend rate and yield for a symbol — not encrypted (public data)."""

    symbol: str
    rate_eur: Optional[float] = None      # Forward annual dividend per share in EUR
    yield_pct: Optional[float] = None     # Forward yield as decimal (0.015 = 1.5%)
    currency: Optional[str] = None        # Native ticker currency
    fetched_at: datetime

    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("rate_eur", "yield_pct")
    @classmethod
    def non_negative(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("Must be zero or greater")
        return v


# ---------------------------------------------------------------------------
# New unified model — replaces PortfolioEntry + WatchlistEntry
# ---------------------------------------------------------------------------

class Position(BaseModel):
    """
    Unified model for both portfolio positions and watchlist entries.
    in_portfolio=True  → portfolio position (quantity required)
    in_watchlist=True  → watchlist entry (visible to cloud agents)
    Both flags can be True simultaneously.

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

    # Analysis (empfehlung plain text; story encrypted at rest)
    empfehlung: Optional[str] = None
    story: Optional[str] = None
    story_skill: Optional[str] = None  # Anlage-Idee label, plain text

    # State
    in_portfolio: bool = False
    in_watchlist: bool = False
    rebalance_excluded: bool = False  # True = shown in rebalance snapshot but no action recommended

    # Sub-type (optional, driven by asset_classes.yaml anlagearten list)
    anlageart: Optional[str] = None

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
        # Quantity is optional for manual-valuation asset classes (Immobilie, Grundstück)
        # that track value via extra_data.estimated_value or purchase_price instead.
        # Validation of required fields per asset type is handled at the service/UI layer.
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
# Search models
# ---------------------------------------------------------------------------

class SearchSession(BaseModel):
    """A search session for finding investment opportunities."""

    id: Optional[int] = None
    query: str
    skill_name: str
    skill_prompt: str
    created_at: datetime


class SearchMessage(BaseModel):
    """A single message in a search session."""

    id: Optional[int] = None
    session_id: int
    role: str       # 'user' or 'assistant'
    content: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Storychecker models
# ---------------------------------------------------------------------------

class StorycheckerSession(BaseModel):
    """A story-check session for validating an investment thesis."""

    id: Optional[int] = None
    position_id: int
    ticker: Optional[str] = None
    position_name: str
    skill_name: str
    skill_prompt: str
    created_at: datetime
    verdict: Optional[str] = None


class StorycheckerMessage(BaseModel):
    """A single message in a storychecker session."""

    id: Optional[int] = None
    session_id: int
    role: str       # 'user' or 'assistant'
    content: str
    created_at: datetime


# ---------------------------------------------------------------------------
# News model
# ---------------------------------------------------------------------------

class NewsRun(BaseModel):
    """A single news digest run — snapshot of results for a set of tickers."""

    id: Optional[int] = None
    skill_name: str
    tickers: str       # comma-separated ticker symbols
    result: str        # full markdown digest
    created_at: datetime


# ---------------------------------------------------------------------------
# Position analyses model
# ---------------------------------------------------------------------------

class PositionAnalysis(BaseModel):
    """A persisted analysis result for a position (e.g. from Storychecker)."""

    id: Optional[int] = None
    position_id: int
    agent: str              # e.g. 'storychecker'
    skill_name: str
    verdict: Optional[str] = None   # 'intact', 'gemischt', 'gefaehrdet', 'unknown'
    summary: Optional[str] = None   # one-sentence summary
    session_id: Optional[int] = None  # reference to agent session
    created_at: datetime


# ---------------------------------------------------------------------------
# Rebalance models
# ---------------------------------------------------------------------------

class RebalanceSession(BaseModel):
    """A rebalancing analysis session — stores portfolio snapshot for follow-up context."""

    id: Optional[int] = None
    skill_name: str
    skill_prompt: str
    portfolio_snapshot: str   # pre-built text snapshot stored for follow-up messages
    created_at: datetime


class RebalanceMessage(BaseModel):
    """A single message in a rebalance session."""

    id: Optional[int] = None
    session_id: int
    role: str       # 'user' or 'assistant'
    content: str
    created_at: datetime


class NewsMessage(BaseModel):
    """A follow-up message in a news digest run."""

    id: Optional[int] = None
    run_id: int
    role: str       # 'user' or 'assistant'
    content: str
    created_at: datetime


# ---------------------------------------------------------------------------
# LLM usage model
# ---------------------------------------------------------------------------

class UsageRecord(BaseModel):
    """Token usage for a single LLM call."""

    id: Optional[int] = None
    agent: str          # e.g. 'portfolio_chat', 'news_agent'
    model: str          # e.g. 'qwen3:8b', 'claude-haiku-4-5-20251001'
    input_tokens: int
    output_tokens: int
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
    hidden: bool = False  # True = system skill, injected silently, not shown in UI


class AppConfig(BaseModel):
    """Key-value store for runtime application configuration."""

    key: str
    value: str


# ---------------------------------------------------------------------------
# Scheduled jobs model
# ---------------------------------------------------------------------------

class StructuralScanRun(BaseModel):
    """A single structural-change scan run."""

    id: Optional[int] = None
    skill_name: str
    user_focus: Optional[str] = None   # optional theme focus from the user
    result: str                         # full markdown report
    created_at: datetime


class StructuralScanMessage(BaseModel):
    """A follow-up message in a structural scan session."""

    id: Optional[int] = None
    run_id: int
    role: str       # 'user' or 'assistant'
    content: str
    created_at: datetime


class ScheduledJob(BaseModel):
    """A recurring agent run configured by the user."""

    id: Optional[int] = None
    agent_name: str          # e.g. 'news'
    skill_name: str
    skill_prompt: str
    frequency: str           # 'daily', 'weekly', 'monthly'
    run_hour: int = 8
    run_minute: int = 0
    run_weekday: Optional[int] = None   # 0=Mon … 6=Sun (weekly jobs)
    run_day: Optional[int] = None       # 1–28 (monthly jobs)
    model: Optional[str] = None         # Claude model; None = use app default
    enabled: bool = True
    last_run: Optional[datetime] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Wealth snapshot models
# ---------------------------------------------------------------------------

class WealthSnapshot(BaseModel):
    """A historical snapshot of total wealth (portfolio value + non-tradeable assets)."""

    id: Optional[int] = None
    date: str                       # YYYY-MM-DD
    total_eur: float
    breakdown: Dict[str, float]     # {"Aktie": 120000, "Immobilie": 80000, ...}
    coverage_pct: float             # % of positions with valid value
    missing_pos: Optional[List[str]] = None  # position names without value
    is_manual: bool = False         # True = manually created or corrected
    note: Optional[str] = None      # optional comment
    created_at: datetime


# ---------------------------------------------------------------------------
# Portfolio Story models
# ---------------------------------------------------------------------------

class PortfolioStory(BaseModel):
    """
    The user's portfolio-level narrative — goals, time horizon, priorities.
    Encrypted at rest: story field contains personal financial goals.
    """

    id: Optional[int] = None
    story: str                            # Freies Narrativ, verschlüsselt
    target_year: Optional[int] = None    # z.B. 2040
    liquidity_need: Optional[str] = None  # z.B. "2028: Immobilienkauf ~150k"
    priority: str = "Gemischt"           # "Wachstum" | "Einkommen" | "Sicherheit" | "Gemischt"
    created_at: datetime
    updated_at: datetime


class PortfolioStoryAnalysis(BaseModel):
    """
    Persisted result of a portfolio story check run.
    Three sections: story alignment, performance, stability — each with own verdict.
    """

    id: Optional[int] = None
    verdict: str                  # "intact" | "gemischt" | "gefaehrdet"
    summary: str                  # Ein-Satz-Fazit Story-Check
    perf_verdict: str             # "on_track" | "achtung" | "kritisch"
    perf_summary: str             # Ein-Satz-Fazit Performance
    stability_verdict: str        # "stabil" | "achtung" | "instabil"
    stability_summary: str        # Ein-Satz-Fazit Stabilität
    full_text: str                # Vollständige LLM-Antwort (Markdown)
    created_at: datetime
