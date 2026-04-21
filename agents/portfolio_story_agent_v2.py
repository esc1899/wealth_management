"""
Portfolio Story Agent V2 — clean slate, focused on story alignment check only.
Analyzes portfolio narrative alignment and performance.
Local Ollama LLM (private 🔒 — no data leaves the machine).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from core.llm.local import OllamaProvider
from core.storage.models import PortfolioStory, PortfolioStoryAnalysis, Skill
from core.storage.positions import PositionsRepository
from core.storage.market_data import MarketDataRepository
from core.storage.skills import SkillsRepository

logger = logging.getLogger(__name__)


@dataclass
class StoryAndPerfResult:
    """Result from story + performance analysis."""
    verdict: str
    summary: str
    perf_verdict: str
    perf_summary: str
    full_text: str


class PortfolioStoryAgentV2:
    """
    Analyzes portfolio story alignment and performance.
    V2: focused scope — only Story & Performance, no Stability or Cash checks.
    """

    def __init__(
        self,
        llm: OllamaProvider,
        positions_repo: PositionsRepository,
        market_repo: MarketDataRepository,
        skills_repo: Optional[SkillsRepository] = None,
        portfolio_story_repo=None,
        agent_runs_repo=None,
    ):
        self._llm = llm
        self._positions = positions_repo
        self._market = market_repo
        self._skills_repo = skills_repo
        self._story_repo = portfolio_story_repo
        self._agent_runs_repo = agent_runs_repo

    @property
    def model(self) -> str:
        """Return the LLM model name."""
        return self._llm.model

    async def generate_story_draft(
        self,
        positions_summary: str,
        existing_story: Optional[PortfolioStory] = None,
        story_text: Optional[str] = None,
        target_year: Optional[int] = None,
        liquidity_need: Optional[str] = None,
        priority: Optional[str] = None,
    ) -> str:
        """
        Generate an AI-assisted portfolio story draft.
        Guided by current portfolio composition, existing story, and new form inputs.
        """
        info = f"Aktuelle Portfolio-Zusammensetzung:\n{positions_summary}"

        goals_lines = []
        if priority:
            goals_lines.append(f"- Priorität: {priority}")
        if target_year:
            goals_lines.append(f"- Ziel-Jahr: {target_year}")
        if liquidity_need:
            goals_lines.append(f"- Liquiditätsbedarf: {liquidity_need}")
        goals_section = "\n".join(goals_lines) if goals_lines else ""

        if existing_story:
            if story_text or target_year or liquidity_need or priority:
                task = f"Aktualisiere diese Portfolio-These anhand der neuen Eingaben:\n\n{existing_story.story}"
                if goals_section:
                    task += f"\n\nNeue Ziele/Eingaben:\n{goals_section}"
            else:
                task = f"Verbessere diese bestehende Portfolio-These:\n\n{existing_story.story}"
        else:
            task = "Schreibe ein prägnantes Portfolio-Narrativ (3–5 Sätze)."
            if goals_section:
                task += f"\n\nBerücksichtige diese Ziele:\n{goals_section}"

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

    async def analyze_story_and_performance(
        self,
        story: PortfolioStory,
        portfolio_snapshot: str,
        position_verdicts: str,
    ) -> StoryAndPerfResult:
        """
        Analyze portfolio story alignment.
        V2: Two focused questions only.
        - Is the portfolio story still intact?
        - How do the positions (with their Story Checker verdicts) support the story?
        """
        self._llm.skill_context = "portfolio_story_check"

        base_prompt = f"""Du bist ein Portfolio-Analyst. Beurteile, ob ein Portfolio mit den Zielen des Investors aligned ist.

Portfolio-These (Narrativ):
{story.story}

Ziele:
- Ziel-Jahr: {story.target_year or 'offen'}
- Liquiditätsbedarf: {story.liquidity_need or 'keine angegeben'}
- Priorität: {story.priority}

Antworte IMMER in diesem exakten Format:

## Portfolio Story-Check
**Story-Urteil:** 🟢 Intakt | 🟡 Gemischt | 🔴 Gefährdet
> {{EIN-SATZ-FAZIT}}

Stimmt das Portfolio noch mit der Geschichte des Investors überein?
- Was bestätigt die These?
- Was stellt sie in Frage?

## Positions-Analyse
**Positions-Urteil:** 🟢 Unterstützen Story | 🟡 Gemischt | 🔴 Gefährden Story
> {{EIN-SATZ-FAZIT}}

Welche Positionen stärken oder schwächen die Story? (Nutze die Verdicts unten.)

---

Portfolio-Daten:
{portfolio_snapshot}

