"""
Portfolio Robustness Agent — finds systemic risks in the overall portfolio composition.

Local Ollama (private 🔒 — no data leaves the machine).
Analyzes portfolio-level concentration, correlation, and diversification gaps
without web search — pure structural analysis from training knowledge.

Verdict values (robustness of the overall portfolio):
  robust      — well diversified, no major systemic risks
  angreifbar  — some concentration or correlation concerns worth monitoring
  fragil      — significant structural risk (concentration, missing diversification)
  kritisch    — major systemic exposure requiring portfolio review

Output: PortfolioRobustnessAnalysis with verdict + summary + full_text.
"""

from __future__ import annotations

import logging
import re

from core.llm.local import OllamaProvider
from core.storage.models import PortfolioRobustnessAnalysis

logger = logging.getLogger(__name__)

AGENT_NAME = "portfolio_robustness"
VALID_VERDICTS = {"robust", "angreifbar", "fragil", "kritisch"}

_VERDICT_SYMBOLS = {
    "robust":      "🟢",
    "angreifbar":  "🟡",
    "fragil":      "🟠",
    "kritisch":    "🔴",
}

_ANALYSIS_PROMPT_DE = """Du bist ein kritischer Portfolio-Risikoanalyst. Analysiere dieses Portfolio aus der Perspektive eines Gegenanalysten.

Untersuche diese 5 Dimensionen:

1. **Konzentrations-Risiko**: Ist eine einzelne Position >15% des Portfolios? Ist ein Sektor >30%?
   Ist eine Asset-Klasse unverhältnismäßig dominant?

2. **Korrelations-Risiko**: Welche Positionen bewegen sich wahrscheinlich gleich (gleicher Sektor, Region, Makro-Faktor)?
   Was passiert wenn der US-Markt 30% fällt? Was wenn Zinsen stark steigen?

3. **Diversifikations-Lücken**: Was fehlt? Rohstoffe, Anleihen, Immobilien, internationale Märkte?
   Gibt es blinde Flecken in der geografischen Verteilung?

4. **Verdicts-Aggregation**: Wie viele Positionen haben schlechte Verdicts (fragwürdig, destruktiv, fragil, kritisch)?
   Wo häufen sich negative Signale?

5. **Makro-Sensitivität**: Wie sensibel ist das Portfolio gegenüber Zinsänderungen, Währungsrisiken, Konjunkturabschwung?

Antworte IMMER in diesem exakten Format:

## Portfolio-Gegenanalyse
**Robustheit:** Schreibe NUR EINES: 🟢 Robust ODER 🟡 Angreifbar ODER 🟠 Fragil ODER 🔴 Kritisch
> {{EIN-SATZ-ZUSAMMENFASSUNG des größten Risikos}}

### Stärkste Gegenargumente
{{3-5 spezifische, konkrete Risiken mit Begründung}}

### Blinde Flecken
{{Was übersieht dieses Portfolio? Was fehlt?}}

### Was bei einem Crash passiert
{{Wie würde dieses Portfolio in einem -30% Marktumfeld performen?}}

---

Portfolio-Daten:
{portfolio_snapshot}

Bisherige Analysen (SC/CG/FA Verdicts):
{position_verdicts}"""

_ANALYSIS_PROMPT_EN = """You are a critical portfolio risk analyst. Analyze this portfolio from a contrarian perspective.

Examine these 5 dimensions:

1. **Concentration Risk**: Is any single position >15% of the portfolio? Is any sector >30%?
   Is any asset class disproportionately dominant?

2. **Correlation Risk**: Which positions likely move together (same sector, region, macro factor)?
   What happens if the US market drops 30%? What if interest rates rise sharply?

3. **Diversification Gaps**: What's missing? Commodities, bonds, real estate, international markets?
   Are there blind spots in geographic distribution?

4. **Verdict Aggregation**: How many positions have poor verdicts?
   Where are negative signals clustering?

5. **Macro Sensitivity**: How sensitive is the portfolio to rate changes, currency risks, economic downturns?

Always respond in this exact format:

## Portfolio Counter-Analysis
**Robustness:** Write ONLY ONE: 🟢 Robust OR 🟡 Vulnerable OR 🟠 Fragile OR 🔴 Critical
> {{ONE-SENTENCE-SUMMARY of the biggest risk}}

### Strongest Counter-Arguments
{{3-5 specific, concrete risks with reasoning}}

### Blind Spots
{{What does this portfolio overlook? What's missing?}}

### What happens in a crash
{{How would this portfolio perform in a -30% market environment?}}

---

Portfolio data:
{portfolio_snapshot}

Existing analyses (SC/CG/FA verdicts):
{position_verdicts}"""


class PortfolioRobustnessAgent:
    """
    Local Ollama agent (private 🔒) — portfolio-level structural risk analysis.
    No web search — purely structural analysis of portfolio composition.
    """

    def __init__(self, llm: OllamaProvider):
        self._llm = llm

    @property
    def model(self) -> str:
        return self._llm.model

    async def analyze(
        self,
        portfolio_snapshot: str,
        position_verdicts: str,
        language: str = "de",
        position_count: int = 0,
    ) -> PortfolioRobustnessAnalysis:
        """
        Analyze portfolio composition for systemic risks.
        Returns PortfolioRobustnessAnalysis with verdict + summary + full_text.
        """
        self._llm.skill_context = "portfolio_robustness"

        template = _ANALYSIS_PROMPT_DE if language == "de" else _ANALYSIS_PROMPT_EN
        prompt = template.format(
            portfolio_snapshot=portfolio_snapshot or "(keine Daten)",
            position_verdicts=position_verdicts or "(keine Verdicts vorhanden)",
        )

        try:
            reply = await self._llm.complete(prompt, max_tokens=1500)
        except Exception as exc:
            logger.warning("portfolio_robustness: LLM error: %s", exc)
            reply = ""

        verdict = _extract_verdict(reply)
        summary = _extract_summary(reply)

        return PortfolioRobustnessAnalysis(
            verdict=verdict,
            summary=summary,
            analysis_text=reply or "(Analyse fehlgeschlagen)",
            position_count=position_count,
            created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )


# ------------------------------------------------------------------
# Parsing helpers
# ------------------------------------------------------------------

def _extract_verdict(text: str) -> str:
    """Extract verdict from structured LLM response."""
    # Look for the verdict line and map by symbol
    symbol_map = {"🟢": "robust", "🟡": "angreifbar", "🟠": "fragil", "🔴": "kritisch"}
    for line in text.split("\n"):
        if "Robustheit" in line or "Robustness" in line:
            for sym, verdict in symbol_map.items():
                if sym in line:
                    return verdict
    # fallback: first symbol found anywhere
    for sym, verdict in symbol_map.items():
        if sym in text:
            return verdict
    # text fallback (priority: worst first so first match wins)
    lower = text.lower()
    for word, verdict in [
        ("kritisch", "kritisch"), ("critical", "kritisch"),
        ("fragil", "fragil"), ("fragile", "fragil"),
        ("angreifbar", "angreifbar"), ("vulnerable", "angreifbar"),
        ("robust", "robust"),
    ]:
        if word in lower:
            return verdict
    return "angreifbar"


def _extract_summary(text: str) -> str:
    """Extract one-sentence summary from the > quote line."""
    m = re.search(r"^>\s*(.+)$", text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    # fallback: first non-empty line after the verdict line
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for i, line in enumerate(lines):
        if any(sym in line for sym in ["🟢", "🟡", "🟠", "🔴"]):
            if i + 1 < len(lines):
                return lines[i + 1]
    return "Portfolio-Robustheit analysiert."
