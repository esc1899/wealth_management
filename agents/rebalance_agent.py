"""
Rebalance Agent — portfolio rebalancing analysis using local Ollama LLM.
Private 🔒 — all portfolio data stays local, nothing is sent to external APIs.

Flow per start_session() call:
  1. Load all portfolio positions from DB
  2. Fetch current market prices from DB
  3. Build a structured portfolio snapshot (stored in DB for follow-up context)
  4. Send to local LLM with the selected skill strategy + optional user context
  5. Persist user + assistant messages and return the session

Flow per chat() call:
  1. Load session (for portfolio snapshot + skill) and message history from DB
  2. Send full conversation to LLM
  3. Persist and return the assistant reply
"""

from __future__ import annotations

from datetime import date
from typing import Optional, Tuple

from core.llm.base import Message, Role
from core.llm.local import OllamaProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.market_data import MarketDataRepository
from core.storage.models import Position, RebalanceSession
from core.storage.positions import PositionsRepository
from core.storage.rebalance import RebalanceRepository

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

SYSTEM_PROMPT = """You are a portfolio management advisor.
You will receive a snapshot of the user's portfolio with current positions, market values, and portfolio weights.
Your task is to analyze the portfolio according to the provided strategy and give concrete, actionable rebalancing recommendations.

Rules:
- Recommendations only — you cannot execute trades
- Be cost-aware: only recommend actions where the benefit clearly outweighs transaction costs
- Flag drift if a position's weight has moved significantly from a balanced allocation
- Be specific: mention approximate EUR amounts and percentages where useful
- Keep the output structured and scannable
- Today's date is {today}"""


class RebalanceAgent:
    """
    Conversational agent: start_session() triggers the initial analysis,
    chat() handles follow-up questions. Uses local Ollama LLM (private 🔒).
    """

    def __init__(
        self,
        positions_repo: PositionsRepository,
        market_repo: MarketDataRepository,
        analyses_repo: PositionAnalysesRepository,
        llm: OllamaProvider,
    ):
        self._positions = positions_repo
        self._market = market_repo
        self._analyses = analyses_repo
        self._llm = llm

    async def start_session(
        self,
        skill_name: str,
        skill_prompt: str,
        user_context: str,
        repo: RebalanceRepository,
    ) -> Tuple[RebalanceSession, str]:
        """
        Build portfolio snapshot, create a session in DB, run initial analysis.

        Args:
            skill_name:   Display name of the strategy
            skill_prompt: The strategy prompt
            user_context: Optional user input ("Ich möchte €2.000 investieren")
            repo:         RebalanceRepository for persistence

        Returns:
            (session, assistant_reply)
        """
        portfolio = self._positions.get_portfolio()
        if not portfolio:
            snapshot = "Portfolio is empty."
        else:
            snapshot = self._build_portfolio_context(portfolio)

        session = repo.create_session(
            skill_name=skill_name,
            skill_prompt=skill_prompt,
            portfolio_snapshot=snapshot,
        )

        user_message = user_context.strip() if user_context.strip() else (
            "Please analyze my portfolio and provide rebalancing recommendations according to the strategy."
        )
        repo.add_message(session.id, "user", user_message)

        system = (
            SYSTEM_PROMPT.format(today=date.today().isoformat())
            + f"\n\n## Strategy: {skill_name}\n{skill_prompt}"
            + f"\n\n## Portfolio\n{snapshot}"
        )
        messages = [
            Message(role=Role.SYSTEM, content=system),
            Message(role=Role.USER, content=user_message),
        ]
        reply = await self._llm.chat(messages, max_tokens=2048)

        repo.add_message(session.id, "assistant", reply)
        return session, reply

    async def chat(
        self,
        session_id: int,
        user_message: str,
        repo: RebalanceRepository,
    ) -> str:
        """
        Send a follow-up message in an existing session.

        Args:
            session_id:   ID of the rebalance session
            user_message: The user's follow-up question
            repo:         RebalanceRepository for persistence

        Returns:
            Assistant reply string
        """
        session = repo.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        repo.add_message(session_id, "user", user_message)

        system = (
            SYSTEM_PROMPT.format(today=date.today().isoformat())
            + f"\n\n## Strategy: {session.skill_name}\n{session.skill_prompt}"
            + f"\n\n## Portfolio\n{session.portfolio_snapshot}"
        )

        history = repo.get_messages(session_id)
        messages = [Message(role=Role.SYSTEM, content=system)] + [
            Message(
                role=Role.USER if m.role == "user" else Role.ASSISTANT,
                content=m.content,
            )
            for m in history
        ]

        reply = await self._llm.chat(messages, max_tokens=2048)
        repo.add_message(session_id, "assistant", reply)
        return reply

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_portfolio_context(self, positions: list[Position]) -> str:
        """Format portfolio positions as readable context for the LLM."""
        rows: list[tuple[Position, Optional[float], Optional[float]]] = []
        total_value = 0.0

        for pos in positions:
            price_record = self._market.get_price(pos.ticker) if pos.ticker else None
            value: Optional[float] = None
            if pos.quantity is not None and price_record is not None:
                value = pos.quantity * price_record.price_eur
                total_value += value
            rows.append((pos, price_record.price_eur if price_record else None, value))

        verdicts = self._analyses.get_latest_bulk(
            [p.id for p in positions if p.id], "storychecker"
        )

        lines = [f"**Portfolio snapshot — {date.today().isoformat()}**\n"]

        for pos, current_price, value in rows:
            weight = f"{value / total_value * 100:.1f}%" if value and total_value > 0 else "n/a"
            purchase = f"€{pos.purchase_price:.2f}" if pos.purchase_price else "unknown"
            current_str = f"€{current_price:.2f}" if current_price is not None else "no price"
            value_str = f"€{value:,.0f}" if value is not None else "n/a"

            if pos.quantity is not None:
                qty = pos.quantity
                qty_str = (
                    f"{int(qty):,}"
                    if qty == int(qty)
                    else f"{qty:,.4f}".rstrip("0").rstrip(".")
                )
            else:
                qty_str = "?"

            analysis = verdicts.get(pos.id)
            verdict_str = ""
            if analysis and analysis.verdict:
                _icons = {"intact": "🟢", "gemischt": "🟡", "gefaehrdet": "🔴"}
                icon = _icons.get(analysis.verdict, "")
                verdict_str = f" | thesis: {icon} {analysis.verdict}"
                if analysis.summary:
                    verdict_str += f" — {analysis.summary}"

            lines.append(
                f"- **{pos.ticker or pos.name}** ({pos.name}): "
                f"{qty_str} {pos.unit} × {current_str} = {value_str} "
                f"({weight} of portfolio) | "
                f"purchase: {purchase} | class: {pos.asset_class}"
                f"{verdict_str}"
            )

        if total_value > 0:
            lines.append(f"\n**Total portfolio value: €{total_value:,.0f}**")
        else:
            lines.append(
                "\n*No current price data available — refresh on Market Data page first.*"
            )

        return "\n".join(lines)
