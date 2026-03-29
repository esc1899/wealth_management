"""
Rebalance Agent — portfolio rebalancing analysis using local Ollama LLM.
Private 🔒 — all portfolio data stays local, nothing is sent to external APIs.

Flow per analyze() call:
  1. Load all portfolio positions from DB
  2. Fetch current market prices from DB
  3. Build a structured portfolio snapshot (positions, values, weights)
  4. Send to local LLM with the selected skill strategy
  5. Return the analysis as a markdown string
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from core.llm.base import Message, Role
from core.llm.local import OllamaProvider
from core.storage.market_data import MarketDataRepository
from core.storage.models import Position
from core.storage.positions import PositionsRepository

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
    Stateless agent: each call to analyze() is independent.
    Uses local Ollama LLM (private 🔒).
    """

    def __init__(
        self,
        positions_repo: PositionsRepository,
        market_repo: MarketDataRepository,
        llm: OllamaProvider,
    ):
        self._positions = positions_repo
        self._market = market_repo
        self._llm = llm

    async def analyze(self, skill_name: str, skill_prompt: str) -> str:
        """
        Build a portfolio snapshot and run a rebalancing analysis.

        Args:
            skill_name:   Display name of the strategy (for context)
            skill_prompt: The strategy prompt that defines how to analyze
        """
        portfolio = self._positions.get_portfolio()
        if not portfolio:
            return "Portfolio is empty. Add positions in Portfolio Chat first."

        portfolio_text = self._build_portfolio_context(portfolio)

        system = (
            SYSTEM_PROMPT.format(today=date.today().isoformat())
            + f"\n\n## Strategy: {skill_name}\n{skill_prompt}"
        )
        messages = [
            Message(role=Role.SYSTEM, content=system),
            Message(
                role=Role.USER,
                content=(
                    "Please analyze my portfolio and provide rebalancing "
                    f"recommendations according to the strategy.\n\n{portfolio_text}"
                ),
            ),
        ]

        return await self._llm.chat(messages, max_tokens=2048)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_portfolio_context(self, positions: list[Position]) -> str:
        """Format portfolio positions as readable context for the LLM."""
        # Compute values and total
        rows: list[tuple[Position, Optional[float], Optional[float]]] = []
        total_value = 0.0

        for pos in positions:
            price_record = self._market.get_price(pos.ticker) if pos.ticker else None
            value: Optional[float] = None
            if pos.quantity is not None and price_record is not None:
                value = pos.quantity * price_record.price_eur
                total_value += value
            rows.append((pos, price_record.price_eur if price_record else None, value))

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

            lines.append(
                f"- **{pos.ticker or pos.name}** ({pos.name}): "
                f"{qty_str} {pos.unit} × {current_str} = {value_str} "
                f"({weight} of portfolio) | "
                f"purchase: {purchase} | class: {pos.asset_class}"
            )

        if total_value > 0:
            lines.append(f"\n**Total portfolio value: €{total_value:,.0f}**")
        else:
            lines.append("\n*No current price data available — refresh on Market Data page first.*")

        return "\n".join(lines)
