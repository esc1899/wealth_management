"""
Tax Loss Harvesting Agent — identifiziert Verlustpositionen für steueroptimiertes Jahresend-Verkaufen.

Local-only (OllamaProvider). Stateless — kein Session-Management, keine DB-Persistenz.
Inputs: pre-gefilterte Verlustpositionen + Watchlist-Kandidaten + bestehende Verdicts.
Output: Markdown-Report mit Empfehlungen, Steuer-Impact-Berechnung, Wash-Sale-Warnungen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from agents.agent_language import response_language_instruction
from agents.market_data_agent import PortfolioValuation
from core.llm.base import Message, Role
from core.llm.local import OllamaProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.models import Position

logger = logging.getLogger(__name__)

_ABGELTUNGSTEUER = 0.26375  # inkl. Solidaritätszuschlag


# ------------------------------------------------------------------
# Output model
# ------------------------------------------------------------------


@dataclass
class TaxLossHarvestingResult:
    total_loss_eur: float
    total_tax_benefit_eur: float
    candidate_count: int
    wash_sale_tickers: list[str]
    report_markdown: str
    generated_at: datetime = field(default_factory=datetime.now)


# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

_SYSTEM_PROMPT = """Du bist ein Tax Loss Harvesting Assistent für deutsche Anleger.

AUFGABE: Analysiere die gegebenen Verlustpositionen und erstelle konkrete Empfehlungen für strategisches Jahresend-Verkaufen.

KONTEXT:
- Abgeltungssteuer in Deutschland: 26,375% (inkl. Solidaritätszuschlag)
- Realisierte Verluste können mit realisierten Gewinnen verrechnet werden
- Wash-Sale-Risiko (Deutschland): Identische Wertpapiere nicht sofort zurückkaufen (30 Tage Mindestabstand empfohlen)

Du erhältst:
1. Verlustpositionen: Name, Ticker, Anlageklasse, Einstandswert, aktueller Wert, unrealisierter Verlust, Verlust%
2. Watchlist-Kandidaten: potenzielle Ersatz-Positionen mit vorhandenen Analyse-Verdicts
3. Wash-Sale-Warnungen: Ticker die sowohl im Portfolio-Verlust als auch auf der Watchlist sind

ANALYSE PRO VERLUSTPOSITION:
- Empfehlung: "Verkaufen + Ersetzen" | "Verkaufen (kein Ersatz)" | "Halten"
- Begründung: Warum lohnt sich der Verlust oder nicht? (Qualität, Erholungspotenzial, Steuer-Impact)
- Ersatz-Kandidaten aus der Watchlist (gleiche Anlageklasse, ähnliche Rolle, kein Wash-Sale-Risiko)

OUTPUT-FORMAT (Markdown):

## 🎯 Tax Loss Harvesting Analyse

### Verlustpositionen

**{Name}** ({Ticker}) — Verlust: €{X} ({Y}%)
- Steuerersparnis bei Realisierung: ~€{Z}
- Empfehlung: {Verkaufen + Ersetzen | Verkaufen | Halten}
- Begründung: {2–3 Sätze}
- Ersatz-Kandidaten: {Name (Ticker) — 1-Satz-Begründung} oder "–"

---

### ⚠️ Wash-Sale Warnungen
{Wenn vorhanden: Ticker + Erklärung, sonst: "Keine Wash-Sale-Risiken erkannt."}

### 💰 Zusammenfassung
- Positionen zur Realisierung empfohlen: {N}
- Gesamtverlust (Kandidaten): €{X}
- Mögliche Steuerersparnis: ~€{Y}

**Hinweis:** Dies ist keine Steuerberatung. Bitte konsultiere einen Steuerberater vor Umsetzung.

