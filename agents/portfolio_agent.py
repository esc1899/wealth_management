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

SYSTEM_PROMPT = """You are a portfolio management assistant.
The user describes financial transactions or watchlist changes in natural language.
Always call the appropriate tool — never answer in plain text when a tool applies.
Today's date is {today}.

Asset classes: Aktie, Aktienfonds, Immobilienfonds, Edelmetall
Units: Stück (for securities), Troy Oz or g (for precious metals)

Physical precious metal coins:
- Krügerrand, Maple Leaf, Britannia, Philharmoniker = 1 troy oz gold → ticker GC=F, asset_class Edelmetall, unit Troy Oz
- Silver Maple Leaf, Silver Britannia = 1 troy oz silver → ticker SI=F, asset_class Edelmetall, unit Troy Oz
- quantity = number of coins

If purchase price is not stated, omit it.
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
                    "ticker":         {"type": "string", "description": "Ticker/yfinance symbol, e.g. AAPL, SAP.DE"},
                    "name":           {"type": "string", "description": "Full asset name"},
                    "asset_class":    {"type": "string", "enum": ["Aktie", "Aktienfonds", "Immobilienfonds", "Edelmetall"]},
                    "quantity":       {"type": "number"},
                    "unit":           {"type": "string", "description": "Stück, Troy Oz, or g"},
                    "purchase_price": {"type": "number", "description": "Price per unit (optional)"},
                    "purchase_date":  {"type": "string", "description": "ISO date, e.g. 2024-01-15"},
                    "isin":           {"type": "string"},
                    "wkn":            {"type": "string"},
                    "notes":          {"type": "string"},
                },
                "required": ["ticker", "name", "asset_class", "quantity", "unit", "purchase_date"],
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
            "description": "Add an asset to the watchlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker":      {"type": "string"},
                    "name":        {"type": "string"},
                    "asset_class": {"type": "string", "enum": ["Aktie", "Aktienfonds", "Immobilienfonds", "Edelmetall"]},
                    "unit":        {"type": "string"},
                    "notes":       {"type": "string"},
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
]


class PortfolioAgent:
    def __init__(self, positions_repo: PositionsRepository, llm: OllamaProvider):
        self._positions = positions_repo
        self._llm = llm

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
            recommendation_source="agent",
        )
        return self._positions.add(position)

    # ------------------------------------------------------------------
    # Natural language interface
    # ------------------------------------------------------------------

    async def chat(self, user_message: str) -> str:
        system = SYSTEM_PROMPT.format(today=date.today().isoformat())
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
                content=f"Tool results:\n{result_summary}\n\nPlease summarize what was done in one or two sentences.",
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
        else:
            return {"error": f"Unknown tool: {name}"}

    def _tool_add_portfolio(self, args: dict) -> dict:
        registry = get_asset_class_registry()
        asset_class = args["asset_class"]
        cfg = registry.require(asset_class)
        position = Position(
            ticker=args["ticker"],
            name=args["name"],
            asset_class=asset_class,
            investment_type=cfg.investment_type,
            quantity=args["quantity"],
            unit=args.get("unit", cfg.default_unit),
            purchase_price=args.get("purchase_price") or None,
            purchase_date=date.fromisoformat(args["purchase_date"]),
            isin=args.get("isin"),
            wkn=args.get("wkn"),
            notes=args.get("notes"),
            added_date=date.today(),
            in_portfolio=True,
        )
        saved = self._positions.add(position)
        return {"success": True, "id": saved.id, "ticker": saved.ticker}

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
            added_date=date.today(),
            in_portfolio=False,
            recommendation_source="user",
        )
        saved = self._positions.add(position)
        return {"success": True, "id": saved.id, "ticker": saved.ticker}

    def _tool_remove_watchlist(self, args: dict) -> dict:
        deleted = self._positions.delete(args["entry_id"])
        return {"success": deleted}

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
                    "recommendation_source": e.recommendation_source,
                    "notes": e.notes,
                }
                for e in entries
            ]
        }
