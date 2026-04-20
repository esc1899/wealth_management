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
from core.storage.models import PortfolioStory, PortfolioStoryAnalysis, Skill
from core.storage.positions import PositionsRepository
from core.storage.market_data import MarketDataRepository
from core.storage.skills import SkillsRepository

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


@dataclass
class StabilityResult:
    """Result from a stability-only analysis (FEAT-18)."""
    verdict: str
    summary: str
    full_text: str


@dataclass
class StoryAndPerfResult:
    """Result from story + performance analysis (FEAT-18)."""
    verdict: str
    summary: str
    perf_verdict: str
    perf_summary: str
    full_text: str


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

        # Build goals section from form inputs
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
                # User edited the story or changed goals — update based on changes
                task = f"Aktualisiere diese Portfolio-These anhand der neuen Eingaben:\n\n{existing_story.story}"
                if goals_section:
                    task += f"\n\nNeue Ziele/Eingaben:\n{goals_section}"
            else:
                # No changes, just refine
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

    async def analyze_stability(
        self,
        metrics: PortfolioMetrics,
        portfolio_snapshot: str,
        skill_prompt: Optional[str] = None,
    ) -> StabilityResult:
        """
        Analyze portfolio stability (Josef's Regel or custom skill).
        FEAT-18: Separate modular check from Story/Performance.
        """
        self._llm.skill_context = "portfolio_stability_check"

        josef_summary = (
            f"Aktien: {metrics.josef_aktien_pct:.0f}% | "
            f"Renten/Geld: {metrics.josef_renten_pct:.0f}% | "
            f"Rohstoffe + Immo: {metrics.josef_rohstoffe_pct:.0f}%"
        )

        system_prompt = f"""Du bist ein kritischer Portfolio-Analyst der Portfolio-Stabilität bewertet.

Portfolio-Daten:
{portfolio_snapshot}

Gewichtung nach Josef's Regel: {josef_summary}

Analysiere die Stabilität des Portfolios gegen die Kriterien unten.
Antworte IMMER in diesem exakten Format:

## Stabilität
**Stabilitäts-Urteil:** 🟢 Stabil | 🟡 Achtung | 🔴 Instabil
> {{EIN-SATZ-FAZIT}}

### Fazit zur Stabilität"""

        if skill_prompt:
            system_prompt += f"\n\n## Stabilitäts-Fokus\n{skill_prompt}"

        user_message = "Bitte analysiere die Stabilität meines Portfolios."

        reply = await self._llm.complete(system_prompt + "\n\n" + user_message, max_tokens=1024)

        # Parse stability section only
        stability_verdict = _extract_verdict_from_section(reply, "Stabilität")
        stability_summary = _extract_summary(reply, "Stabilität")

        return StabilityResult(
            verdict=stability_verdict or "unknown",
            summary=stability_summary or "Einschätzung ausstehend",
            full_text=reply,
        )

    async def analyze_story_and_performance(
        self,
        story: PortfolioStory,
        portfolio_snapshot: str,
        dividend_snapshot: str,
        skill_prompt: Optional[str] = None,
        inflation_rate: Optional[float] = None,
    ) -> StoryAndPerfResult:
        """
        Analyze portfolio story alignment and performance.
        FEAT-18: Separate modular check from Stability.
        """
        self._llm.skill_context = "portfolio_story_check"

        inflation_context = ""
        if inflation_rate is not None:
            inflation_context = (
                f"\n\nAktuelle Inflation (HICP): {inflation_rate:.2f}% "
                f"(Referenzwert für Bewertung geldbasierter Anlagen)"
            )

        base_prompt = f"""Du bist ein kritischer Portfolio-Analyst der bewertet ob ein Portfolio mit den Zielen des Investors aligned ist.

Portfolio-These (Narrativ):
{story.story}

Ziele:
- Ziel-Jahr: {story.target_year or 'offen'}
- Liquiditätsbedarf: {story.liquidity_need or 'keine angegeben'}
- Priorität: {story.priority}

Analysiere anhand der Portfolio-Daten unten ob die These noch hält.
Antworte IMMER in diesem exakten Format (zwei Sektionen mit je eigenem Urteil):

## Portfolio Story-Check
**Story-Urteil:** 🟢 Intakt | 🟡 Gemischt | 🔴 Gefährdet
> {{EIN-SATZ-FAZIT}}

### Was bestätigt die Portfolio-These
### Was stellt sie in Frage

## Performance & Dividenden
**Performance-Urteil:** 🟢 On Track | 🟡 Achtung | 🔴 Kritisch
> {{EIN-SATZ-FAZIT}}

### Einschätzung im Kontext der Ziele

---

Portfolio-Daten:
{portfolio_snapshot}

Dividenden-Snapshot:
{dividend_snapshot}{inflation_context}"""

        system_prompt = base_prompt
        if skill_prompt:
            system_prompt += f"\n\n## Story-Fokus\n{skill_prompt}"

        user_message = "Bitte analysiere mein Portfolio gegen die angegebene These und Ziele."

        reply = await self._llm.complete(system_prompt + "\n\n" + user_message, max_tokens=1024)

        story_verdict = _extract_verdict_from_section(reply, "Portfolio Story-Check")
        story_summary = _extract_summary(reply, "Portfolio Story-Check")
        perf_verdict = _extract_verdict_from_section(reply, "Performance & Dividenden")
        perf_summary = _extract_summary(reply, "Performance & Dividenden")

        return StoryAndPerfResult(
            verdict=story_verdict or "unknown",
            summary=story_summary or "Analyse ausstehend",
            perf_verdict=perf_verdict or "unknown",
            perf_summary=perf_summary or "Bewertung ausstehend",
            full_text=reply,
        )

    async def analyze(
        self,
        story: PortfolioStory,
        portfolio_snapshot: str,
        metrics: PortfolioMetrics,
        dividend_snapshot: str,
        inflation_rate: Optional[float] = None,
        selected_skill: Optional[Skill] = None,
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

        # Build Josef's Rule summary for stability assessment
        # Note: "Rohstoffe" includes Edelmetalle + Immobilien combined
        josef_summary = (
            f"Aktien: {metrics.josef_aktien_pct:.0f}% | "
            f"Renten/Geld: {metrics.josef_renten_pct:.0f}% | "
            f"Rohstoffe + Immo: {metrics.josef_rohstoffe_pct:.0f}%"
        )

        # Build BASE system prompt (without specific stability rule — that comes from skills)
        base_prompt = f"""Du bist ein kritischer Portfolio-Analyst der bewertet ob ein Portfolio mit den Zielen des Investors aligned ist.

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

Beurteile die Stabilität mit den Kriterien unten (Fokus-Bereich je nach ausgewählter Stabilitäts-Regel).

### Fazit zur Stabilität

---

Portfolio-Daten:
{portfolio_snapshot}

Gewichtung nach Josef's Regel: {josef_summary}

Dividenden-Snapshot:
{dividend_snapshot}{inflation_context}"""

        # Build final system prompt: base + stability rule from skill only
        system_prompt = base_prompt
        if selected_skill and selected_skill.prompt:
            system_prompt += f"\n\n## Stabilitäts-Fokus: {selected_skill.name}\n{selected_skill.prompt}"

        user_message = "Bitte analysiere mein Portfolio gegen die angegebene These und Ziele."

        reply = await self._llm.complete(system_prompt + "\n\n" + user_message, max_tokens=2048)

        # Parse structured output
        analysis = self._parse_analysis(reply, full_text=reply)

        # Persist analysis if repo is available
        if self._story_repo:
            self._story_repo.save_analysis(analysis)

        return analysis

    async def analyze_positions(
        self,
        story: PortfolioStory,
        positions: list,  # List of Position objects
        verdicts: dict,   # position_id -> PositionAnalysis dicts from various agents
    ) -> list:
        """
        Analyze how each position strengthens/weakens the portfolio story.
        Returns list of PortfolioStoryPositionFit objects.
        Single batch LLM call for all positions.
        """
        self._llm.skill_context = "portfolio_story_position_fit"

        if not positions:
            return []

        # Build position snapshot with key info
        position_lines = []
        for pos in positions:
            ticker = f" ({pos.ticker})" if pos.ticker else ""
            verdicts_info = []

            # Add existing verdicts if available
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

        # Parse position fits from reply
        fits = self._parse_position_fits(reply, positions)

        # Persist position fits if repo is available
        if self._story_repo and fits:
            self._story_repo.save_position_fits(fits)

        # Log the run if repo is available
        if self._agent_runs_repo:
            # Build a summary from the fits if available
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

        # Create lookup: ticker -> position for matching (case-insensitive)
        ticker_to_pos = {pos.ticker.upper(): pos for pos in positions if pos.ticker}

        if not ticker_to_pos:
            return []  # No positions with tickers to match

        # Parse each line: expect "TICKER: role | summary"
        for line in text.split("\n"):
            line = line.strip()
            if not line or ":" not in line:
                continue

            # Split on first colon: "TICKER: rest"
            parts = line.split(":", 1)
            ticker = parts[0].strip().upper()
            rest = parts[1].strip() if len(parts) > 1 else ""

            # Must be a known ticker
            if ticker not in ticker_to_pos:
                continue

            # Extract role from rest: match against FIT_ROLES
            fit_role = None
            for role in FIT_ROLES:
                if role in rest:
                    fit_role = role
                    break

            if not fit_role:
                continue

            # Extract summary: text after "|"
            if "|" in rest:
                fit_summary = rest.split("|", 1)[1].strip()
            else:
                fit_summary = rest.replace(fit_role, "").strip()

            # Clean up
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