Positions-Story-Checker Verdicts:
{position_verdicts}"""

        user_message = "Bitte analysiere mein Portfolio gegen die angegebene These und Ziele."

        reply = await self._llm.complete(base_prompt + "\n\n" + user_message, max_tokens=1024)

        story_verdict = _extract_verdict_from_section(reply, "Portfolio Story-Check")
        story_summary = _extract_summary(reply, "Portfolio Story-Check")
        perf_verdict = _extract_verdict_from_section(reply, "Positions-Analyse")
        perf_summary = _extract_summary(reply, "Positions-Analyse")

        return StoryAndPerfResult(
            verdict=story_verdict or "unknown",
            summary=story_summary or "Analyse ausstehend",
            perf_verdict=perf_verdict or "unknown",
            perf_summary=perf_summary or "Bewertung ausstehend",
            full_text=reply,
        )

    async def analyze_positions(
        self,
        story: PortfolioStory,
        positions: list,
        verdicts: dict,
    ) -> list:
        """
        Analyze how each position strengthens/weakens the portfolio story.
        Returns list of PortfolioStoryPositionFit objects.
        """
        self._llm.skill_context = "portfolio_story_position_fit"

        if not positions:
            return []

        position_lines = []
        for pos in positions:
            ticker = f" ({pos.ticker})" if pos.ticker else ""
            verdicts_info = []

            if pos.id in verdicts:
                pos_verdicts = verdicts[pos.id]
                for agent_name, verdict_obj in pos_verdicts.items():
                    if verdict_obj:
                        verdicts_info.append(f"{agent_name}: {verdict_obj.verdict}")

            verdict_str = " | ".join(verdicts_info) if verdicts_info else "keine Analysen"
            position_lines.append(
                f"- {pos.name}{ticker} [{pos.asset_class}] — {verdict_str}"
            )

        positions_snapshot = "\n".join(position_lines)

        system_prompt = f"""Du bist ein Portfolio-Berater der bewertet welche Rolle jede Position in der Portfolio-These spielt.

Portfolio-These:
{story.story}

Ziele:
- Ziel-Jahr: {story.target_year or 'offen'}
- Priorität: {story.priority}

Weise JEDE Position EINE Rolle zu, die sie in dieser Story erfüllt:
- Wachstumsmotor: treibt Kapitalwachstum
- Stabilitätsanker: reduziert Portfoliovolatilität
- Einkommensquelle: generiert Ausschüttungen
- Diversifikationselement: geringe Korrelation zum Rest
- Fehlplatzierung: passt nicht zur Story-Logik

Die Rolle richtet sich nach der STORY-LOGIK, nicht nach absoluter Qualität.
"Fehlplatzierung" nur wenn die Position keinen erkennbaren Platz in dieser Story hat.

**WICHTIG: Antworte EXAKT in diesem Format — EINE Zeile pro Position:**

TICKER: Rolle | Ein-Satz-Begründung

Verwende NUR die Ticker aus der Liste unten. Keine Nummern, keine Worte vor dem Ticker.

Positionen zur Bewertung:
{positions_snapshot}"""

        user_message = "Bitte bewerte jede Position."

        reply = await self._llm.complete(system_prompt + "\n\n" + user_message, max_tokens=1024)

        fits = self._parse_position_fits(reply, positions)

        if self._story_repo and fits:
            self._story_repo.save_position_fits(fits)

        if self._agent_runs_repo:
            fit_counts = {}
            for fit in fits:
                role = fit.role if hasattr(fit, 'role') else 'unknown'
                fit_counts[role] = fit_counts.get(role, 0) + 1

            fit_summary = ", ".join(f"{role}: {count}" for role, count in fit_counts.items()) if fit_counts else "No fits"

            self._agent_runs_repo.log_run(
                agent_name="portfolio_story",
                model=self.model,
                output_summary=f"Position fits: {fit_summary}",
                context_summary=f"Analyzed {len(positions)} positions",
            )

        return fits

    @staticmethod
    def _parse_position_fits(text: str, positions: list) -> list:
        """Extract position fit roles from LLM output."""
        from core.storage.models import PortfolioStoryPositionFit, FIT_ROLES
        from datetime import datetime, timezone

        fits = []
        ticker_to_pos = {pos.ticker.upper(): pos for pos in positions if pos.ticker}

        if not ticker_to_pos:
            return []

        for line in text.split("\n"):
            line = line.strip()
            if not line or ":" not in line:
                continue

            parts = line.split(":", 1)
            ticker = parts[0].strip().upper()
            rest = parts[1].strip() if len(parts) > 1 else ""

            if ticker not in ticker_to_pos:
                continue

            fit_role = None
            for role in FIT_ROLES:
                if role in rest:
                    fit_role = role
                    break

            if not fit_role:
                continue

            if "|" in rest:
                fit_summary = rest.split("|", 1)[1].strip()
            else:
                fit_summary = rest.replace(fit_role, "").strip()

            fit_summary = fit_summary.replace("[", "").replace("]", "").strip()
            if not fit_summary:
                fit_summary = f"Position spielt Rolle: {fit_role}"

            pos = ticker_to_pos[ticker]
            fit = PortfolioStoryPositionFit(
                position_id=pos.id,
                fit_role=fit_role,
                fit_summary=fit_summary,
                created_at=datetime.now(timezone.utc),
            )
            fits.append(fit)

        return fits


# ──────────────────────────────────────────────────────────────────────
# Parsing helpers
# ──────────────────────────────────────────────────────────────────────


def _extract_verdict_from_section(text: str, section_name: str) -> Optional[str]:
    """
    Extract verdict emoji from a specific section.
    Returns: 'intact', 'gemischt', 'gefaehrdet', 'on_track', 'achtung', 'kritisch', or None.
    """
    lines = text.split("\n")
    in_section = False
    for line in lines:
        if section_name in line:
            in_section = True
        if in_section and "**" in line and "-Urteil:" in line:
            if "🟢" in line:
                if "Story" in section_name:
                    return "intact"
                elif "Performance" in section_name:
                    return "on_track"
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
