"""
Watchlist Checker Agent — evaluates which watchlist positions fit into the current portfolio.

Local-only (OllamaProvider). Runs once, no sessions.
Inputs: portfolio snapshot, watchlist positions with existing verdicts.
Output: per-position fit verdict + summary, full analysis text.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from core.llm.base import Message, Role
from core.llm.local import OllamaProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.models import Position

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

Sei direkt und konkret. Keine Allgemeinplätze. Antworte auf Deutsch.
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
    ) -> None:
        self._positions = positions_repo
        self._analyses = analyses_repo
        self._llm = llm

    @property
    def model(self) -> str:
        return self._llm.model

    async def check_watchlist(
        self,
        portfolio_snapshot: str,
        watchlist_positions: list[Position],
        story_analysis_text: Optional[str] = None,
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

        # Add watchlist positions with any existing verdicts
        context_parts.extend(["", "## Watchlist-Positionen"])
        for pos in watchlist_positions:
            pos_line = f"- {pos.name} ({pos.ticker})"
            if pos.asset_class:
                pos_line += f" [{pos.asset_class}]"
            context_parts.append(pos_line)

            # Add any existing verdicts from other agents
            if pos.id:
                existing_verdicts = self._analyses.get_latest_bulk([pos.id], agent=None)
                if existing_verdicts:
                    for av in existing_verdicts:
                        agent_name = av["agent"].capitalize()
                        verdict = av.get("verdict", "?")
                        context_parts.append(f"  - {agent_name}: {verdict}")

        context = "\n".join(context_parts)

        # LLM call (combine system prompt with context, send as user message)
        messages = [
            Message(role=Role.USER, content=f"{BASE_SYSTEM_PROMPT}\n\n{context}")
        ]

        response = await self._llm.chat(messages)
        full_text = response

        # Parse and persist results
        fits = _parse_watchlist_results(watchlist_positions, response)
        for fit in fits:
            self._analyses.save(
                position_id=fit.position_id,
                agent="watchlist_checker",
                skill_name="",  # Watchlist checker is not skill-based
                verdict=fit.verdict,
                summary=fit.summary,
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
            # Extract ticker from "NAME (TICKER)" format
            if "(" in header and ")" in header:
                ticker = header[header.rfind("(") + 1 : header.rfind(")")].strip()
                pos = pos_lookup.get(ticker.upper())
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
