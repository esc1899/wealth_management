"""
ConsensusGapAgent — measures the gap between the user's investment thesis and market consensus.

Claude's Strategie Säule 2: Für jede Portfolio-Position mit Story wird geprüft:
  - Was ist der aktuelle Analyst-Konsens?
  - Stimmt die operative Realität mit der User-These überein?
  - Wächst die Konsens-Lücke (Markt liegt immer noch falsch) oder schließt sie sich?

Verdict values:
  wächst     — gap growing: market increasingly wrong in user's favor → 🟢 strong hold/add
  stabil     — gap stable: thesis intact, no major consensus shift → 🟡 hold
  schließt   — gap closing: market catching up → 🟡 consider trimming
  eingeholt  — consensus has caught up: thesis fully priced in → 🔴 review / consider selling

Storage: reuses position_analyses table (agent='consensus_gap').

Flow:
  1. For each portfolio position with a story, build a prompt
  2. One Claude call per batch (passes all positions at once)
  3. Parse verdicts from structured output
  4. Store in position_analyses
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

from core.llm.claude import ClaudeProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.models import Position

AGENT_NAME = "consensus_gap"

VALID_VERDICTS = {"wächst", "stabil", "schließt", "eingeholt"}

# Tool for structured verdict submission
SUBMIT_VERDICT_TOOL = {
    "name": "submit_consensus_verdict",
    "description": "Submit the consensus gap verdict for a portfolio position.",
    "input_schema": {
        "type": "object",
        "properties": {
            "position_id": {
                "type": "integer",
                "description": "The position ID to analyze",
            },
            "verdict": {
                "type": "string",
                "enum": ["wächst", "stabil", "schließt", "eingeholt"],
                "description": "The consensus gap verdict",
            },
            "summary": {
                "type": "string",
                "description": "One sentence: consensus vs. thesis",
            },
            "analysis": {
                "type": "string",
                "description": "2 sentences max: consensus target/rating and supporting data",
            },
        },
        "required": ["position_id", "verdict", "summary"],
    },
}

# ------------------------------------------------------------------
# System prompts
# ------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """Konsens-Lücken-Analyst. Für jede Position: Ist der Markt noch falsch, oder hat er die These eingeholt?

Use max 1 web_search per position. Focus: current analyst consensus price target + rating, one recent data point.

Verdicts:
- wächst: gap growing — market increasingly wrong in investor's favor
- stabil: gap stable — thesis intact, no major shift
- schließt: gap closing — market catching up
- eingeholt: gap gone — thesis fully priced in

Für jede Position: Rufe submit_consensus_verdict auf mit position_id (die Zahl), verdict, summary und analysis.
Rufe es einmal pro Position auf — kein Freitext-Output nötig.

Apply skill strategy below."""


class ConsensusGapAgent:
    """
    Cloud agent (Claude ☁️) — analyses portfolio positions for consensus gaps.
    Stores verdicts in position_analyses (agent='consensus_gap').
    """

    def __init__(
        self,
        llm: ClaudeProvider,
        analyses_repo: PositionAnalysesRepository,
    ):
        self._llm = llm
        self._analyses_repo = analyses_repo

    @property
    def model(self) -> str:
        """Return the LLM model name."""
        return self._llm.model

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
        Analyse all positions with stories. Returns list of (position_id, verdict, summary).
        Verdicts are also persisted in position_analyses.
        """
        eligible = [p for p in positions if p.story and p.id is not None]
        if not eligible:
            return []

        self._llm.skill_context = skill_name
        self._llm.position_count = len(eligible)  # Track how many positions in this batch
        system = ANALYSIS_SYSTEM_PROMPT + f"\n\n## Strategie-Skill\n{skill_prompt}"
        all_results: List[Tuple[str, str, str, str]] = []

        # Process in batches of 2 to stay within rate limits
        batch_size = 2
        for i in range(0, len(eligible), batch_size):
            batch = eligible[i: i + batch_size]
            positions_text = self._format_positions(batch)
            user_msg = (
                f"Analysiere diese Portfolio-Positionen auf ihre Konsens-Lücke.\n\n{positions_text}"
            )
            response = await self._llm.chat_with_tools(
                messages=[{"role": "user", "content": user_msg}],
                tools=[
                    {"type": "web_search_20250305", "name": "web_search"},
                    SUBMIT_VERDICT_TOOL,
                ],
                system=system,
                max_tokens=2500,
            )
            # Extract verdicts from tool calls
            parsed = [
                (
                    str(c.input.get("position_id")),
                    c.input.get("verdict", "").lower(),
                    c.input.get("summary", ""),
                    c.input.get("analysis", ""),
                )
                for c in response.tool_calls
                if c.name == "submit_consensus_verdict"
                and c.input.get("verdict", "").lower() in VALID_VERDICTS
            ]
            if not parsed:
                logger.warning(
                    "consensus_gap: no submit_consensus_verdict calls in batch %d", i
                )
            all_results.extend(parsed)

            # Pause between batches to avoid rate limit
            if i + batch_size < len(eligible):
                await asyncio.sleep(12)

        # Persist all found verdicts
        for pos_id_str, verdict, summary, analysis in all_results:
            try:
                pos_id = int(pos_id_str)
            except ValueError:
                continue
            if verdict not in VALID_VERDICTS:
                continue
            self._analyses_repo.save(
                position_id=pos_id,
                agent=AGENT_NAME,
                skill_name=skill_name,
                verdict=verdict,
                summary=summary,
            )

        return [(int(r[0]), r[1], r[2]) for r in all_results if r[1] in VALID_VERDICTS]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_positions(self, positions: List[Position]) -> str:
        lines = []
        for p in positions:
            lines.append(f"### Position ID: {p.id}")
            lines.append(f"**Name:** {p.name}")
            if p.ticker:
                lines.append(f"**Ticker:** {p.ticker}")
            lines.append(f"**Asset-Klasse:** {p.asset_class}")
            if p.purchase_date:
                lines.append(f"**Kaufdatum:** {p.purchase_date.isoformat()}")
            lines.append(f"**Investment-These (Story):**\n{p.story}")
            lines.append("")
        return "\n".join(lines)
