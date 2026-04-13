"""
Investment Kompass Agent — analyzes investment questions with full portfolio context.

Local-only (OllamaProvider). One-shot call — no sessions.
Builds context from implicit agent hierarchy:
  Ebene 0: positions + watchlist + current_prices + portfolio_story
  Ebene 1: storychecker/fundamental/consensus_gap verdicts
  Ebene 2: portfolio_story analysis + watchlist_checker results
Outputs: investment analysis + lineage metadata.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.llm.base import Message, Role
from core.llm.local import OllamaProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.models import Position
from core.storage.portfolio_story import PortfolioStoryRepository

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Output models
# ------------------------------------------------------------------


@dataclass
class InvestmentAnalysis:
    """Result of an investment analysis."""
    response: str
    lineage: dict  # metadata about context sources


# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """Du bist ein fokussierter Investment-Analyst.

Deine Aufgabe: Beantwortete ausschließlich Investment-relevante Fragen basierend auf
dem bereitgestellten Portfolio-Kontext.

Regeln:
- Sei analytisch und direkt. Keine Werbesprache.
- Nutze die verfügbaren Daten (Portfolio, Story, Verdicts, Watchlist).
- Gib keine allgemeinen Finanzratschläge, sondern Portfolio-spezifische Analysen.
- Andere Themen lehnst du höflich aber bestimmt ab: "Das passt nicht zu Portfolio-Analysen."

Ton: Rational, respektlos gegenüber Mode-Thesen, hilfreich für ernsthafte Investoren.
Antworte auf Deutsch."""


# ------------------------------------------------------------------
# Agent
# ------------------------------------------------------------------


class InvestmentCompassAgent:
    """
    Local agent that analyzes investment questions with full portfolio context.
    One-shot call — builds context from implicit agent hierarchy.
    """

    def __init__(
        self,
        positions_repo,
        market_repo,
        analyses_repo: PositionAnalysesRepository,
        portfolio_story_repo: PortfolioStoryRepository,
        llm: OllamaProvider,
        skills_repo=None,
    ) -> None:
        self._positions = positions_repo
        self._market = market_repo
        self._analyses = analyses_repo
        self._portfolio_story = portfolio_story_repo
        self._llm = llm
        self._skills = skills_repo

    @property
    def model(self) -> str:
        return self._llm.model

    async def analyze(
        self,
        user_query: str,
        skill_name: Optional[str] = None,
        skill_prompt: Optional[str] = None,
    ) -> InvestmentAnalysis:
        """
        Analyze an investment question with full context.
        Returns analysis + lineage metadata.

        Phase 1: Validates query against portfolio story FIRST.
        Only proceeds if usecase is valid and compatible with story.

        Phase 2: Builds usecase-specific context and executes analysis.
        """
        self._llm.skill_context = skill_name or "investment_compass"

        # Phase 1: Classify and validate query against portfolio story
        portfolio_story = self._portfolio_story.get_current() if self._portfolio_story else None
        usecase, is_valid, rejection_reason = self._classify_and_validate(
            user_query=user_query,
            portfolio_story=portfolio_story
        )

        if not is_valid:
            return InvestmentAnalysis(
                response=f"⚠️ **Anfrage passt nicht zu Portfolio-Analysen**\n\n{rejection_reason}",
                lineage={
                    "rejected": True,
                    "rejection_reason": rejection_reason,
                    "usecase_attempted": usecase,
                }
            )

        # Phase 2: Execute usecase-specific analysis (if valid)
        return await self._execute_usecase(
            usecase=usecase,
            user_query=user_query,
            skill_name=skill_name,
            skill_prompt=skill_prompt,
            portfolio_story=portfolio_story,
        )

    async def _execute_usecase(
        self,
        usecase: str,
        user_query: str,
        skill_name: Optional[str],
        skill_prompt: Optional[str],
        portfolio_story: Optional[object],
    ) -> InvestmentAnalysis:
        """
        Phase 2: Execute usecase-specific analysis.

        - Builds context filtered for the usecase
        - Injects skill only if relevant for this usecase
        - Uses usecase-specific system prompt
        - Returns analysis + lineage metadata
        """
        # Build usecase-specific context with lineage tracking
        context, lineage = self._build_context_for_usecase(usecase, portfolio_story)
        lineage["usecase"] = usecase

        # Determine if skill should be used for this usecase
        use_skill = self._should_use_skill_for_usecase(usecase)
        skill_context = ""
        if use_skill and skill_name:
            # Add skill to lineage tracking
            lineage["skills_used"].append(skill_name)
            # Include skill prompt in context if available
            if skill_prompt:
                skill_context = f"\n\n## Strategie: {skill_name}\n{skill_prompt}"

        # Get usecase-specific system prompt
        system_prompt = self._get_usecase_prompt(usecase)
        system_prompt += f"\n\n## Portfolio-Kontext\n{context}"
        if skill_context:
            system_prompt += skill_context

        # LLM call
        full_prompt = f"{system_prompt}\n\n{user_query}"
        messages = [
            Message(role=Role.USER, content=full_prompt)
        ]

        full_response = await self._llm.chat(messages)

        return InvestmentAnalysis(
            response=full_response,
            lineage=lineage,
        )

    def _should_use_skill_for_usecase(self, usecase: str) -> bool:
        """
        Determine if a skill should be injected for this usecase.

        Skills are optional and modulate HOW analysis is performed:
        - ALLOCATION: ✓ Yes (Value/Growth/Income modulate position selection)
        - REBALANCING: ✓ Yes (Conservative/Aggressive modulate weight targets)
        - ANALYSIS: ✓ Yes (e.g., "Buffett-style analysis" looks for value/moats/robustness)
        - WITHDRAWAL: ✗ No (logic is fixed: liquidity > capital preservation)

        Only WITHDRAWAL is blocked since withdrawal logic is predetermined.
        """
        return usecase != "WITHDRAWAL"

    def _get_usecase_prompt(self, usecase: str) -> str:
        """
        Get usecase-specific system prompt.
        Each usecase has different instructions for the LLM.
        """
        prompts = {
            "ALLOCATION": """Du bist ein Allokations-Berater. Der Nutzer hat neue Mittel zu investieren.

