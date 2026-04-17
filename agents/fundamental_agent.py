"""
FundamentalAgent — estimates fair value and over/under-valuation of portfolio positions.

Uses Claude + web search to find current valuation multiples (P/E, P/B, EV/EBITDA),
compare them to sector averages, and produce a simple DCF-based fair value estimate.

Verdict values:
  unterbewertet  — trading significantly below fair value → 🟢
  fair           — trading near fair value → 🟡
  überbewertet   — trading above fair value → 🔴
  unbekannt      — insufficient data for reliable valuation

Storage: reuses position_analyses table (agent='fundamental').
"""

from __future__ import annotations
import logging


import asyncio
import re
from typing import List, Optional, Tuple

from core.currency import symbol
from core.llm.claude import ClaudeProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.models import Position


logger = logging.getLogger(__name__)
AGENT_NAME = "fundamental"

VALID_VERDICTS = {"unterbewertet", "fair", "überbewertet", "unbekannt"}

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """Fundamental equity analyst. Assess: undervalued, fairly valued, or overvalued.

STRICT RULES — token budget is limited:
- Exactly 1 web_search per position. No more.
- Search only for: current P/E, analyst price target, and current price.
- Do NOT retrieve full articles. Use the most concise search query possible.

Verdicts:
- unterbewertet: >20% discount to fair value
- fair: within ±15% of fair value
- überbewertet: >20% premium to fair value
- unbekannt: insufficient data

Output EXACTLY (machine-parsed):
POSITION: [ID]
VERDICT: [unterbewertet|fair|überbewertet|unbekannt]
FAIR_VALUE_EUR: [EUR per share, or N/A]
UPSIDE_PCT: [e.g. +24% or -18%, or N/A]
SUMMARY: [One sentence with key metric]
ANALYSIS:
[2 sentences max: key numbers found, verdict rationale]
---

Apply valuation strategy skill below."""

POSITION_BLOCK_PATTERN = re.compile(
    r"\*{0,2}POSITION:\*{0,2}\s*(\d+).*?[\n\r]+"
    r".*?\*{0,2}VERDICT:\*{0,2}\s*(unterbewertet|fair|überbewertet|unbekannt).*?[\n\r]+"
    r".*?\*{0,2}FAIR_VALUE_EUR:\*{0,2}\s*(.+?)[\n\r]+"
    r".*?\*{0,2}UPSIDE_PCT:\*{0,2}\s*(.+?)[\n\r]+"
    r".*?\*{0,2}SUMMARY:\*{0,2}\s*(.+?)[\n\r]+"
    r"[\s\S]*?\*{0,2}ANALYSIS:\*{0,2}\s*[\n\r]+([\s\S]*?)(?=\n---|\Z)",
    re.IGNORECASE,
)


