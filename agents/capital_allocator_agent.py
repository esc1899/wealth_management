"""
Capital Allocator Agent — evaluates management quality as capital allocators.

Cloud-only (ClaudeProvider). Watchlist positions only — not scheduled.
Analyzes 3 dimensions: historical decisions, insider ownership, communication quality.

Verdict values:
  exzellent  — outstanding capital allocation (buybacks at right prices, value-accretive M&A)
  solide     — solid allocation, minor weaknesses, no material value destruction
  fragwürdig — recurring mistakes (expensive acquisitions, buybacks at highs, unclear guidance)
  destruktiv — management demonstrably destroys shareholder value

Storage: capital_allocator_sessions + capital_allocator_messages,
referenced from position_analyses (agent='capital_allocator', session_id).

Eligibility: ticker required (story not needed — management quality is public information).
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Tuple

from core.llm.claude import ClaudeProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.capital_allocator import CapitalAllocatorRepository
from core.storage.models import PublicPosition, CapitalAllocatorMessage
from agents.agent_language import response_language_with_fixed_codes, current_date_context

logger = logging.getLogger(__name__)

AGENT_NAME = "capital_allocator"
VALID_VERDICTS = {"exzellent", "solide", "fragwürdig", "destruktiv"}

# ------------------------------------------------------------------
# Tool
# ------------------------------------------------------------------

SUBMIT_CA_VERDICT_TOOL = {
    "name": "submit_ca_verdict",
    "description": "Submit the capital allocator quality verdict after completing the analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "position_id": {
                "type": "integer",
                "description": "The position ID being analyzed",
            },
            "verdict": {
                "type": "string",
                "enum": ["exzellent", "solide", "fragwürdig", "destruktiv"],
                "description": "Capital allocator quality verdict",
            },
            "summary": {
                "type": "string",
                "description": "One sentence: the single most important finding about management's capital allocation",
            },
            "analysis": {
                "type": "string",
                "description": "3-4 sentences: scorecard evidence across the 3 dimensions",
            },
        },
        "required": ["position_id", "verdict", "summary"],
    },
}

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """Du bist ein Capital Allocator Analyst. Prüfe das Management auf Qualität der Kapitalallokation.

Nutze web_search gezielt für diese 3 Dimensionen:

1. **Historische Entscheidungen**: Buybacks — zu welchen Kursniveaus? Waren sie günstig oder zu Höchstständen?
   M&A-Track-Record — welche Übernahmen gab es, zu welchen Preisen, wie war die Integration?
   Dividendenpolitik — konsistent erhöht, stabil, oder gekürzt?

2. **Insider-Ownership & Anreize**: Wie viel Aktien hält das Management? Options-lastig oder echte Aktien mit Haltefristen?
   Sind die Interessen mit Aktionären aligned?

3. **Kommunikation & Track-Record**: Guidance-Qualität — liefern sie was sie versprechen?
   Positive oder negative Überraschungen? Sind CEO-Statements substanziell oder Marketing-Blabla?

**Verdicts:**
- exzellent: Management allokiert Kapital überragend — Buybacks zu günstigen Preisen, M&A wertschaffend, klare konsistente Kommunikation, hohes Insider-Ownership
- solide: Solide Allokation mit kleineren Mängeln — kein Schaden, aber kein struktureller Alpha durch Management
- fragwürdig: Wiederkehrende Fehler — teure Übernahmen, Buybacks zu Höchstkursen, unklare oder enttäuschende Guidance
- destruktiv: Management vernichtet nachweislich Aktionärswert — klarer Grund zur Vorsicht

Kein Kauf-/Verkaufs-Rat. Nur Transparenz über Management-Qualität.
Für jede Position: submit_ca_verdict aufrufen mit position_id, verdict, summary und analysis."""


# ------------------------------------------------------------------
# Agent
# ------------------------------------------------------------------


class CapitalAllocatorAgent:
    """
    Cloud agent (Claude ☁️) — analyzes management capital allocation quality.
    Watchlist-only, on-demand. No scheduled batch jobs.
    """

    def __init__(
        self,
        llm: ClaudeProvider,
        analyses_repo: PositionAnalysesRepository,
        ca_repo: CapitalAllocatorRepository,
    ):
        self._llm = llm
        self._analyses_repo = analyses_repo
        self._ca_repo = ca_repo

    @property
    def model(self) -> str:
        return self._llm.model

    def get_messages(self, session_id: int) -> list[CapitalAllocatorMessage]:
        return self._ca_repo.get_messages(session_id)

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
        Analyse all eligible positions in parallel (up to 3 concurrent).
        Eligibility: position must have a ticker and an id.
        Returns list of (position_id, verdict, summary).
        """
        eligible = [p for p in positions if p.ticker and p.id is not None]
        if not eligible:
            return []

        self._llm.skill_context = skill_name
        self._llm.position_count = len(eligible)
        system = (
            current_date_context()
            + ANALYSIS_SYSTEM_PROMPT
            + "\n"
            + response_language_with_fixed_codes(language, ["exzellent", "solide", "fragwürdig", "destruktiv"])
        )
        if skill_prompt:
            system += f"\n\n## Analyse-Fokus\n{skill_prompt}"

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
        """Analyse a single position and persist results."""
        user_msg = self._format_position(pos)

        session = self._ca_repo.create_session(
            position_id=pos.id,
            ticker=pos.ticker,
            position_name=pos.name,
            skill_name=skill_name,
        )
        self._ca_repo.add_message(session.id, "user", user_msg)

        try:
            response = await self._llm.chat_with_tools(
                messages=[{"role": "user", "content": user_msg}],
                tools=[
                    {"type": "web_search_20250305", "name": "web_search", "max_uses": 1},
                    SUBMIT_CA_VERDICT_TOOL,
                ],
                system=system,
                max_tokens=4000,
            )
        except Exception as exc:
            logger.warning("capital_allocator: LLM error for %s: %s", pos.name, exc)
            return []

        parsed = [
            (
                str(c.input.get("position_id")),
                c.input.get("verdict", "").lower(),
                c.input.get("summary", ""),
                c.input.get("analysis", ""),
            )
            for c in response.tool_calls
            if c.name == "submit_ca_verdict"
            and c.input.get("verdict", "").lower() in VALID_VERDICTS
        ]
        if not parsed:
            logger.warning("capital_allocator: no verdict for position %d (%s)", pos.id or 0, pos.name)
            return []

        assistant_content = response.content.strip() or parsed[0][3]
        self._ca_repo.add_message(session.id, "assistant", assistant_content)

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

    def _format_position(self, pos: PublicPosition) -> str:
        lines = [
            f"Analysiere die Kapitalallokations-Qualität des Managements für diese Position.",
            f"",
            f"**Position ID:** {pos.id}",
            f"**Name:** {pos.name}",
            f"**Ticker:** {pos.ticker}",
        ]
        if pos.asset_class:
            lines.append(f"**Asset-Klasse:** {pos.asset_class}")
        if pos.isin:
            lines.append(f"**ISIN:** {pos.isin}")
        return "\n".join(lines)
