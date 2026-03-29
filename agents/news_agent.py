"""
News Agent — fetches and digests recent news for portfolio positions.

Flow per run_digest() call:
  1. Build list of tickers + names from caller
  2. Send a single Claude request with web_search to find news for each position
  3. Apply the skill-defined filter strategy (e.g. long-term investor, earnings focus)
  4. Return a formatted markdown digest
"""

from __future__ import annotations

from typing import Optional

from core.llm.claude import ClaudeProvider

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """You are an investment news analyst.
For each portfolio position provided, search for recent news (last 14 days) and assess its relevance.

For every position produce a section using EXACTLY this format:
## [TICKER] — [Company Name]
- Key news item 1 (date if known)
- Key news item 2
- **Assessment:** [🟢 No action needed / 🟡 Worth monitoring / 🔴 Review position]
- **Sources:** [title1](url1), [title2](url2)

Rules:
- Only include news that is relevant to the investment decision
- Skip positions where nothing noteworthy was found (note this briefly with 🟢 No action needed)
- Be concise: 2–4 news bullets per position maximum
- Always include a **Sources:** line with clickable markdown links to the articles you found
- Apply the filter strategy below when deciding what counts as relevant"""

# Server-side web search — Anthropic executes this, no client handling needed
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

# Allow enough iterations for multiple tickers
MAX_TOOL_ITERATIONS = 15


class NewsAgent:
    """
    Stateless agent: each call to run_digest() is independent.
    Uses Claude API + web search (cloud ☁️ — data is sent to Anthropic).
    """

    def __init__(self, llm: ClaudeProvider):
        self._llm = llm

    async def run_digest(
        self,
        tickers: list[str],
        ticker_names: Optional[dict[str, str]] = None,
        skill_name: str = "Long-term Investor",
        skill_prompt: str = "",
    ) -> str:
        """
        Run a news digest for the given tickers.

        Args:
            tickers:      List of ticker symbols (e.g. ["AAPL", "SAP.DE"])
            ticker_names: Optional map ticker → company name for better search context
            skill_name:   Display name of the skill being used
            skill_prompt: The skill prompt that defines the filter strategy
        """
        if not tickers:
            return "No positions found. Add positions in Portfolio Chat first."

        names = ticker_names or {}
        system = BASE_SYSTEM_PROMPT
        if skill_prompt:
            system += f"\n\n## Filter Strategy: {skill_name}\n{skill_prompt}"

        position_lines = "\n".join(
            f"- **{t}** ({names.get(t, t)})" for t in tickers
        )
        user_message = (
            f"Please search for recent news for the following portfolio positions "
            f"and produce a digest applying the filter strategy:\n\n{position_lines}"
        )

        response = await self._llm.chat_with_tools(
            messages=[{"role": "user", "content": user_message}],
            tools=[WEB_SEARCH_TOOL],
            system=system,
            max_tokens=8192,
        )
        return response.content or "No news digest generated."
