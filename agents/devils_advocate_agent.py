"""
Devils Advocate Agent — finds the strongest bear case against a watchlist position.

Cloud-only (ClaudeProvider). Watchlist positions only — not scheduled.
Attacks the investment thesis from all angles: short-seller reports, sector headwinds,
regulatory risks, competitive threats, management red flags.

Verdict values (robustness of the investment thesis):
  robust      — thesis holds; bear case is weak or well-known and priced in
  angreifbar  — notable risks identified; worth monitoring closely
  fragil      — multiple serious concerns; re-examine thesis
  kritisch    — strong counter-arguments; thesis may be fundamentally wrong

Storage: devils_advocate_sessions + devils_advocate_messages,
referenced from position_analyses (agent='devils_advocate', session_id).

Privacy note: sends position.name + position.story to cloud (Storychecker-exception-pattern).
Story is optional — agent runs without it but produces more targeted output with it.

Eligibility: ticker + id required. Story optional but improves quality.
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional, Tuple

from core.llm.claude import ClaudeProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.devils_advocate import DevilsAdvocateRepository
from core.storage.models import DevilsAdvocateMessage, PublicPosition
from agents.agent_language import response_language_with_fixed_codes, current_date_context

logger = logging.getLogger(__name__)

AGENT_NAME = "devils_advocate"
VALID_VERDICTS = {"robust", "angreifbar", "fragil", "kritisch"}

# ------------------------------------------------------------------
# Tool
# ------------------------------------------------------------------

SUBMIT_DA_VERDICT_TOOL = {
    "name": "submit_da_verdict",
    "description": "Submit the devil's advocate verdict after completing the bear-case analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "position_id": {
                "type": "integer",
                "description": "The position ID being analyzed",
            },
            "verdict": {
                "type": "string",
                "enum": ["robust", "angreifbar", "fragil", "kritisch"],
                "description": "Robustness of the investment thesis given the bear case found",
            },
            "summary": {
                "type": "string",
                "description": "One sentence: the single strongest counter-argument to the investment thesis",
            },
            "analysis": {
                "type": "string",
                "description": "3-4 sentences: the top bear-case arguments found, specific and evidence-based",
            },
        },
        "required": ["position_id", "verdict", "summary"],
    },
}

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """Du bist ein kritischer Gegenanalyst — ein professioneller Devil's Advocate.
Deine Aufgabe: Finde die stärksten Argumente GEGEN dieses Investment.

Nutze web_search gezielt für:

1. **Bären-Argumente**: Short-Seller-Reports, kritische Analysten-Einschätzungen, Leerverkäufer-Thesen.
   Was sagen die, die gegen dieses Unternehmen wetten?

2. **Strukturelle Risiken**: Wettbewerber-Angriffe, Disruption durch neue Technologien oder Geschäftsmodelle.
   Regulatory-Risiken, ESG-Probleme, Kartellverfahren. Sektor-Gegenwind.

3. **Bewertungs- und Finanzrisiken**: Ist die Aktie zu teuer? Zu viel Schulden? Freier Cashflow rückläufig?
   Guidance-Enttäuschungen in der Vergangenheit?

Wenn eine Investment-These vorliegt: Greife spezifisch DIESE These an. Was könnten die Autoren dieser These übersehen haben?
Wenn keine These vorliegt: Führe eine allgemeine Due-Diligence-Gegenanalyse durch.

**Verdicts (Robustheit der Investment-These):**
- robust: Die These hält stand — Gegenargumente sind schwach, bekannt oder bereits eingepreist
- angreifbar: Nennenswerte Risiken identifiziert — These ist vertretbar, aber eng beobachten
- fragil: Mehrere ernsthafte Probleme — These ruht auf unsicheren Annahmen, überdenken
- kritisch: Starke Gegenbeweise — These könnte fundamental falsch sein, grundsätzliche Revision nötig