Beachte:
- Die Portfolio Story gibt die strategische Richtung
- Aktuelle Gewichtung aus Portfolio-Kontext
- Welche Positionen sind untergewichtet vs. Portfolio Story?
- Passt die neue Allokation zur Story und aktuellen Zielen?

Antworte konkret mit Positionen (oder Asset-Klassen), nicht mit Allgemeinplätzen.
Antworte auf Deutsch.""",

            "REBALANCING": """Du bist ein Rebalancing-Analyst. Der Nutzer überlegt sein Portfolio umzustrukturieren.

Beachte:
- Die Portfolio Story ist der "Kompass" — in welche Richtung weicht das Portfolio ab?
- Sind Positionen über/untergewichtet vs. Story und Analyst-Verdicts?
- Welche Positionen stärken die Story, welche schwächen sie?
- Josef's Regel als Stabilisierungs-Richtlinie (1/3 Aktien, 1/3 Renten/Geld, 1/3 Rohstoffe+Immobilien)

Antworte konkret mit Gewichte-Vorschlägen oder Positionen.
Antworte auf Deutsch.""",

            "WITHDRAWAL": """Du bist ein Liquiditäts-Berater. Der Nutzer muss Geld abheben.

Beachte:
- Liquidität erhalten: Renten und laufende Erträge vor Aktien
- Story-Fit: Welche Positionen kann man gehen, ohne die Story zu brechen?
- Unter der Withdrawal-Logik: strukturiert, nicht emotional

Antworte konkret mit Positions-Vorschlägen zum Verkauf.
Antworte auf Deutsch.""",

            "ANALYSIS": """Du analysierst die Robustheit des Portfolios gegen ein Szenario.

Beachte:
- Die Portfolio Story definiert die Ziele (z.B. "stabiles Einkommen in 5 Jahren")
- Wie robust ist das Portfolio gegen Inflation/Rezession/Zinsanstieg/Marktvolatilität?
- Fehlen Hedges oder Puffer?
- Josef's Regel als Stabilitäts-Richtlinie