Sei direkt und konkret. Erkläre Empfehlungen kurz und klar."""


# ------------------------------------------------------------------
# Agent
# ------------------------------------------------------------------


class TaxLossHarvestingAgent:
    """
    Local Ollama agent for tax loss harvesting analysis.
    Stateless — no session management, no DB persistence.
    """

    def __init__(self, llm: OllamaProvider) -> None:
        self._llm = llm

    @property
    def model(self) -> str:
        return self._llm.model

    async def analyze(
        self,
        loss_positions: list[PortfolioValuation],
        watchlist_positions: list[Position],
        verdicts: dict[str, dict[int, object]],
        wash_sale_tickers: list[str],
        language: str = "de",
    ) -> TaxLossHarvestingResult:
        """Generate tax loss harvesting report from pre-filtered loss positions."""
        total_loss = sum(abs(v.pnl_eur) for v in loss_positions if v.pnl_eur is not None)
        tax_benefit = total_loss * _ABGELTUNGSTEUER

        if not loss_positions:
            return TaxLossHarvestingResult(
                total_loss_eur=0.0,
                total_tax_benefit_eur=0.0,
                candidate_count=0,
                wash_sale_tickers=[],
                report_markdown="Keine Verlustpositionen über dem Schwellwert gefunden.",
            )

        self._llm.skill_context = "tax_loss_harvesting"

        context = _build_context(loss_positions, watchlist_positions, verdicts, wash_sale_tickers)
        system_prompt = _SYSTEM_PROMPT + "\n\n" + response_language_instruction(language)

        messages = [Message(role=Role.USER, content=f"{system_prompt}\n\n{context}")]
        response = await self._llm.chat(messages, max_tokens=4096)

        return TaxLossHarvestingResult(
            total_loss_eur=total_loss,
            total_tax_benefit_eur=tax_benefit,
            candidate_count=len(loss_positions),
            wash_sale_tickers=wash_sale_tickers,
            report_markdown=response,
        )


# ------------------------------------------------------------------
# Context builder
# ------------------------------------------------------------------


def _build_context(
    loss_positions: list[PortfolioValuation],
    watchlist_positions: list[Position],
    verdicts: dict[str, dict[int, object]],
    wash_sale_tickers: list[str],
) -> str:
    parts: list[str] = []

    parts.append("## Verlustpositionen (vorgefilterter Verlust über Schwellwert)\n")
    for v in sorted(loss_positions, key=lambda x: x.pnl_eur or 0):
        loss = abs(v.pnl_eur) if v.pnl_eur is not None else 0.0
        pct = abs(v.pnl_pct) if v.pnl_pct is not None else 0.0
        tax = loss * _ABGELTUNGSTEUER
        wash = " ⚠️ WASH-SALE-RISIKO" if v.symbol in wash_sale_tickers else ""
        cost = v.cost_basis_eur or 0.0
        current = v.current_value_eur or 0.0
        parts.append(
            f"- **{v.name}** ({v.symbol}) [{v.asset_class}]{wash}\n"
            f"  Einstand: €{cost:,.0f} | Aktuell: €{current:,.0f} | "
            f"Verlust: -€{loss:,.0f} (-{pct:.1f}%) | Steuerersparnis: ~€{tax:,.0f}"
        )

    parts.append("\n## Watchlist-Kandidaten (potenzielle Ersatz-Positionen)\n")
    if not watchlist_positions:
        parts.append("Keine Watchlist-Kandidaten vorhanden.")
    else:
        for p in watchlist_positions:
            line = f"- **{p.name}** ({p.ticker or '–'}) [{p.asset_class}]"
            pos_verdicts: list[str] = []
            if p.id:
                for agent_key, label in [
                    ("storychecker", "SC"),
                    ("consensus_gap", "CG"),
                    ("fundamental_analyzer", "FA"),
                ]:
                    v_map = verdicts.get(agent_key, {})
                    if p.id in v_map and v_map[p.id] and v_map[p.id].verdict:
                        pos_verdicts.append(f"{label}:{v_map[p.id].verdict}")
            if pos_verdicts:
                line += f" ({', '.join(pos_verdicts)})"
            parts.append(line)

    if wash_sale_tickers:
        parts.append(f"\n## ⚠️ Wash-Sale Warnungen\n")
        parts.append(
            "Folgende Ticker sind SOWOHL in den Verlustpositionen ALS AUCH auf der Watchlist. "
            "Bei Verkauf mindestens 30 Tage warten vor Rückkauf:\n"
        )
        for t in wash_sale_tickers:
            parts.append(f"- {t}")

    return "\n".join(parts)