Kein Kauf-/Verkaufs-Rat. Nur ehrliche Gegenanalyse.
Für jede Position: submit_da_verdict aufrufen mit position_id, verdict, summary und analysis."""


# ------------------------------------------------------------------
# Agent
# ------------------------------------------------------------------


def _extract_parsed(response) -> list:
    return [
        (
            str(c.input.get("position_id")),
            c.input.get("verdict", "").lower(),
            c.input.get("summary", ""),
            c.input.get("analysis", ""),
        )
        for c in response.tool_calls
        if c.name == "submit_da_verdict"
        and c.input.get("verdict", "").lower() in VALID_VERDICTS
    ]


class DevilsAdvocateAgent:
    """
    Cloud agent (Claude ☁️) — finds the bear case for watchlist positions.
    Privacy note: sends position.name + story to cloud (Storychecker-exception-pattern).
    Watchlist-only, on-demand. Not scheduled.
    """

    def __init__(
        self,
        llm: ClaudeProvider,
        analyses_repo: PositionAnalysesRepository,
        da_repo: DevilsAdvocateRepository,
    ):
        self._llm = llm
        self._analyses_repo = analyses_repo
        self._da_repo = da_repo

    @property
    def model(self) -> str:
        return self._llm.model

    def get_messages(self, session_id: int) -> list[DevilsAdvocateMessage]:
        return self._da_repo.get_messages(session_id)

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
            + response_language_with_fixed_codes(language, list(VALID_VERDICTS))
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

        session = self._da_repo.create_session(
            position_id=pos.id,
            ticker=pos.ticker,
            position_name=pos.name,
            skill_name=skill_name,
        )
        self._da_repo.add_message(session.id, "user", user_msg)

        try:
            response = await self._llm.chat_with_tools(
                messages=[{"role": "user", "content": user_msg}],
                tools=[
                    {"type": "web_search_20250305", "name": "web_search", "max_uses": 2},
                    SUBMIT_DA_VERDICT_TOOL,
                ],
                system=system,
                max_tokens=4000,
            )
        except Exception as exc:
            logger.warning("devils_advocate: LLM error for %s: %s", pos.name, exc)
            return []

        parsed = _extract_parsed(response)

        # Fallback: if LLM wrote analysis but didn't call the tool, force a second call
        if not parsed and response.content.strip():
            try:
                analysis_so_far = response.content.strip()
                followup_msg = (
                    f"Du hast diese Analyse verfasst:\n\n{analysis_so_far}\n\n"
                    f"Rufe jetzt submit_da_verdict auf. Position ID: {pos.id}"
                )
                response2 = await self._llm.chat_with_tools(
                    messages=[
                        {"role": "user", "content": user_msg},
                        {"role": "assistant", "content": analysis_so_far},
                        {"role": "user", "content": followup_msg},
                    ],
                    tools=[SUBMIT_DA_VERDICT_TOOL],
                    system=system,
                    max_tokens=1000,
                    tool_choice={"type": "tool", "name": "submit_da_verdict"},
                )
                parsed = _extract_parsed(response2)
                if parsed:
                    response = response2
            except Exception as exc:
                logger.warning("devils_advocate: fallback call failed for %s: %s", pos.name, exc)

        if not parsed:
            logger.warning("devils_advocate: no verdict for position %d (%s)", pos.id or 0, pos.name)
            return []

        # Store the analysis from the tool call (not the LLM's interim thinking text)
        analysis_text = parsed[0][3] if parsed[0][3] else response.content.strip()
        self._da_repo.add_message(session.id, "assistant", analysis_text)

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
            "Analysiere diese Watchlist-Position aus der Perspektive eines kritischen Gegenanalysten.",
            "",
            f"**Position ID:** {pos.id}",
            f"**Name:** {pos.name}",
            f"**Ticker:** {pos.ticker}",
        ]
        if pos.asset_class:
            lines.append(f"**Asset-Klasse:** {pos.asset_class}")
        if pos.isin:
            lines.append(f"**ISIN:** {pos.isin}")
        if pos.story:
            lines.append("")
            lines.append("**Investment-These (greife diese spezifisch an):**")
            lines.append(pos.story)
        return "\n".join(lines)
