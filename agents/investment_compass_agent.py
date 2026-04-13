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

from core.llm.local import OllamaProvider
from core.storage.analyses import PositionAnalysesRepository
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
        """
        self._llm.skill_context = skill_name or "investment_compass"

        # Build context with lineage tracking
        context, lineage = self._build_context_with_lineage(skill_name, skill_prompt)

        # Build prompt
        system_prompt = BASE_SYSTEM_PROMPT
        if skill_prompt:
            system_prompt += f"\n\n## Strategie: {skill_name}\n{skill_prompt}"

        system_prompt += f"\n\n## Portfolio-Kontext\n{context}"

        # LLM call - combine system and context with user query
        full_prompt = f"{system_prompt}\n\n{user_query}"
        messages = [
            {
                "role": "user",
                "content": full_prompt,
            }
        ]

        full_response = await self._llm.chat(messages)

        return InvestmentAnalysis(
            response=full_response,
            lineage=lineage,
        )

    def _build_context_with_lineage(
        self, skill_name: Optional[str] = None, skill_prompt: Optional[str] = None
    ) -> tuple[str, dict]:
        """
        Build portfolio context from implicit agent hierarchy.
        Returns (context_string, lineage_metadata).
        """
        context_parts = []
        lineage = {
            "agents_used": [],
            "skills_used": [],
            "model": self.model,
            "timestamp": datetime.now().isoformat(),
        }

        # -------- Ebene 0: Always available --------

        # Portfolio snapshot
        positions = self._positions.get_portfolio()
        watchlist = self._positions.get_watchlist()

        portfolio_text = _build_portfolio_snapshot(positions, self._market)
        context_parts.append("## Portfolio (aktuell)")
        context_parts.append(portfolio_text)
        lineage["agents_used"].append("portfolio_data")

        # Watchlist
        if watchlist:
            watchlist_text = _build_watchlist_summary(watchlist)
            context_parts.append("")
            context_parts.append("## Watchlist")
            context_parts.append(watchlist_text)

        # Portfolio story
        story = self._portfolio_story.get_latest()
        if story:
            context_parts.append("")
            context_parts.append(f"## Portfolio Story")
            context_parts.append(f"{story.story[:300]}..." if len(story.story) > 300 else story.story)
            if story.target_year:
                context_parts.append(f"Ziel-Jahr: {story.target_year}")
            context_parts.append(f"Priorität: {story.priority}")

        # -------- Ebene 1: Analyst verdicts (if available) --------

        if positions:
            position_ids = [p.id for p in positions]
            for agent_name in ["storychecker", "fundamental", "consensus_gap"]:
                verdicts = self._analyses.get_latest_bulk(position_ids, agent_name)
                if verdicts:
                    context_parts.append("")
                    context_parts.append(f"## {agent_name.capitalize()}-Verdicts")
                    for v in verdicts:
                        pos = next((p for p in positions if p.id == v["position_id"]), None)
                        if pos:
                            verdict = v.get("verdict", "?")
                            summary = v.get("summary", "")
                            line = f"- {pos.name}: {verdict}"
                            if summary:
                                line += f" — {summary[:80]}"
                            context_parts.append(line)
                    lineage["agents_used"].append(agent_name)

        # -------- Ebene 2: Portfolio story analysis (if available) --------

        story_analyses = self._portfolio_story.get_latest_analysis()
        if story_analyses:
            context_parts.append("")
            context_parts.append("## Portfolio Story Analyse")
            context_parts.append(f"Story-Fit: {story_analyses.get('verdict')}")
            context_parts.append(f"Performance: {story_analyses.get('perf_verdict')}")
            context_parts.append(f"Stabilität: {story_analyses.get('stability_verdict')}")
            lineage["agents_used"].append("portfolio_story")

        # -------- Add skill info --------

        if skill_name:
            lineage["skills_used"].append(skill_name)

        context = "\n".join(context_parts)
        return context, lineage


def _build_portfolio_snapshot(positions: list, market_repo) -> str:
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


def _build_watchlist_summary(watchlist: list) -> str:
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