class FundamentalAgent:
    """
    Cloud agent (Claude ☁️) — fundamental valuation of portfolio positions.
    Stores verdicts in position_analyses (agent='fundamental').
    """

    def __init__(
        self,
        llm: ClaudeProvider,
        analyses_repo: PositionAnalysesRepository,
    ):
        self._llm = llm
        self._analyses_repo = analyses_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_portfolio(
        self,
        positions: List[Position],
        skill_name: str,
        skill_prompt: str,
    ) -> List[Tuple[int, str, str]]:
        """
        Analyse all eligible positions. Returns list of (position_id, verdict, summary).
        Verdicts are persisted in position_analyses.
        """
        # Only positions with tickers are fundamentally analysable
        all_with_ticker = [p for p in positions if p.ticker and p.id is not None]
        if not all_with_ticker:
            return []

        # Auto-assign "unbekannt" for asset classes Claude cannot meaningfully value
        # (bond funds, precious metals, crypto — no DCF/P/E applicable)
        _AUTO_UNBEKANNT = {"Rentenfonds", "Edelmetall", "Kryptowährung"}
        auto_skip = [p for p in all_with_ticker if p.asset_class in _AUTO_UNBEKANNT]
        eligible  = [p for p in all_with_ticker if p.asset_class not in _AUTO_UNBEKANNT]

        output: List[Tuple[int, str, str]] = []

        for pos in auto_skip:
            summary = f"Automatisch als unbekannt klassifiziert — {pos.asset_class} ist nicht klassisch bewertbar (kein DCF/P/E anwendbar)."
            self._analyses_repo.save(
                position_id=pos.id,
                agent=AGENT_NAME,
                skill_name=skill_name,
                verdict="unbekannt",
                summary=summary,
            )
            output.append((pos.id, "unbekannt", summary))

        if not eligible:
            return output

        self._llm.skill_context = skill_name
        self._llm.position_count = len(eligible)  # Track how many positions in this batch
        system = ANALYSIS_SYSTEM_PROMPT + f"\n\n## Bewertungs-Skill\n{skill_prompt}"
        all_results: List[Tuple[str, str, str, str, str, str]] = []

        # Process one position at a time — fundamental analysis is very token-heavy
        batch_size = 1
        for i in range(0, len(eligible), batch_size):
            batch = eligible[i: i + batch_size]
            positions_text = self._format_positions(batch)
            user_msg = (
                f"Analysiere die Fundamentalbewertung dieser Position.\n\n{positions_text}"
            )
            response = await self._llm.chat_with_tools(
                messages=[{"role": "user", "content": user_msg}],
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                system=system,
                max_tokens=1800,
            )
            all_results.extend(self._parse_verdicts(response.content or ""))

            if i + batch_size < len(eligible):
                await asyncio.sleep(5)

        # Persist verdicts; embed fair value + upside in summary
        for pos_id_str, verdict, fair_value, upside, summary, analysis in all_results:
            if verdict not in VALID_VERDICTS:
                continue
            try:
                pos_id = int(pos_id_str)
            except ValueError:
                continue

            # Enrich summary with fair value / upside if available
            rich_summary = summary
            extras = []
            if fair_value and fair_value.upper() != "N/A":
                extras.append(f"Fair Value: {fair_value} {symbol()}")
            if upside and upside.upper() != "N/A":
                extras.append(f"Upside: {upside}")
            if extras:
                rich_summary = f"{summary} ({', '.join(extras)})"

            self._analyses_repo.save(
                position_id=pos_id,
                agent=AGENT_NAME,
                skill_name=skill_name,
                verdict=verdict,
                summary=rich_summary,
            )
            output.append((pos_id, verdict, rich_summary))

        return output

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_positions(self, positions: List[Position]) -> str:
        lines = []
        for p in positions:
            lines.append(f"### Position ID: {p.id}")
            lines.append(f"**Name:** {p.name}")
            lines.append(f"**Ticker:** {p.ticker}")
            lines.append(f"**Asset-Klasse:** {p.asset_class}")
            if p.anlageart:
                lines.append(f"**Anlage-Art:** {p.anlageart}")
            if p.purchase_price:
                lines.append(f"**Kaufpreis:** {p.purchase_price:.2f} {symbol()}")
            if p.purchase_date:
                lines.append(f"**Kaufdatum:** {p.purchase_date.isoformat()}")
            if p.story:
                lines.append(f"**Investment-These:** {p.story}")
            lines.append("")
        return "\n".join(lines)

    def _parse_verdicts(
        self, text: str
    ) -> List[Tuple[str, str, str, str, str, str]]:
        """Parse structured verdict blocks: (pos_id, verdict, fair_value, upside, summary, analysis)."""
        results = []
        for m in POSITION_BLOCK_PATTERN.finditer(text):
            results.append((
                m.group(1).strip(),   # pos_id
                m.group(2).strip().lower(),  # verdict
                m.group(3).strip(),   # fair_value_eur
                m.group(4).strip(),   # upside_pct
                m.group(5).strip(),   # summary
                m.group(6).strip(),   # analysis
            ))
        return results