Antworte mit Robustheit-Bewertung und konkreten Schwachstellen.
Antworte auf Deutsch.""",
        }

        return prompts.get(usecase, BASE_SYSTEM_PROMPT)

    def _build_context_for_usecase(
        self,
        usecase: str,
        portfolio_story: Optional[object],
    ) -> tuple[str, dict]:
        """
        Build context filtered for the specific usecase.

        Different usecases need different context:
        - ALLOCATION: "Welche Positionen sind untergewichtet?"
        - REBALANCING: "Wo sind Abweichungen vs. Story?"
        - WITHDRAWAL: "Was ist liquid und passt zu Story?"
        - ANALYSIS: "Stabilität vs. Story-Ziel?"
        """
        context_parts = []
        lineage = {
            "agents_used": [],
            "skills_used": [],
            "model": self.model,
            "timestamp": datetime.now().isoformat(),
        }

        # Always include portfolio snapshot
        positions = self._positions.get_portfolio()
        watchlist = self._positions.get_watchlist()

        portfolio_text = _build_portfolio_snapshot(positions, self._market)
        context_parts.append("## Portfolio (aktuell)")
        context_parts.append(portfolio_text)
        lineage["agents_used"].append("portfolio_data")

        # Include watchlist if available
        if watchlist:
            watchlist_text = _build_watchlist_summary(watchlist)
            context_parts.append("")
            context_parts.append("## Watchlist")
            context_parts.append(watchlist_text)

        # Always include portfolio story
        if portfolio_story:
            context_parts.append("")
            context_parts.append("## Portfolio Story")
            context_parts.append(f"{portfolio_story.story[:300]}..." if len(portfolio_story.story) > 300 else portfolio_story.story)
            if portfolio_story.target_year:
                context_parts.append(f"Ziel-Jahr: {portfolio_story.target_year}")
            context_parts.append(f"Priorität: {portfolio_story.priority}")

        # Usecase-specific additional context
        if positions:
            position_ids = [p.id for p in positions]

            # For ANALYSIS and REBALANCING: Include analyst verdicts
            if usecase in ["ANALYSIS", "REBALANCING"]:
                for agent_name in ["storychecker", "fundamental", "consensus_gap"]:
                    verdicts = self._analyses.get_latest_bulk(position_ids, agent_name)
                    if verdicts:
                        context_parts.append("")
                        context_parts.append(f"## {agent_name.capitalize()}-Verdicts")
                        for verdict_obj in verdicts.values():
                            pos = next((p for p in positions if p.id == verdict_obj.position_id), None)
                            if pos:
                                verdict = verdict_obj.verdict or "?"
                                summary = verdict_obj.summary or ""
                                line = f"- {pos.name}: {verdict}"
                                if summary:
                                    line += f" — {summary[:80]}"
                                context_parts.append(line)
                        lineage["agents_used"].append(agent_name)

            # For ANALYSIS: Include portfolio story analysis
            if usecase == "ANALYSIS":
                story_analyses = self._portfolio_story.get_latest_analysis() if self._portfolio_story else None
                if story_analyses:
                    context_parts.append("")
                    context_parts.append("## Portfolio Story Analyse")
                    context_parts.append(f"Story-Fit: {story_analyses.get('verdict')}")
                    context_parts.append(f"Performance: {story_analyses.get('perf_verdict')}")
                    context_parts.append(f"Stabilität: {story_analyses.get('stability_verdict')}")
                    lineage["agents_used"].append("portfolio_story")

        context = "\n".join(context_parts)
        return context, lineage

    def _classify_and_validate(
        self,
        user_query: str,
        portfolio_story: Optional[object] = None,
    ) -> tuple[str, bool, str]:
        """
        Phase 1: Classify query into usecase and validate against portfolio story.

        Returns:
        - usecase: one of ALLOCATION, REBALANCING, WITHDRAWAL, ANALYSIS, or INVALID
        - is_valid: bool — is this query compatible with portfolio analysis?
        - reason: str — if invalid, why? (shown to user)

        Logic:
        1. Classify query into usecase (using keywords + LLM judgment)
        2. Check if usecase makes sense for this portfolio
        3. If portfolio story exists, validate that query respects the story's constraints
        """
        query_lower = user_query.lower()

        # Simple keyword-based classification (can be enhanced with LLM if needed)
        if any(w in query_lower for w in ["investier", "anlegen", "wie viel", "10000", "euro", "kaufen"]):
            usecase = "ALLOCATION"
        elif any(w in query_lower for w in ["rebalancer", "umstruktur", "rebalance", "gewicht", "umschicht"]):
            usecase = "REBALANCING"
        elif any(w in query_lower for w in ["abheben", "verkauf", "reduz", "entnehm", "liquidät", "verkaufen", "entnehmen"]):
            usecase = "WITHDRAWAL"
        elif any(w in query_lower for w in ["robust", "szenario", "krise", "stabilität", "risiko", "stre", "halten", "hold", "soll ich", "bewertung", "bewertet", "fit", "passt", "about", "über", "was", "wie"]):
            usecase = "ANALYSIS"
        else:
            usecase = "UNKNOWN"

        # Validate against portfolio story
        if portfolio_story:
            # If portfolio story exists, query should align with its strategy
            # Examples of incompatible queries:
            # - Story: "conservative, income-focused" + Query: "maximize growth speculation"
            # - Story: "no crypto" + Query: "should I buy bitcoin?"
            # - Story: "long-term, 20-year horizon" + Query: "timing the market"

            if usecase == "UNKNOWN":
                return "INVALID", False, (
                    "Deine Frage passt nicht zu Portfolio-Analysen. "
                    "Ich kann dir bei: Geld investieren? Rebalancieren? Abheben? Robustheit prüfen? helfen."
                )

            # Validate story alignment for each usecase
            if usecase == "ALLOCATION":
                # ALLOCATION is always valid if story exists
                return usecase, True, ""

            elif usecase == "REBALANCING":
                # REBALANCING is always valid
                return usecase, True, ""

            elif usecase == "WITHDRAWAL":
                # WITHDRAWAL is always valid
                return usecase, True, ""

            elif usecase == "ANALYSIS":
                # ANALYSIS is always valid
                return usecase, True, ""

        else:
            # No portfolio story — still allow analysis but warn
            if usecase == "UNKNOWN":
                return "INVALID", False, (
                    "Deine Frage passt nicht zu Portfolio-Analysen. "
                    "Probier: 'Wie investiere ich 10.000€?' oder 'Soll ich rebalancieren?'"
                )
            return usecase, True, ""



def _build_portfolio_snapshot(positions: list[Position], market_repo) -> str:
    """Build portfolio text summary (shows only portfolio positions, not watchlist)."""
    portfolio_positions = [p for p in positions if p.in_portfolio]
    if not portfolio_positions:
        return "(Leer)"

    lines = []

    # Group by asset class
    by_class = {}
    for pos in portfolio_positions:
        ac = pos.asset_class or "Other"
        if ac not in by_class:
            by_class[ac] = []
        by_class[ac].append(pos)

    for asset_class, pos_list in sorted(by_class.items()):
        lines.append(f"### {asset_class}")

        for pos in pos_list:
            qty_str = f"{pos.quantity}" if pos.quantity else "1"
            lines.append(f"- {pos.name} ({pos.ticker}): {qty_str}")

    return "\n".join(lines)


def _build_watchlist_summary(watchlist: list[Position]) -> str:
    """Build watchlist text summary."""
    if not watchlist:
        return "(Leer)"

    lines = []
    for pos in watchlist[:10]:  # Show first 10
        line = f"- {pos.name} ({pos.ticker})"
        if pos.asset_class:
            line += f" [{pos.asset_class}]"
        lines.append(line)

    if len(watchlist) > 10:
        lines.append(f"... + {len(watchlist) - 10} weitere")

    return "\n".join(lines)
