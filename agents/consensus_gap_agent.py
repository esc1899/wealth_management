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

Storage: consensus_gap_sessions + consensus_gap_messages (like SC/FA pattern),
referenced from position_analyses (agent='consensus_gap', session_id).

Flow:
  1. For each portfolio position with a story, create a session
  2. One Claude call per position with web_search tool
  3. Parse verdicts from structured output
  4. Store full LLM response as assistant message, persist in position_analyses with session_id
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

from core.llm.claude import ClaudeProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.consensus_gap import ConsensusGapRepository
from core.storage.models import PublicPosition, ConsensusGapMessage
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
        cg_repo: ConsensusGapRepository,
    ):
        self._llm = llm
        self._analyses_repo = analyses_repo
        self._cg_repo = cg_repo

    @property
    def model(self) -> str:
        """Return the LLM model name."""
        return self._llm.model

    def get_messages(self, session_id: int) -> list[ConsensusGapMessage]:
        """Retrieve all messages from a consensus gap session."""
        return self._cg_repo.get_messages(session_id)

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
        Analyse all positions with stories in parallel (up to 3 concurrent).
        Returns list of (position_id, verdict, summary).
        Verdicts are also persisted in position_analyses.
        """
        eligible = [p for p in positions if p.story and p.id is not None]
        if not eligible:
            return []

        self._llm.skill_context = skill_name
        self._llm.position_count = len(eligible)
        system = ANALYSIS_SYSTEM_PROMPT + "\n" + response_language_with_fixed_codes(language, ["wächst", "stabil", "schließt", "eingeholt"])
        system += f"\n\n## Strategie-Skill\n{skill_prompt}"

        semaphore = asyncio.Semaphore(3)

        async def _analyze_one(pos: PublicPosition) -> List[Tuple[int, str, str]]:
            async with semaphore:
                return await self._analyze_position(pos, system, skill_name)

        raw = await asyncio.gather(*[_analyze_one(pos) for pos in eligible])
        return [item for sublist in raw for item in sublist]

    async def _analyze_position(
        self,
        pos: PublicPosition,
        system: str,
        skill_name: str,
    ) -> List[Tuple[int, str, str]]:
        """Analyse a single position and persist results. Returns list of (position_id, verdict, summary)."""
        positions_text = self._format_positions([pos])
        user_msg = f"Analysiere diese Portfolio-Position auf ihre Konsens-Lücke.\n\n{positions_text}"

        session = self._cg_repo.create_session(
            position_id=pos.id,
            ticker=pos.ticker,
            position_name=pos.name,
            skill_name=skill_name,
        )
        self._cg_repo.add_message(session.id, "user", user_msg)

        try:
            response = await self._llm.chat_with_tools(
                messages=[{"role": "user", "content": user_msg}],
                tools=[
                    {"type": "web_search_20250305", "name": "web_search"},
                    SUBMIT_VERDICT_TOOL,
                ],
                system=system,
                max_tokens=2500,
            )
        except Exception as exc:
            logger.warning("consensus_gap: LLM error for %s: %s", pos.name, exc)
            return []

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
            return []

        assistant_content = response.content.strip() or parsed[0][3]
        self._cg_repo.add_message(session.id, "assistant", assistant_content)

        results = []
        for pos_id_str, verdict, summary, _ in parsed:
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
                session_id=session.id,
            )
            results.append((pos_id, verdict, summary))
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
