"""
Research Agent — chat-based stock analysis using Claude + web search.

Flow per chat() call:
  1. Save user message to DB
  2. Load conversation history from DB
  3. Call Claude with web_search + add_to_watchlist tools
  4. If Claude calls add_to_watchlist → execute → send result → call Claude again
  5. Save final assistant response to DB and return it
"""

from __future__ import annotations
import logging


import json
from datetime import date
from typing import Optional

from core.llm.claude import ClaudeProvider, ClaudeResponse, ClaudeToolCall
from core.storage.models import Position, ResearchSession
from core.storage.positions import PositionsRepository
from core.storage.research import ResearchRepository
from core.strategy_config import StrategyConfig, StrategyRegistry


logger = logging.getLogger(__name__)
# ------------------------------------------------------------------
# System prompt base
# ------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """Du bist ein erfahrener Investment-Research-Analyst.
Der Nutzer möchte eine Aktie analysieren und bewerten.

Vorgehen:
1. Suche im Web nach aktuellen Informationen zur Aktie (Fundamentaldaten, Nachrichten, Analystenmeinungen)
2. Analysiere die gefundenen Informationen gemäß der unten definierten Analysestrategie
3. Gib eine ausführliche, strukturierte Bewertung mit folgenden Abschnitten:
   - **Kurzfazit** (2-3 Sätze Zusammenfassung)
   - **Fundamentaldaten** (KGV, KBV, Umsatz/Gewinnwachstum, Margen, Verschuldung)
   - **Wachstumsperspektiven** (Markt, Produkte, Strategie)
   - **Stärken**
   - **Risiken**
   - **Analystenmeinungen & Kursziele**
   - **Bewertung gemäß Strategie** (konkrete Einschätzung mit Begründung)

Wichtig: Füge die Aktie zur Watchlist NUR hinzu, wenn der Nutzer dies explizit verlangt (z.B. "Füge zur Watchlist hinzu" oder "Watchlist").

