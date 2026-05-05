"""
Search Agent — chat-based investment screening using Claude + web search.

Flow per chat() call:
  1. Save user message to DB
  2. Load conversation history from DB
  3. Call Claude with web_search + add_to_watchlist tools
  4. If Claude calls add_to_watchlist → execute → send result → call Claude again
  5. Save final assistant response to DB and return it
"""

from __future__ import annotations
import logging


from datetime import date
from typing import Optional

from core.asset_class_config import get_asset_class_registry
from core.llm.claude import ClaudeProvider, ClaudeResponse, ClaudeToolCall
from core.storage.models import Position, SearchSession
from core.storage.positions import PositionsRepository
from core.storage.search import SearchRepository


logger = logging.getLogger(__name__)
# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """You are an experienced investment screening analyst.
The user wants to find investment opportunities matching specific criteria.

Approach:
1. Use web search to find current, relevant investments matching the criteria
2. Screen and rank results according to the skill strategy below
3. Present a structured output:
   - **Summary** (2–3 sentences of key findings)
   - **Ranked Candidates** — each entry:
     - Ticker/ISIN, full name, sector/theme
     - Key metrics: P/E, dividend yield, TER (for funds), 1y/3y performance, etc.
     - Brief assessment (1–2 sentences)
   - **Cost Warning** — flag any high fees, wide spreads, or illiquid markets
   - **Watchlist Picks** — top 1–3 candidates worth adding to the watchlist

Use the propose_for_watchlist tool for each investment you recommend under **Watchlist Picks**. The user will review your proposals and decide which ones to add.
Be factual and cite specific numbers wherever available."""

# ------------------------------------------------------------------
# Tool definitions
# ------------------------------------------------------------------

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

PROPOSE_FOR_WATCHLIST_TOOL = {
    "name": "propose_for_watchlist",
    "description": "Propose an investment as a watchlist candidate. The user will review and confirm before it is added.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Ticker symbol or ISIN, e.g. AAPL, IE00B4L5Y983, SAP.DE",
            },
            "name": {
                "type": "string",
                "description": "Full name of the investment",
            },
            "asset_class": {
                "type": "string",
                "enum": ["Aktie", "Aktienfonds", "Immobilienfonds", "Edelmetall"],
                "description": "Asset class: Aktie = stock, Aktienfonds = equity fund/ETF",
            },
            "notes": {
                "type": "string",
                "description": "Brief reason for the watchlist (1 sentence)",
            },
            "story": {
                "type": "string",
                "description": "Investment thesis in 2–3 sentences — why this investment is interesting, what the core opportunity is, and what to watch",
            },
        },
        "required": ["ticker", "name", "asset_class"],
    },
}

TOOLS = [WEB_SEARCH_TOOL, PROPOSE_FOR_WATCHLIST_TOOL]
CLIENT_TOOL_NAMES = {"propose_for_watchlist"}
MAX_TOOL_ITERATIONS = 5


class SearchAgent:

    def __init__(
        self,
        positions_repo: PositionsRepository,
        search_repo: SearchRepository,
        llm: ClaudeProvider,
    ):
        self._positions = positions_repo
        self._search = search_repo
        self._llm = llm
        self._session_proposals: dict[int, list[dict]] = {}

    @property
    def model(self) -> str:
        return self._llm.model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_session(
        self,
        query: str,
        skill_name: str,
        skill_prompt: str,
    ) -> SearchSession:
        """Create a new search session."""
        return self._search.create_session(
            query=query,
            skill_name=skill_name,
            skill_prompt=skill_prompt,
        )

    async def chat(self, session_id: int, user_message: str, enable_thinking: bool = False) -> tuple[str, list[dict]]:
        """Send a user message in an existing session and return the assistant reply + proposals."""
        session = self._search.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        self._session_proposals[session_id] = []
        self._current_session_id = session_id

        system = BASE_SYSTEM_PROMPT + "\n\n## Screening Strategy\n" + session.skill_prompt

        api_messages = self._build_api_messages(session_id)
        api_messages.append({"role": "user", "content": user_message})
        self._search.add_message(session_id, "user", user_message)

        response: Optional[ClaudeResponse] = None
        for _ in range(MAX_TOOL_ITERATIONS):
            response = await self._llm.chat_with_tools(
                messages=api_messages,
                tools=TOOLS,
                system=system,
                max_tokens=4096,
                enable_thinking=enable_thinking,
            )

            client_calls = [
                tc for tc in response.tool_calls if tc.name in CLIENT_TOOL_NAMES
            ]
            if not client_calls:
                break

            tool_results = []
            for tc in client_calls:
                result_text = self._execute_tool(tc)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result_text,
                })

            api_messages.append({"role": "assistant", "content": response.raw_blocks})
            api_messages.append({"role": "user", "content": tool_results})

        final_content = response.content if response else ""
        self._search.add_message(session_id, "assistant", final_content)
        proposals = self._session_proposals.get(session_id, [])
        return final_content, proposals

    def list_sessions(self, limit: int = 50):
        return self._search.list_sessions(limit=limit)

    def get_session(self, session_id: int) -> Optional[SearchSession]:
        return self._search.get_session(session_id)

    def get_messages(self, session_id: int):
        return self._search.get_messages(session_id)

    def delete_session(self, session_id: int) -> None:
        self._search.delete_session(session_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_api_messages(self, session_id: int) -> list[dict]:
        db_messages = self._search.get_messages(session_id)
        return [
            {"role": m.role, "content": m.content}
            for m in db_messages
            if m.role in ("user", "assistant")
        ]

    def _execute_tool(self, tool_call: ClaudeToolCall) -> str:
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
        ticker = proposal.get("ticker", "")
        name = proposal.get("name", ticker)
        asset_class = proposal.get("asset_class", "Aktie")
        notes = proposal.get("notes", "")
        story = proposal.get("story", "")

        registry = get_asset_class_registry()
        try:
            cfg = registry.require(asset_class)
        except Exception:
            cfg = registry.require("Aktie")

        position = Position(
            ticker=ticker,
            name=name,
            asset_class=asset_class,
            investment_type=cfg.investment_type,
            unit=cfg.default_unit,
            notes=notes,
            story=story or None,
            added_date=date.today(),
            in_portfolio=False,
            in_watchlist=True,
            recommendation_source="search_agent",
        )
        saved = self._positions.add(position)

        if story and saved.id:
            try:
                from state import get_storychecker_agent
                storychecker = get_storychecker_agent()
                storychecker.start_session(position=saved)
            except Exception as e:
                logger.warning(f"Could not auto-validate story: {e}")

        return saved
