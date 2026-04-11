"""
Portfolio Story Agent — analyzes portfolio alignment with user goals.
Local Ollama LLM (private 🔒 — no data leaves the machine).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from core.llm.local import OllamaProvider
from core.storage.models import PortfolioStory, PortfolioStoryAnalysis
from core.storage.positions import PositionsRepository
from core.storage.market_data import MarketDataRepository

logger = logging.getLogger(__name__)


@dataclass
class PortfolioMetrics:
    """Computed portfolio-level metrics for the agent."""
    total_value_eur: float
    total_pnl_eur: float
    total_pnl_pct: float
    total_annual_dividend_eur: float
    portfolio_dividend_yield_pct: float
    josef_aktien_pct: float
    josef_renten_pct: float
    josef_rohstoffe_pct: float
    positions_count: int


class PortfolioStoryAgent:
    """
    Analyzes portfolio story alignment and performance.
    Two separate checks: Story alignment vs. reality, and Performance vs. goals.
    Stabili output format: structured sections with verdicts and summaries.
    """

    def __init__(
        self,
        llm: OllamaProvider,
        positions_repo: PositionsRepository,
        market_repo: MarketDataRepository,
    ):
        self._llm = llm
        self._positions = positions_repo
        self._market = market_repo

    async def generate_story_draft(
        self,
        positions_summary: str,
        existing_story: Optional[PortfolioStory] = None,
    ) -> str:
        """
        Generate an AI-assisted portfolio story draft.
        Guided by current portfolio composition and any existing story.
        """
        info = f"Aktuelle Portfolio-Zusammensetzung:\n{positions_summary}"

        if existing_story:
            task = f"Aktualisiere und verbessere diese bestehende Portfolio-These:\n\n{existing_story.story}"
        else:
            task = "Schreibe ein prägnantes Portfolio-Narrativ (3–5 Sätze)."

        prompt = (
            f"Du bist ein erfahrener Vermögensberater.\n\n"
            f"{info}\n\n"
            f"{task}\n\n"
            "Das Narrativ soll erklären: Was sind die langfristigen Ziele? "
            "Welcher Anlagehorizont? Welche Prioritäten (Wachstum/Einkommen/Sicherheit)? "
            "Welche wichtigen Lebens-Meilensteine (Immobilienkauf, Ruhestand, etc.)?\n\n"
            "Antworte NUR mit der These, keine Einleitung, keine Überschrift."
        )

        return await self._llm.complete(prompt, max_tokens=500)

    async def analyze(
        self,
        story: PortfolioStory,
        portfolio_snapshot: str,
        metrics: PortfolioMetrics,
        dividend_snapshot: str,
        inflation_rate: Optional[float] = None,
    ) -> PortfolioStoryAnalysis:
        """
        Analyze portfolio story alignment and performance.
        Returns structured analysis with three sections: Story, Performance, Stability.
        """
        self._llm.skill_context = "portfolio_story_check"

        # Build context for LLM
        inflation_context = ""
        if inflation_rate is not None:
            inflation_context = (
                f"\n\nAktuelle Inflation (HICP): {inflation_rate:.2f}% "
                f"(Referenzwert für Bewertung geldbasierter Anlagen)"
            )

        system_prompt = f"""Du bist ein kritischer Portfolio-Analyst der bewertet ob ein Portfolio mit den Zielen des Investors aligned ist.

Portfolio-These (Narrativ):
{story.story}

Ziele:
- Ziel-Jahr: {story.target_year or 'offen'}
- Liquiditätsbedarf: {story.liquidity_need or 'keine angegeben'}
- Priorität: {story.priority}

Analysiere anhand der Portfolio-Daten unten ob die These noch hält.
Antworte IMMER in diesem exakten Format (drei Sektionen mit je eigenem Urteil):

## Portfolio Story-Check
**Story-Urteil:** 🟢 Intakt | 🟡 Gemischt | 🔴 Gefährdet
> {{EIN-SATZ-FAZIT}}

### Was bestätigt die Portfolio-These
### Was stellt sie in Frage

## Performance & Dividenden
**Performance-Urteil:** 🟢 On Track | 🟡 Achtung | 🔴 Kritisch
> {{EIN-SATZ-FAZIT}}

### Einschätzung im Kontext der Ziele

## Stabilität
**Stabilitäts-Urteil:** 🟢 Stabil | 🟡 Achtung | 🔴 Instabil
> {{EIN-SATZ-FAZIT}}

### Impact der Gewichtung auf Portfoliostabilität

---

Portfolio-Daten:
{portfolio_snapshot}

Dividenden-Snapshot:
{dividend_snapshot}{inflation_context}"""

        user_message = "Bitte analysiere mein Portfolio gegen die angegebene These und Ziele."

        reply = await self._llm.complete(system_prompt + "\n\n" + user_message, max_tokens=2048)

        # Parse structured output
        analysis = self._parse_analysis(reply, full_text=reply)
        return analysis

    @staticmethod
    def _parse_analysis(text: str, full_text: str = "") -> PortfolioStoryAnalysis:
        """Extract verdicts and summaries from structured LLM output."""
        # Extract verdicts using emoji patterns
        story_verdict = _extract_verdict_from_section(text, "Portfolio Story-Check")
        story_summary = _extract_summary(text, "Portfolio Story-Check")

        perf_verdict = _extract_verdict_from_section(text, "Performance & Dividenden")
        perf_summary = _extract_summary(text, "Performance & Dividenden")

        stability_verdict = _extract_verdict_from_section(text, "Stabilität")
        stability_summary = _extract_summary(text, "Stabilität")

        from datetime import datetime, timezone
        return PortfolioStoryAnalysis(
            verdict=story_verdict or "unknown",
            summary=story_summary or "Analyse ausstehend",
            perf_verdict=perf_verdict or "unknown",
            perf_summary=perf_summary or "Bewertung ausstehend",
            stability_verdict=stability_verdict or "unknown",
            stability_summary=stability_summary or "Einschätzung ausstehend",
            full_text=full_text,
            created_at=datetime.now(timezone.utc),
        )


# ──────────────────────────────────────────────────────────────────────
# Parsing helpers
# ──────────────────────────────────────────────────────────────────────


def _extract_verdict_from_section(text: str, section_name: str) -> Optional[str]:
    """
    Extract verdict emoji from a specific section.
    Returns: 'intact', 'gemischt', 'gefaehrdet', 'on_track', 'achtung', 'kritisch', 'stabil', 'instabil', or None.
    """
    # Find the section
    lines = text.split("\n")
    in_section = False
    for line in lines:
        if section_name in line:
            in_section = True
        if in_section and "**" in line and "-Urteil:" in line:
            # Parse verdict from this line
            if "🟢" in line:
                # Determine which type based on context
                if "Story" in section_name:
                    return "intact"
                elif "Performance" in section_name:
                    return "on_track"
                elif "Stabilität" in section_name:
                    return "stabil"
            elif "🟡" in line:
                if "Story" in section_name:
                    return "gemischt"
                else:
                    return "achtung"
            elif "🔴" in line:
                if "Story" in section_name:
                    return "gefaehrdet"
                elif "Performance" in section_name:
                    return "kritisch"
                elif "Stabilität" in section_name:
                    return "instabil"
            return None
    return None


def _extract_summary(text: str, section_name: str) -> Optional[str]:
    """Extract the one-sentence blockquote summary from a section."""
    lines = text.split("\n")
    in_section = False
    for i, line in enumerate(lines):
        if section_name in line:
            in_section = True
        if in_section and line.strip().startswith("> "):
            return line.strip()[2:].strip()
    return None