Antworte auf Deutsch. Sei konkret und belege deine Aussagen mit Zahlen wenn möglich."""

# ------------------------------------------------------------------
# Tool definitions
# ------------------------------------------------------------------

# Server-side web search — Anthropic executes this, no client handling needed
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

ADD_TO_WATCHLIST_TOOL = {
    "name": "add_to_watchlist",
    "description": "Füge eine Aktie zur Watchlist hinzu wenn du sie als investitionswürdig bewertest.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Ticker-Symbol, z.B. AAPL, SAP.DE, BMW.DE",
            },
            "name": {
                "type": "string",
                "description": "Vollständiger Unternehmensname",
            },
            "asset_class": {
                "type": "string",
                "enum": ["Aktie", "Aktienfonds", "Immobilienfonds", "Edelmetall"],
                "description": "Asset-Klasse, für Aktien immer 'Aktie'",
            },
            "notes": {
                "type": "string",
                "description": "Kurze Begründung warum die Aktie empfohlen wird",
            },
        },
        "required": ["ticker", "name", "asset_class"],
    },
}

TOOLS = [WEB_SEARCH_TOOL, ADD_TO_WATCHLIST_TOOL]

# Tools that require client-side execution (not server-side)
CLIENT_TOOL_NAMES = {"add_to_watchlist"}

# Maximum tool-call iterations to prevent infinite loops
MAX_TOOL_ITERATIONS = 5


class ResearchAgent:

    def __init__(
        self,
        positions_repo: PositionsRepository,
        research_repo: ResearchRepository,
        llm: ClaudeProvider,
        strategy_registry: StrategyRegistry,
    ):
        self._positions = positions_repo
        self._research = research_repo
        self._llm = llm
        self._strategies = strategy_registry

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def model(self) -> str:
        return self._llm.model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_session(
        self,
        ticker: str,
        strategy_name: str,
        company_name: Optional[str] = None,
        custom_prompt: Optional[str] = None,
    ) -> ResearchSession:
        """
        Create a new research session.
        For custom strategies pass strategy_name=CUSTOM_STRATEGY_NAME and custom_prompt=<text>.
        For named strategies strategy_name must exist in the registry.
        """
        if custom_prompt is not None:
            strategy_prompt = custom_prompt
        else:
            strategy = self._strategies.require(strategy_name)
            strategy_prompt = strategy.system_prompt

        return self._research.create_session(
            ticker=ticker,
            strategy_name=strategy_name,
            strategy_prompt=strategy_prompt,
            company_name=company_name,
        )

    async def chat(self, session_id: int, user_message: str) -> str:
        """
        Send a user message in an existing session and return the assistant reply.
        Handles the tool-calling loop for add_to_watchlist.
        """
        session = self._research.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        # Build system prompt = base + strategy focus
        self._llm.skill_context = session.strategy_name
        system = BASE_SYSTEM_PROMPT + "\n\n## Analysestrategie\n" + session.strategy_prompt

        # Load history before adding new message, then append manually
        api_messages = self._build_api_messages(session_id)
        api_messages.append({"role": "user", "content": user_message})

        # Persist user message to DB
        self._research.add_message(session_id, "user", user_message)

        # Tool calling loop (handles client-side tools like add_to_watchlist)
        for _ in range(MAX_TOOL_ITERATIONS):
            response = await self._llm.chat_with_tools(
                messages=api_messages,
                tools=TOOLS,
                system=system,
                max_tokens=4096,
            )

            client_calls = [
                tc for tc in response.tool_calls
                if tc.name in CLIENT_TOOL_NAMES
            ]

            if not client_calls:
                # No client tools to execute — we're done
                break

            # Execute each client tool call
            tool_results = []
            for tc in client_calls:
                result_text = self._execute_tool(session, tc)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result_text,
                })

            # Extend conversation: assistant message + tool results
            api_messages.append({
                "role": "assistant",
                "content": response.raw_blocks,
            })
            api_messages.append({
                "role": "user",
                "content": tool_results,
            })

        # Persist final assistant response
        self._research.add_message(session_id, "assistant", response.content)
        return response.content

    def list_sessions(self, limit: int = 50) -> list[ResearchSession]:
        return self._research.list_sessions(limit=limit)

    def get_session(self, session_id: int) -> Optional[ResearchSession]:
        return self._research.get_session(session_id)

    def get_messages(self, session_id: int):
        return self._research.get_messages(session_id)

    def delete_session(self, session_id: int) -> None:
        self._research.delete_session(session_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_api_messages(self, session_id: int) -> list[dict]:
        """Convert DB messages to Anthropic API format."""
        db_messages = self._research.get_messages(session_id)
        api_messages = []
        for msg in db_messages:
            if msg.role in ("user", "assistant"):
                api_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })
        return api_messages

    def _execute_tool(self, session: ResearchSession, tool_call: ClaudeToolCall) -> str:
        """Execute a client-side tool call and return the result as a string."""
        if tool_call.name == "add_to_watchlist":
            return self._tool_add_to_watchlist(session, tool_call.input)
        return f"Unknown tool: {tool_call.name}"

    def _tool_add_to_watchlist(self, session: ResearchSession, args: dict) -> str:
        ticker = args.get("ticker", session.ticker)
        name = args.get("name", ticker)
        asset_class = args.get("asset_class", "Aktie")
        notes = args.get("notes", "")
        investment_type = "Wertpapiere"  # all stock-type assets

        try:
            position = Position(
                ticker=ticker,
                name=name,
                asset_class=asset_class,
                investment_type=investment_type,
                unit="Stück",
                added_date=date.today(),
                in_portfolio=False,
                in_watchlist=True,
                recommendation_source="research_agent",
                strategy=session.strategy_name,
                notes=notes,
            )
            saved = self._positions.add(position)
            return f"'{name}' ({ticker}) wurde zur Watchlist hinzugefügt (ID: {saved.id})."
        except Exception as exc:
            return f"Fehler beim Hinzufügen zur Watchlist: {exc}"
