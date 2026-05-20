"""
Dividend Calendar Agent — qualitative analysis of dividend portfolio.

Local-only (OllamaProvider). One-shot run, no sessions, no DB persistence.
Inputs: 12-month cashflow forecast + portfolio valuations with dividend data.
Output: qualitative summary of portfolio dividend quality.
"""

import logging
from dataclasses import dataclass

from core.llm.local import OllamaProvider
from core.dividend_calendar import MonthlyForecast, DividendContribution, get_top_contributors
from agents.agent_language import response_language_instruction

logger = logging.getLogger(__name__)


@dataclass
class DividendCalendarAnalysis:
    """Result of a dividend portfolio quality analysis."""
    full_text: str
    summary: str         # 1-sentence takeaway
    total_annual_eur: float
    monthly_avg_eur: float
    coverage_pct: float


_BASE_SYSTEM_PROMPT = """Du bist ein erfahrener Dividenden-Analyst der die Qualität eines Dividenden-Portfolios bewertet.

Du erhältst:
- Gesamte Jahresdividende und monatlichen Durchschnitt
- Top-Dividendenzahler mit ihren jährlichen Ausschüttungen
- Abdeckungsquote (% der Positionen mit Dividendendaten)
- Konzentration (Top-3 Zahler als % der Gesamtdividende)

Deine Analyse soll folgende Aspekte abdecken:
1. **Gesamtbild**: Wie hoch ist das passive Einkommenspotenzial? Realistisch einordnen.
2. **Konzentration**: Wie abhängig ist das Portfolio von einzelnen Zahlern?
3. **Diversifikation**: Sind die Dividenden über Assetklassen gestreut?
4. **Qualitätseinschätzung**: Sind die Hauptzahler etablierte, zuverlässige Dividendentitel?
5. **Empfehlung**: Konkrete Handlungsempfehlung (1-2 Sätze).

Format:
- Markdown mit Überschriften
- Am Ende eine Zeile: **Fazit:** [Ein-Satz-Zusammenfassung]
- Keine Spekulationen über zukünftige Dividendenkürzungen ohne Belege
- Keine Finanzberatung — nur Analyse"""


class DividendCalendarAgent:
    """Ollama-based agent for qualitative dividend portfolio analysis."""

    def __init__(self, llm: OllamaProvider) -> None:
        self._llm = llm

    async def analyze(
        self,
        forecasts: list[MonthlyForecast],
        valuations: list,  # list[PortfolioValuation]
        language: str = "de",
    ) -> DividendCalendarAnalysis:
        """Analyze dividend portfolio quality.

        Args:
            forecasts: 12-month cashflow forecast from compute_monthly_cashflow_forecast
            valuations: full PortfolioValuation list (for context)
            language: "de" or "en"

        Returns:
            DividendCalendarAnalysis with full_text and summary
        """
        total_annual = sum(
            c.annual_dividend_eur
            for c in (forecasts[0].contributions if forecasts else [])
        )
        monthly_avg = total_annual / 12 if total_annual > 0 else 0.0

        portfolio_count = sum(
            1 for v in valuations
            if v.in_portfolio and not v.analysis_excluded
        )
        paying_count = len(forecasts[0].contributions) if forecasts else 0
        coverage_pct = round(paying_count / portfolio_count * 100, 1) if portfolio_count else 0.0

        top = get_top_contributors(forecasts, top_n=5)
        top3_sum = sum(c.annual_dividend_eur for c in top[:3])
        concentration_pct = round(top3_sum / total_annual * 100, 1) if total_annual > 0 else 0.0

        context = self._build_context(
            total_annual=total_annual,
            monthly_avg=monthly_avg,
            coverage_pct=coverage_pct,
            concentration_pct=concentration_pct,
            top_contributors=top,
        )

        system_prompt = _BASE_SYSTEM_PROMPT + "\n\n" + response_language_instruction(language)

        logger.info(
            "DividendCalendarAgent: analyzing %d paying positions, total annual EUR %.0f",
            paying_count,
            total_annual,
        )

        full_text = await self._llm.complete(
            prompt=context,
            system=system_prompt,
            max_tokens=2048,
        )

        summary = self._extract_summary(full_text)

        return DividendCalendarAnalysis(
            full_text=full_text,
            summary=summary,
            total_annual_eur=total_annual,
            monthly_avg_eur=monthly_avg,
            coverage_pct=coverage_pct,
        )

    def _build_context(
        self,
        total_annual: float,
        monthly_avg: float,
        coverage_pct: float,
        concentration_pct: float,
        top_contributors: list[DividendContribution],
    ) -> str:
        lines = [
            "## Dividenden-Portfolio Übersicht",
            "",
            f"- Jährliche Gesamtdividende: **{total_annual:,.0f} EUR**",
            f"- Monatlicher Durchschnitt: **{monthly_avg:,.0f} EUR**",
            f"- Abdeckung: **{coverage_pct:.1f}%** der Positionen haben Dividendendaten",
            f"- Konzentration Top-3: **{concentration_pct:.1f}%** der Gesamtdividende",
            "",
            "## Top-Dividendenzahler",
            "",
        ]

        if top_contributors:
            lines.append("| Position | Asset-Klasse | Jährlich (EUR) | Rendite |")
            lines.append("|----------|--------------|----------------|---------|")
            for c in top_contributors:
                yield_str = f"{c.dividend_yield_pct * 100:.1f}%" if c.dividend_yield_pct else "—"
                lines.append(f"| {c.name} ({c.symbol}) | {c.asset_class} | {c.annual_dividend_eur:,.0f} | {yield_str} |")
        else:
            lines.append("Keine Dividendenzahler im Portfolio.")

        lines.append("")
        lines.append("Bitte analysiere die Qualität dieses Dividenden-Portfolios.")

        return "\n".join(lines)

    def _extract_summary(self, full_text: str) -> str:
        """Extract the **Fazit:** line from the LLM response."""
        for line in full_text.splitlines():
            if "**Fazit:**" in line or "**Conclusion:**" in line:
                summary = line.replace("**Fazit:**", "").replace("**Conclusion:**", "").strip()
                if summary:
                    return summary
        # Fallback: first non-empty line that isn't a heading
        for line in full_text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("|"):
                return stripped[:200]
        return ""
