"""
FundamentalAgent — estimates fair value and over/under-valuation of portfolio positions.

Uses Claude + web search to find current valuation multiples (P/E, P/B, EV/EBITDA),
compare them to sector averages, and produce a simple DCF-based fair value estimate.

Verdict values:
  unterbewertet  — trading significantly below fair value → 🟢
  fair           — trading near fair value → 🟡
  überbewertet   — trading above fair value → 🔴
  unbekannt      — insufficient data for reliable valuation

Storage: reuses position_analyses table (agent='fundamental').
"""

from __future__ import annotations

import asyncio
import re
from typing import List, Optional, Tuple

from core.llm.claude import ClaudeProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.models import Position

AGENT_NAME = "fundamental"

VALID_VERDICTS = {"unterbewertet", "fair", "überbewertet", "unbekannt"}

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """You are a fundamental equity analyst. Your job is to assess whether a stock is undervalued, fairly valued, or overvalued based on quantitative valuation metrics.

## Methodology
For each position, research and apply as many of the following as data allows:

1. **P/E-Bewertung** — Current P/E vs. 5-year average, sector average, and S&P 500 average
2. **P/B-Bewertung** — Price-to-Book vs. sector average (especially relevant for banks, insurers)
3. **EV/EBITDA** — Enterprise value vs. EBITDA, compare to sector peers
4. **DCF-Schätzung** — Simple DCF: use analyst consensus revenue/earnings growth for next 3–5 years, apply a discount rate of 8–10%, estimate terminal value
5. **Analystenkursziele** — Consensus price target vs. current price (upside/downside %)
6. **PEG-Ratio** — P/E relative to growth rate (< 1 = potentially undervalued)
7. **Dividendenrendite** — For dividend stocks: current yield vs. historical average

## Verdict Criteria
- **unterbewertet**: Multiple metrics indicate >20% discount to fair value. Strong case for upside.
- **fair**: Trading within ±15% of estimated fair value. No clear directional signal.
- **überbewertet**: Multiple metrics indicate >20% premium to fair value. Limited upside or downside risk.
- **unbekannt**: Insufficient public data, pre-revenue company, or extremely difficult to value (some commodities, cryptos).

## Output Format (REQUIRED — machine-parsed)
For EACH position, output EXACTLY this block:

POSITION: [ID]
VERDICT: [unterbewertet|fair|überbewertet|unbekannt]
FAIR_VALUE_EUR: [estimated fair value per share in EUR, or N/A]
UPSIDE_PCT: [estimated upside/downside as %, e.g. +24% or -18%, or N/A]
SUMMARY: [One sentence verdict with key metric]
ANALYSIS:
[3–5 sentences covering: key metrics found, comparison to peers/history, fair value rationale, main risk to the valuation]
---

## Rules
- Use web_search to find current price, P/E, P/B, EV/EBITDA, analyst targets, and recent earnings
- Be specific: cite actual numbers, not vague assessments
- For precious metals or crypto: compare to historical price levels and use technical/supply analysis
- For fixed income or cash: output VERDICT: unbekannt (not equity-valued)
- Every position MUST get a verdict block
- Apply the valuation strategy skill below"""

POSITION_BLOCK_PATTERN = re.compile(
    r"POSITION:\s*(\d+)\s*\n"
    r"VERDICT:\s*(unterbewertet|fair|überbewertet|unbekannt)\s*\n"
    r"FAIR_VALUE_EUR:\s*(.+?)\s*\n"
    r"UPSIDE_PCT:\s*(.+?)\s*\n"
    r"SUMMARY:\s*(.+?)\s*\n"
    r"ANALYSIS:\s*\n(.*?)(?=\n---|\Z)",
    re.DOTALL | re.IGNORECASE,
)


class FundamentalAgent:
    """
    Cloud agent (Claude ☁️) — fundamental valuation of portfolio positions.
    Stores verdicts in position_analyses (agent='fundamental').
    """

    def __init__(self, llm: ClaudeProvider):
        self._llm = llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze_portfolio(
        self,
        positions: List[Position],
        skill_name: str,
        skill_prompt: str,
        analyses_repo: PositionAnalysesRepository,
    ) -> List[Tuple[int, str, str]]:
        """
        Analyse all eligible positions. Returns list of (position_id, verdict, summary).
        Verdicts are persisted in position_analyses.
        """
        # Only positions with tickers are fundamentally analysable
        eligible = [p for p in positions if p.ticker and p.id is not None]
        if not eligible:
            return []

        system = ANALYSIS_SYSTEM_PROMPT + f"\n\n## Bewertungs-Skill\n{skill_prompt}"
        all_results: List[Tuple[str, str, str, str, str, str]] = []

        # Process in batches of 2 — fundamental analysis is token-heavy
        batch_size = 2
        for i in range(0, len(eligible), batch_size):
            batch = eligible[i: i + batch_size]
            positions_text = self._format_positions(batch)
            user_msg = (
                f"Analysiere die Fundamentalbewertung dieser Positionen.\n\n{positions_text}"
            )
            response = await self._llm.chat_with_tools(
                messages=[{"role": "user", "content": user_msg}],
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                system=system,
                max_tokens=4096,
            )
            all_results.extend(self._parse_verdicts(response.content or ""))

            if i + batch_size < len(eligible):
                await asyncio.sleep(5)

        # Persist verdicts; embed fair value + upside in summary
        output: List[Tuple[int, str, str]] = []
        for pos_id_str, verdict, fair_value, upside, summary, analysis in all_results:
            if verdict not in VALID_VERDICTS:
                continue
            try:
                pos_id = int(pos_id_str)
            except ValueError:
                continue

            # Enrich summary with fair value / upside if available
            rich_summary = summary
            extras = []
            if fair_value and fair_value.upper() != "N/A":
                extras.append(f"Fair Value: {fair_value} €")
            if upside and upside.upper() != "N/A":
                extras.append(f"Upside: {upside}")
            if extras:
                rich_summary = f"{summary} ({', '.join(extras)})"

            analyses_repo.save(
                position_id=pos_id,
                agent=AGENT_NAME,
                skill_name=skill_name,
                verdict=verdict,
                summary=rich_summary,
            )
            output.append((pos_id, verdict, rich_summary))

        return output

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_positions(self, positions: List[Position]) -> str:
        lines = []
        for p in positions:
            lines.append(f"### Position ID: {p.id}")
            lines.append(f"**Name:** {p.name}")
            lines.append(f"**Ticker:** {p.ticker}")
            lines.append(f"**Asset-Klasse:** {p.asset_class}")
            if p.anlageart:
                lines.append(f"**Anlage-Art:** {p.anlageart}")
            if p.purchase_price:
                lines.append(f"**Kaufpreis:** {p.purchase_price:.2f} €")
            if p.purchase_date:
                lines.append(f"**Kaufdatum:** {p.purchase_date.isoformat()}")
            if p.story:
                lines.append(f"**Investment-These:** {p.story}")
            lines.append("")
        return "\n".join(lines)

    def _parse_verdicts(
        self, text: str
    ) -> List[Tuple[str, str, str, str, str, str]]:
        """Parse structured verdict blocks: (pos_id, verdict, fair_value, upside, summary, analysis)."""
        results = []
        for m in POSITION_BLOCK_PATTERN.finditer(text):
            results.append((
                m.group(1).strip(),   # pos_id
                m.group(2).strip().lower(),  # verdict
                m.group(3).strip(),   # fair_value_eur
                m.group(4).strip(),   # upside_pct
                m.group(5).strip(),   # summary
                m.group(6).strip(),   # analysis
            ))
        return results
