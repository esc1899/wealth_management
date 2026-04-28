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
from agents.agent_language import response_language_instruction


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

Wenn die Aktie als investitionswürdig bewertet ist, verwende das Vorschlag-Tool propose_for_watchlist zur Empfehlung. Der Nutzer wird die Vorschläge review und entscheiden, welche zur Watchlist hinzugefügt werden sollen.

Sei konkret und belege deine Aussagen mit Zahlen wenn möglich."""

# ------------------------------------------------------------------
# Tool definitions
# ------------------------------------------------------------------

# Server-side web search — Anthropic executes this, no client handling needed
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

PROPOSE_FOR_WATCHLIST_TOOL = {
    "name": "propose_for_watchlist",
    "description": "Propose a stock as a watchlist candidate. The user will review and confirm before it is added.",
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
            "story": {
                "type": "string",
                "description": "Investment thesis in 2–3 sentences — why this stock is interesting, what the core opportunity is, and what to watch",
            },
        },
        "required": ["ticker", "name", "asset_class"],
    },
}

TOOLS = [WEB_SEARCH_TOOL, PROPOSE_FOR_WATCHLIST_TOOL]

# Tools that require client-side execution (not server-side)
CLIENT_TOOL_NAMES = {"propose_for_watchlist"}

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
        self._session_proposals: dict[int, list[dict]] = {}
        self._current_session_id: int | None = None

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

    async def chat(self, session_id: int, user_message: str, language: str = "de") -> tuple[str, list[dict]]:
        """
        Send a user message in an existing session and return the assistant reply + proposals.
        Handles the tool-calling loop for propose_for_watchlist.

        Args:
            session_id: The research session ID
            user_message: The user's input
            language: Language code for LLM output (default: "de")

        Returns:
            Tuple of (assistant_reply, proposals_list)
        """
        session = self._research.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        self._session_proposals[session_id] = []
        self._current_session_id = session_id

        # Build system prompt = base + strategy focus + language
        self._llm.skill_context = session.strategy_name
        system = BASE_SYSTEM_PROMPT + "\n" + response_language_instruction(language) + "\n\n## Analysestrategie\n" + session.strategy_prompt

        # Load history before adding new message, then append manually
        api_messages = self._build_api_messages(session_id)
        api_messages.append({"role": "user", "content": user_message})

        # Persist user message to DB
        self._research.add_message(session_id, "user", user_message)

        # Tool calling loop (handles client-side tools like propose_for_watchlist)
        for _ in range(MAX_TOOL_ITERATIONS):
            response = await self._llm.chat_with_tools(
                messages=api_messages,
                tools=TOOLS,
                system=system,
                max_tokens=4096,
                enable_cache=False,
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
        proposals = self._session_proposals.get(session_id, [])
        return response.content, proposals

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
        if tool_call.name == "propose_for_watchlist":
            return self._tool_propose_for_watchlist(tool_call.input)
        return f"Unknown tool: {tool_call.name}"

    def _tool_propose_for_watchlist(self, args: dict) -> str:
        """Collect proposal without writing to DB — user will confirm later."""
        proposal = {
            "ticker": args.get("ticker", ""),
            "name": args.get("name", args.get("ticker", "")),
            "asset_class": args.get("asset_class", "Aktie"),
            "notes": args.get("notes", ""),
            "story": args.get("story", ""),
        }
        session_id = self._current_session_id
        self._session_proposals[session_id].append(proposal)
        return f"Added '{proposal['name']}' ({proposal['ticker']}) to proposal list for review."

    def add_from_proposal(self, session_id: int, proposal: dict) -> Position:
        """Write a proposal to the watchlist after user confirmation."""
        session = self._research.get_session(session_id)
        ticker = proposal.get("ticker", "")
        name = proposal.get("name", ticker)
        asset_class = proposal.get("asset_class", "Aktie")
        notes = proposal.get("notes", "")
        story = proposal.get("story", "")
        investment_type = "Wertpapiere"

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
            strategy=session.strategy_name if session else None,
            notes=notes,
            story=story or None,
        )
        saved = self._positions.add(position)

        if story and saved.id:
            try:
                from state import get_storychecker_agent
                storychecker = get_storychecker_agent()
                storychecker.start_session(position=saved)
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.warning(f"Could not auto-validate story: {e}")

        return saved
