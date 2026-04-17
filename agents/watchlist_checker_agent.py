"""
Watchlist Checker Agent — evaluates which watchlist positions fit into the current portfolio.

Local-only (OllamaProvider). Runs once, no sessions.
Inputs: portfolio snapshot, watchlist positions with existing verdicts.
Output: per-position fit verdict + summary, full analysis text.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

from core.llm.base import Message, Role
from core.llm.local import OllamaProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.models import Position, Skill
from core.storage.skills import SkillsRepository
from agents.agent_language import response_language_instruction

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Output models
# ------------------------------------------------------------------


@dataclass
class WatchlistFit:
    """Verdict for a single watchlist position."""
    position_id: int
    verdict: str  # "sehr_passend" | "passend" | "neutral" | "nicht_passend"
    summary: str


@dataclass
class WatchlistCheckResult:
    """Result of a watchlist check run."""
    position_fits: list[WatchlistFit]
    full_text: str


# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """Du bist ein kritischer Portfolio-Analyst der bewertet, welche Watchlist-Positionen gut in das bestehende Portfolio passen würden.

Du erhältst:
- Snapshot des aktuellen Portfolios (Josef's Regel, Holdings, Werte)
- Portfolio Story und Ausrichtung (falls vorhanden)
- Watchlist-Positionen mit Details und bekannten Verdicts (Storychecker, Fundamental, Consensus Gap)

Deine Aufgabe: Beurteile pro Watchlist-Position ob und wie gut sie ins Portfolio passt.
Beachte:
- Josef's Regel (1/3 Aktien, 1/3 Renten/Geld, 1/3 Rohstoffe+Immo) und aktuelle Anteile
- Portfolio-Story und strategische Ausrichtung
- Bestehende Analyst-Verdicts (Qualität, Bewertung)
- Diversifikation und Risiko
- Nicht Empfehlungen geben, sondern fit evaluieren

Antworte in diesem Format für JEDE Watchlist-Position:

## {NAME} ({TICKER})
**Fit:** {AMPEL}

> {EIN-SATZ-FAZIT}

{Begründung 2–3 Sätze zum fit mit Portfolio}

---

Nach allen Positionen ein Gesamtfazit:

## Zusammenfassung
{2–3 Sätze welche Positionen am meisten Sinn machen und warum}

---

Ampel-Regeln (genau eine wählen pro Position):
- 🟢 **Sehr passend** — Füllt Portfolio-Lücke, passt zur Story, gute Fundamentals
- 🟡 **Passend** — Macht Sinn, aber nicht dringend oder einige kleine Vorbehalte
- ⚪ **Neutral** — Passt rein, aber nicht besonders gesucht
- 🔴 **Nicht passend** — Widerspricht Portfolio-Ausrichtung oder aktuelle Übergewichtung

Sei direkt und konkret. Keine Allgemeinplätze.
Keine neuen Empfehlungen — nur fit-Analyse bestehender Watchlist-Positionen."""


# ------------------------------------------------------------------
# Agent
# ------------------------------------------------------------------


class WatchlistCheckerAgent:
    """
    Local agent that evaluates fit of watchlist positions into current portfolio.
    One-shot run — no sessions.
    """

    def __init__(
        self,
        positions_repo,
        analyses_repo: PositionAnalysesRepository,
        llm: OllamaProvider,
        skills_repo: Optional[SkillsRepository] = None,
        wc_repo=None,
        agent_runs_repo=None,
    ) -> None:
        self._positions = positions_repo
        self._analyses = analyses_repo
        self._llm = llm
        self._skills_repo = skills_repo
        self._wc_repo = wc_repo
        self._agent_runs_repo = agent_runs_repo

    @property
    def model(self) -> str:
        return self._llm.model

    async def check_watchlist(
        self,
        portfolio_snapshot: str,
        watchlist_positions: list[Position],
        story_analysis_text: Optional[str] = None,
        selected_skill: Optional[Skill] = None,
        language: str = "de",
    ) -> WatchlistCheckResult:
        """Evaluate which watchlist positions fit into the current portfolio."""
        if not watchlist_positions:
            return WatchlistCheckResult(
                position_fits=[],
                full_text="Keine Watchlist-Positionen vorhanden.",
            )

        self._llm.skill_context = "watchlist_checker"

        # Build context
        context_parts = [
            "## Portfolio-Snapshot",
            portfolio_snapshot,
        ]

        if story_analysis_text:
            context_parts.extend([
                "",
                "## Portfolio Story & Analyse",
                story_analysis_text,
            ])

        # Bulk-fetch verdicts for all positions upfront (3 calls instead of N×3)
        watchlist_ids = [pos.id for pos in watchlist_positions if pos.id]
        bulk_verdicts = {}
        if watchlist_ids:
            for agent_name in ["storychecker", "fundamental", "consensus_gap"]:
                results = self._analyses.get_latest_bulk(watchlist_ids, agent_name)
                for pos_id, verdict_obj in results.items():
                    if pos_id not in bulk_verdicts:
                        bulk_verdicts[pos_id] = {}
                    bulk_verdicts[pos_id][agent_name] = verdict_obj

        # Add watchlist positions with any existing verdicts
        context_parts.extend(["", "## Watchlist-Positionen"])
        for pos in watchlist_positions:
            pos_line = f"- {pos.name} ({pos.ticker})"
            if pos.asset_class:
                pos_line += f" [{pos.asset_class}]"
            context_parts.append(pos_line)

            # Add any existing verdicts from other agents
            if pos.id and pos.id in bulk_verdicts:
                for agent_name, verdict_obj in bulk_verdicts[pos.id].items():
                    if verdict_obj:
                        agent_display = verdict_obj.agent.capitalize()
                        verdict = verdict_obj.verdict or "?"
                        context_parts.append(f"  - {agent_display}: {verdict}")

        context = "\n".join(context_parts)

        # Build system prompt with optional skill injection
        system_prompt = BASE_SYSTEM_PROMPT + "\n" + response_language_instruction(language)
        if selected_skill and selected_skill.prompt:
            system_prompt = f"{system_prompt}\n\n## Fokus-Bereich ({selected_skill.name}):\n{selected_skill.prompt}"

        # LLM call (combine system prompt with context, send as user message)
        messages = [
            Message(role=Role.USER, content=f"{system_prompt}\n\n{context}")
        ]

        response = await self._llm.chat(messages)
        full_text = response

        # Parse and persist results
        fits = _parse_watchlist_results(watchlist_positions, response)
        skill_name = selected_skill.name if selected_skill else ""
        for fit in fits:
            self._analyses.save(
                position_id=fit.position_id,
                agent="watchlist_checker",
                skill_name=skill_name,
                verdict=fit.verdict,
                summary=fit.summary,
            )

        # Persist analysis if repos are available
        if self._wc_repo and self._agent_runs_repo:
            import json
            from datetime import datetime
            from core.storage.models import WatchlistCheckerAnalysis

            # Calculate fit counts from result
            fit_counts = {
                "sehr_passend": sum(1 for f in fits if f.verdict == "sehr_passend"),
                "passend": sum(1 for f in fits if f.verdict == "passend"),
                "neutral": sum(1 for f in fits if f.verdict == "neutral"),
                "nicht_passend": sum(1 for f in fits if f.verdict == "nicht_passend"),
            }

            # Serialize position fits
            position_fits_json = json.dumps([{
                "position_id": fit.position_id,
                "verdict": fit.verdict,
                "summary": fit.summary,
            } for fit in fits])

            # Extract summary from "## Zusammenfassung" section if present
            summary = None
            if full_text:
                zusammenfassung_idx = full_text.find("## Zusammenfassung")
                if zusammenfassung_idx != -1:
                    after = full_text[zusammenfassung_idx:].split('\n', 1)
                    if len(after) > 1:
                        body = after[1].strip()
                        first_line = next((l.strip() for l in body.split('\n') if l.strip()), None)
                        summary = first_line[:200] if first_line else None

            # Fallback: create summary from fit counts if not found
            if not summary:
                summary = f"Geprüft: {fit_counts['sehr_passend']} sehr passend, {fit_counts['passend']} passend, {fit_counts['neutral']} neutral, {fit_counts['nicht_passend']} nicht passend"

            # Build and save analysis
            analysis = WatchlistCheckerAnalysis(
                summary=summary,
                full_text=full_text,
                fit_counts=fit_counts,
                position_fits_json=position_fits_json,
                skill_name=selected_skill.name if selected_skill else "",
                model=self.model,
                created_at=datetime.now(),
            )
            self._wc_repo.save_analysis(analysis)

            # Log to agent_runs
            self._agent_runs_repo.log_run(
                agent_name="watchlist_checker",
                model=self.model,
                output_summary=f"Checked {len(watchlist_positions)} positions: {fit_counts['sehr_passend']} sehr passend, {fit_counts['passend']} passend",
                context_summary=f"Skill: {selected_skill.name if selected_skill else 'Standard'}",
            )

        return WatchlistCheckResult(
            position_fits=fits,
            full_text=full_text,
        )


# ------------------------------------------------------------------
# Parsing helpers
# ------------------------------------------------------------------


def _parse_watchlist_results(
    watchlist_positions: list[Position],
    response: str,
) -> list[WatchlistFit]:
    """Extract structured verdicts from LLM response."""
    fits = []

    # Build a quick lookup for positions by name/ticker
    pos_lookup = {pos.ticker.upper(): pos for pos in watchlist_positions}
    pos_lookup.update({pos.name.lower(): pos for pos in watchlist_positions})

    lines = response.split("\n")
    current_pos_id = None
    verdict = None
    summary_lines = []

    for line in lines:
        line_stripped = line.strip()

        # Header "## NAME (TICKER)"
        if line_stripped.startswith("##") and "(" in line_stripped:
            # Save previous result
            if current_pos_id is not None and verdict is not None:
                summary = " ".join(summary_lines).strip()
                fits.append(
                    WatchlistFit(
                        position_id=current_pos_id,
                        verdict=verdict,
                        summary=summary,
                    )
                )

            # Parse new position
            header = line_stripped.replace("##", "").strip()
            # Extract ticker from "NAME (TICKER)" or "NAME (TICKER) (ASSET_CLASS)" format
            # Test all bracketed candidates (first match wins)
            if "(" in header and ")" in header:
                candidates = re.findall(r'\(([^)]+)\)', header)
                pos = None
                for candidate in candidates:
                    pos = pos_lookup.get(candidate.upper())
                    if pos:
                        break

                if pos:
                    current_pos_id = pos.id
                    verdict = None
                    summary_lines = []

        # Verdict line "**Fit:** {AMPEL}"
        elif "**Fit:**" in line_stripped and current_pos_id is not None:
            # Extract verdict emoji and text
            rest = line_stripped.replace("**Fit:**", "").strip()
            if "🟢" in rest:
                verdict = "sehr_passend"
            elif "🟡" in rest:
                verdict = "passend"
            elif "⚪" in rest:
                verdict = "neutral"
            elif "🔴" in rest:
                verdict = "nicht_passend"
            else:
                verdict = "unknown"

        # Summary lines (after ">")
        elif current_pos_id is not None and line_stripped.startswith(">"):
            summary_lines.append(line_stripped[1:].strip())
        elif current_pos_id is not None and line_stripped and not line_stripped.startswith("##") and not line_stripped.startswith("**"):
            # Accumulate body text
            if line_stripped not in ["---", ""]:
                summary_lines.append(line_stripped)

    # Save last result
    if current_pos_id is not None and verdict is not None:
        summary = " ".join(summary_lines).strip()
        fits.append(
            WatchlistFit(
                position_id=current_pos_id,
                verdict=verdict,
                summary=summary,
            )
        )

    return fits
