"""
Portfolio Agent — natural language interface for portfolio and watchlist management.
"""

import json
from datetime import date
from typing import Optional

from core.asset_class_config import get_asset_class_registry
from core.llm.base import Message, Role
from core.llm.local import OllamaProvider
from core.storage.models import Position
from core.storage.positions import PositionsRepository
from core.storage.skills import SkillsRepository
from agents.market_data_fetcher import MarketDataFetcher
from core.storage.market_data import MarketDataRepository

# All asset classes that support auto-fetch (eligible for watchlist)
_WATCHLIST_CLASSES = [
    "Aktie", "Aktienfonds", "Rentenfonds", "Immobilienfonds", "Edelmetall", "Kryptowährung",
]

# All known asset classes (portfolio accepts all)
_ALL_CLASSES = [
    "Aktie", "Aktienfonds", "Rentenfonds", "Immobilienfonds", "Edelmetall",
    "Kryptowährung", "Anleihe", "Festgeld", "Bargeld", "Immobilie", "Grundstück",
]

SYSTEM_PROMPT = """You are a portfolio management assistant.
The user describes financial transactions or watchlist changes in natural language.
Always call the appropriate tool — never answer in plain text when a tool applies.
Today's date is {today}.

Asset classes: {asset_classes}
Units: Stück (for securities and real estate), Troy Oz or g (for precious metals), EUR (for cash/deposits)

Physical precious metal coins:
- Krügerrand, Maple Leaf, Britannia, Philharmoniker = 1 troy oz gold → ticker GC=F, asset_class Edelmetall, unit Troy Oz
- Silver Maple Leaf, Silver Britannia = 1 troy oz silver → ticker SI=F, asset_class Edelmetall, unit Troy Oz
- quantity = number of coins

Auto-fetch asset classes (Aktie, Aktienfonds, Rentenfonds, Immobilienfonds, Edelmetall, Kryptowährung):
- Always provide the Yahoo Finance ticker symbol (e.g. SAP.DE, AAPL, BTC-USD, IWDA.AS)
- German stocks: append .DE (e.g. SAP.DE, SIE.DE, ALV.DE, MUV2.DE)
- Swiss stocks: append .SW (e.g. NESN.SW)
- UK stocks: append .L (e.g. SHEL.L)
- US stocks: no suffix (e.g. AAPL, MSFT)
- If you do not know the correct Yahoo Finance ticker, ask the user before calling the tool

Non-watchlist asset classes (Festgeld, Bargeld, Anleihe, Immobilie, Grundstück):
- Always add these as portfolio positions (in_portfolio=True), never as watchlist entries
- ticker is not required for these types

Before calling add_portfolio_entry or add_to_watchlist, verify you have all key data:
- For auto-fetch types: ticker is required — ask the user if unknown
- Purchase price and date: if not stated, ask once before saving ("Kaufpreis und -datum fehlen — soll ich die Position trotzdem ohne diese Angaben anlegen?")
- Only skip asking if the user explicitly says to add without that data

For company names you don't know, use the ticker as the name."""

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "add_portfolio_entry",
            "description": "Add a newly purchased asset to the portfolio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker":         {"type": "string", "description": "Ticker/yfinance symbol, e.g. AAPL, SAP.DE (optional for non-auto-fetch types)"},
                    "name":           {"type": "string", "description": "Full asset name"},
                    "asset_class":    {"type": "string", "enum": _ALL_CLASSES},
                    "quantity":       {"type": "number", "description": "Number of units (optional for Immobilie/Grundstück)"},
                    "unit":           {"type": "string", "description": "Stück, Troy Oz, g, or EUR"},
                    "purchase_price": {"type": "number", "description": "Price per unit in EUR (optional)"},
                    "purchase_date":  {"type": "string", "description": "ISO date, e.g. 2024-01-15"},
                    "isin":           {"type": "string"},
                    "wkn":            {"type": "string"},
                    "notes":          {"type": "string"},
                    "empfehlung":     {"type": "string", "description": "User recommendation label, e.g. Kaufen, Halten, Verkaufen"},
                    "story":          {"type": "string", "description": "Investment thesis or rationale"},
                    "anlageart":      {"type": "string", "description": "Sub-type of asset class, e.g. ETF, Einzelaktie, Münze (optional)"},
                },
                "required": ["name", "asset_class", "unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_portfolio_entry",
            "description": "Remove an entry from the portfolio by its ID.",
            "parameters": {
                "type": "object",
                "properties": {"entry_id": {"type": "integer"}},
                "required": ["entry_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_portfolio",
            "description": "List all portfolio entries.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_watchlist",
            "description": "Add an asset to the watchlist. Only supported for auto-fetch asset classes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker":      {"type": "string", "description": "Ticker/yfinance symbol"},
                    "name":        {"type": "string"},
                    "asset_class": {"type": "string", "enum": _WATCHLIST_CLASSES},
                    "unit":        {"type": "string"},
                    "notes":       {"type": "string"},
                    "empfehlung":  {"type": "string", "description": "User recommendation label"},
                    "story":       {"type": "string", "description": "Investment thesis"},
                },
                "required": ["ticker", "name", "asset_class", "unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_watchlist",
            "description": "Remove an entry from the watchlist by its ID.",
            "parameters": {
                "type": "object",
                "properties": {"entry_id": {"type": "integer"}},
                "required": ["entry_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_watchlist",
            "description": "List all watchlist entries.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_watchlist",
            "description": "Remove ALL entries from the watchlist at once.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clear_portfolio",
            "description": "Remove ALL entries from the portfolio at once.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


class PortfolioAgent:
    def __init__(
        self,
        positions_repo: PositionsRepository,
        llm: OllamaProvider,
        skills_repo: Optional[SkillsRepository] = None,
        market_fetcher: Optional[MarketDataFetcher] = None,
        market_repo: Optional[MarketDataRepository] = None,
    ):
        self._positions = positions_repo
        self._llm = llm
        self._skills_repo = skills_repo
        self._market_fetcher = market_fetcher
        self._market_repo = market_repo

    # ------------------------------------------------------------------
    # Public API for other agents
    # ------------------------------------------------------------------

    def add_to_watchlist(
        self,
        ticker: str,
        name: str,
        asset_class: str,
        unit: str = "Stück",
        notes: Optional[str] = None,
    ) -> Position:
        """Direct API for other agents to add entries to the watchlist."""
        registry = get_asset_class_registry()
        cfg = registry.require(asset_class)
        position = Position(
            ticker=ticker,
            name=name,
            asset_class=asset_class,
            investment_type=cfg.investment_type,
            unit=unit,
            notes=notes,
            added_date=date.today(),
            in_portfolio=False,
            in_watchlist=True,
            recommendation_source="agent",
        )
        return self._positions.add(position)

    # ------------------------------------------------------------------
    # Natural language interface
    # ------------------------------------------------------------------

    async def chat(self, user_message: str) -> str:
        registry = get_asset_class_registry()
        system = SYSTEM_PROMPT.format(
            today=date.today().isoformat(),
            asset_classes=", ".join(registry.all_names()),
        )
        # Inject hidden system skills (Datenpflege-Assistent etc.)
        if self._skills_repo:
            system_skills = self._skills_repo.get_system_skills()
            for s in system_skills:
                system += f"\n\n{s.prompt}"

        messages = [
            Message(role=Role.SYSTEM, content=system),
            Message(role=Role.USER, content=user_message),
        ]

        response = await self._llm.chat_with_tools(messages, tools=TOOLS)

        if not response.has_tool_calls:
            return response.content or "Done."

        results = []
        for tool_call in response.tool_calls:
            result = self._execute_tool(tool_call.name, tool_call.arguments)
            results.append(f"{tool_call.name}: {json.dumps(result, ensure_ascii=False)}")

        result_summary = "\n".join(results)
        follow_up = messages + [
            Message(role=Role.ASSISTANT, content=response.content or ""),
            Message(
                role=Role.USER,
                content=(
                    f"Tool results:\n{result_summary}\n\n"
                    "Please confirm what was saved or done in 1-2 sentences in German. "
                    "For saved positions include: name, ticker (if available), quantity + unit, "
                    "purchase price (€), purchase date. If there was an error, explain it clearly."
                ),
            ),
        ]
        final = await self._llm.chat_with_tools(follow_up, tools=[])
        return final.content or "Done."

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def _execute_tool(self, name: str, args: dict) -> dict:
        if name == "add_portfolio_entry":
            return self._tool_add_portfolio(args)
        elif name == "remove_portfolio_entry":
            return self._tool_remove_portfolio(args)
        elif name == "list_portfolio":
            return self._tool_list_portfolio()
        elif name == "add_to_watchlist":
            return self._tool_add_watchlist(args)
        elif name == "remove_from_watchlist":
            return self._tool_remove_watchlist(args)
        elif name == "list_watchlist":
            return self._tool_list_watchlist()
        elif name == "clear_watchlist":
            return self._tool_clear_watchlist()
        elif name == "clear_portfolio":
            return self._tool_clear_portfolio()
        else:
            return {"error": f"Unknown tool: {name}"}

    def _tool_add_portfolio(self, args: dict) -> dict:
        registry = get_asset_class_registry()
        asset_class = args["asset_class"]
        cfg = registry.require(asset_class)

        # Validate purchase_date
        purchase_date_raw = args.get("purchase_date")
        purchase_date = None
        if purchase_date_raw:
            try:
                purchase_date = date.fromisoformat(purchase_date_raw)
            except ValueError:
                return {"error": f"Invalid date format: '{purchase_date_raw}'. Use YYYY-MM-DD."}
            if purchase_date > date.today():
                return {"error": f"Purchase date {purchase_date_raw} is in the future. Please use today's date or earlier."}

        # Validate quantity
        quantity = args.get("quantity")
        if quantity is not None and float(quantity) <= 0:
            return {"error": "Quantity must be greater than 0."}

        # Validate purchase_price
        purchase_price = args.get("purchase_price")
        if purchase_price is not None and float(purchase_price) < 0:
            return {"error": "Purchase price cannot be negative."}

        position = Position(
            ticker=args.get("ticker") or None,
            name=args["name"],
            asset_class=asset_class,
            investment_type=cfg.investment_type,
            quantity=float(quantity) if quantity is not None else None,
            unit=args.get("unit", cfg.default_unit),
            purchase_price=float(purchase_price) if purchase_price is not None else None,
            purchase_date=purchase_date,
            isin=args.get("isin"),
            wkn=args.get("wkn"),
            notes=args.get("notes"),
            empfehlung=args.get("empfehlung"),
            story=args.get("story"),
            anlageart=args.get("anlageart") or None,
            added_date=date.today(),
            in_portfolio=True,
        )
        saved = self._positions.add(position)

        # Auto-fetch current price for new auto-fetch positions with a ticker
        if saved.ticker and cfg.auto_fetch and self._market_fetcher and self._market_repo:
            try:
                records, _ = self._market_fetcher.fetch_current_prices([saved.ticker])
                for rec in records:
                    self._market_repo.upsert_price(rec)
            except Exception:
                pass  # non-critical

        return {
            "success": True,
            "id": saved.id,
            "ticker": saved.ticker,
            "name": saved.name,
            "quantity": saved.quantity,
            "unit": saved.unit,
            "purchase_price": saved.purchase_price,
            "purchase_date": saved.purchase_date.isoformat() if saved.purchase_date else None,
        }

    def _tool_remove_portfolio(self, args: dict) -> dict:
        deleted = self._positions.delete(args["entry_id"])
        return {"success": deleted}

    def _tool_list_portfolio(self) -> dict:
        entries = self._positions.get_portfolio()
        return {
            "entries": [
                {
                    "id": e.id,
                    "ticker": e.ticker,
                    "name": e.name,
                    "asset_class": e.asset_class,
                    "quantity": e.quantity,
                    "unit": e.unit,
                    "purchase_price": e.purchase_price,
                    "purchase_date": e.purchase_date.isoformat() if e.purchase_date else None,
                    "empfehlung": e.empfehlung,
                }
                for e in entries
            ]
        }

    def _tool_add_watchlist(self, args: dict) -> dict:
        registry = get_asset_class_registry()
        asset_class = args["asset_class"]
        cfg = registry.require(asset_class)
        position = Position(
            ticker=args["ticker"],
            name=args["name"],
            asset_class=asset_class,
            investment_type=cfg.investment_type,
            unit=args.get("unit", cfg.default_unit),
            notes=args.get("notes"),
            empfehlung=args.get("empfehlung"),
            story=args.get("story"),
            added_date=date.today(),
            in_portfolio=False,
            in_watchlist=True,
            recommendation_source="user",
        )
        saved = self._positions.add(position)
        return {"success": True, "id": saved.id, "ticker": saved.ticker}

    def _tool_remove_watchlist(self, args: dict) -> dict:
        deleted = self._positions.delete(args["entry_id"])
        return {"success": deleted}

    def _tool_clear_portfolio(self) -> dict:
        entries = self._positions.get_portfolio()
        count = 0
        for entry in entries:
            if self._positions.delete(entry.id):
                count += 1
        return {"deleted": count}

    def _tool_clear_watchlist(self) -> dict:
        entries = self._positions.get_watchlist()
        count = 0
        for entry in entries:
            if self._positions.delete(entry.id):
                count += 1
        return {"deleted": count}

    def _tool_list_watchlist(self) -> dict:
        entries = self._positions.get_watchlist()
        return {
            "entries": [
                {
                    "id": e.id,
                    "ticker": e.ticker,
                    "name": e.name,
                    "asset_class": e.asset_class,
                    "unit": e.unit,
                    "added_date": e.added_date.isoformat(),
                    "empfehlung": e.empfehlung,
                    "story": e.story,
                }
                for e in entries
            ]
        }
