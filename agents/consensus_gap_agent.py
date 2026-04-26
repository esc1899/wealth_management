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
from core.storage.models import PublicPosition
from agents.agent_language import response_language_with_fixed_codes

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
        positions: List[PublicPosition],
        skill_name: str,
        skill_prompt: str,
        language: str = "de",
    ) -> List[Tuple[int, str, str]]:
        """
        Analyse all positions with stories. Returns list of (position_id, verdict, summary).
        Verdicts are also persisted in position_analyses.

        Args:
            positions: List of positions to analyze
            skill_name: Name of the configured skill
            skill_prompt: Custom skill prompt
            language: Language code for LLM output (default: "de")
        """
        eligible = [p for p in positions if p.story and p.id is not None]
        if not eligible:
            return []

        self._llm.skill_context = skill_name
        self._llm.position_count = len(eligible)
        system = ANALYSIS_SYSTEM_PROMPT + "\n" + response_language_with_fixed_codes(language, ["wächst", "stabil", "schließt", "eingeholt"])
        system += f"\n\n## Strategie-Skill\n{skill_prompt}"
        results: List[Tuple[int, str, str]] = []

        # Process 1 position at a time — ensures Claude completes verdict submission
        for idx, pos in enumerate(eligible):
            positions_text = self._format_positions([pos])
            user_msg = (
                f"Analysiere diese Portfolio-Position auf ihre Konsens-Lücke.\n\n{positions_text}"
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
            # Extract verdict from tool calls
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
                logger.warning("consensus_gap: no verdict for position %d (%s)", pos.id or 0, pos.name)
            else:
                # Persist immediately after each position
                for pos_id_str, verdict, summary, analysis in parsed:
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
                    results.append((pos_id, verdict, summary))

            # Pause between positions to avoid rate limit
            if idx < len(eligible) - 1:
                await asyncio.sleep(1)

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_positions(self, positions: List[PublicPosition]) -> str:
        lines = []
        for p in positions:
            lines.append(f"### Position ID: {p.id}")
            lines.append(f"**Name:** {p.name}")
            if p.ticker:
                lines.append(f"**Ticker:** {p.ticker}")
            lines.append(f"**Asset-Klasse:** {p.asset_class}")
            lines.append(f"**Investment-These (Story):**\n{p.story}")
            lines.append("")
        return "\n".join(lines)
