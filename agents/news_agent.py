"""
News Agent — fetches and digests recent news for portfolio positions.

Flow per start_run() call:
  1. Build list of tickers + names from caller
  2. Run the digest via web_search (cloud ☁️)
  3. Store run + user/assistant messages in DB
  4. Return (run, digest_text)

Flow per chat() call:
  1. Load run (for digest context) and message history from DB
  2. Send follow-up using Claude plain chat (no web_search)
  3. System prompt includes the original digest as reference
  4. Persist and return the assistant reply
"""

from __future__ import annotations
import logging


from typing import Optional, Tuple

from core.llm.base import Message, Role
from core.llm.claude import ClaudeProvider
from core.storage.models import NewsRun
from core.storage.news import NewsRepository


logger = logging.getLogger(__name__)
# ------------------------------------------------------------------
# System prompts
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

FOLLOWUP_SYSTEM_PROMPT = """You are an investment news analyst.
The user has received the following news digest for their portfolio and may have follow-up questions.

Answer based on the digest and your general knowledge. Be concise and specific.
If asked about a position not in the digest, say so clearly.

## News Digest
{digest}"""

# Server-side web search — Anthropic executes this, no client handling needed
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

# Allow enough iterations for multiple tickers
MAX_TOOL_ITERATIONS = 15


class NewsAgent:
    """
    Conversational agent: start_run() triggers the digest, chat() handles follow-ups.
    Uses Claude API + web search (cloud ☁️ — data is sent to Anthropic).
    """

    def __init__(self, llm: ClaudeProvider):
        self._llm = llm

    @property
    def model(self) -> str:
        return self._llm.model

    async def start_run(
        self,
        tickers: list[str],
        ticker_names: Optional[dict[str, str]],
        skill_name: str,
        skill_prompt: str,
        user_context: str,
        repo: NewsRepository,
    ) -> Tuple[NewsRun, str]:
        """
        Run a news digest, persist run + messages in DB, return (run, digest).

        Args:
            tickers:      List of ticker symbols
            ticker_names: Optional map ticker → company name
            skill_name:   Display name of the skill
            skill_prompt: The skill prompt defining the filter strategy
            user_context: Optional user focus ("Fokus auf Tech-Positionen")
            repo:         NewsRepository for persistence
        """
        self._llm.skill_context = skill_name
        self._llm.position_count = len(tickers)  # Track how many tickers in digest
        digest = await self._run_digest(tickers, ticker_names, skill_name, skill_prompt)
        run = repo.save_run(skill_name=skill_name, tickers=tickers, result=digest)

        user_message = user_context.strip() if user_context.strip() else (
            f"Please run a news digest for my portfolio using the '{skill_name}' strategy."
        )
        repo.add_message(run.id, "user", user_message)
        repo.add_message(run.id, "assistant", digest)
        return run, digest

    async def chat(
        self,
        run_id: int,
        user_message: str,
        repo: NewsRepository,
    ) -> str:
        """
        Answer a follow-up question about a news digest run.
        Uses plain Claude chat (no web_search) with the digest as context.

        Args:
            run_id:       ID of the news run
            user_message: The user's follow-up question
            repo:         NewsRepository for persistence

        Returns:
            Assistant reply string
        """
        run = repo.get_run(run_id)
        if run is None:
            raise ValueError(f"News run {run_id} not found")

        repo.add_message(run_id, "user", user_message)

        system = FOLLOWUP_SYSTEM_PROMPT.format(digest=run.result)
        history = repo.get_messages(run_id)
        # Skip the first two messages (initial user context + digest) — they're in the system prompt
        followup_history = history[2:] if len(history) > 2 else []

        messages = [Message(role=Role.SYSTEM, content=system)] + [
            Message(
                role=Role.USER if m.role == "user" else Role.ASSISTANT,
                content=m.content,
            )
            for m in followup_history
        ]

        reply = await self._llm.chat(messages, max_tokens=2048)
        repo.add_message(run_id, "assistant", reply)
        return reply

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_digest(
        self,
        tickers: list[str],
        ticker_names: Optional[dict[str, str]],
        skill_name: str,
        skill_prompt: str,
    ) -> str:
        """Execute the web-search digest and return the markdown result."""
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
            max_tokens=4096,
        )
        return response.content or "No news digest generated."
