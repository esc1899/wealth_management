"""
Position Story Service — generates investment theses for individual positions.

Encapsulates LLM calls with proper usage tracking and configuration management.
Replaces inline _generate_story_proposal() calls from pages.
"""

import asyncio
import logging
from typing import Optional

from core.constants import CLAUDE_HAIKU
from core.llm.claude import ClaudeProvider
from core.storage.usage import UsageRepository

logger = logging.getLogger(__name__)


class PositionStoryService:
    """Service for generating and updating investment theses for positions."""

    def __init__(
        self,
        api_key: str,
        usage_repo: Optional[UsageRepository] = None,
        model: Optional[str] = None,
        base_url: str = "",
        openai_api_key: str = "",
        openai_base_url: str = "",
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._openai_api_key = openai_api_key
        self._openai_base_url = openai_base_url
        self._usage_repo = usage_repo
        self._model = model or CLAUDE_HAIKU

    def generate_position_story(
        self,
        name: str,
        ticker: Optional[str] = None,
        asset_class: Optional[str] = None,
        existing_story: Optional[str] = None,
    ) -> str:
        """
        Generate an investment thesis for a position (sync wrapper).

        Args:
            name: Position name (company/fund name)
            ticker: Ticker symbol (optional)
            asset_class: Asset class (Aktie, Fonds, etc.)
            existing_story: Existing story to update (if any)

        Returns:
            Generated or updated investment thesis (2–4 sentences)
        """
        return asyncio.run(self._generate_position_story_async(name, ticker, asset_class, existing_story))

    async def _generate_position_story_async(
        self,
        name: str,
        ticker: Optional[str] = None,
        asset_class: Optional[str] = None,
        existing_story: Optional[str] = None,
    ) -> str:
        """
        Async implementation of position story generation.
        """
        if self._openai_base_url:
            from core.llm.openai_compatible import OpenAICompatibleProvider
            llm = OpenAICompatibleProvider(api_key=self._openai_api_key, model=self._model, base_url=self._openai_base_url)
        else:
            llm = ClaudeProvider(api_key=self._api_key, model=self._model, base_url=self._base_url)

        # Track position context for usage stats
        llm.skill_context = "position_story"
        llm.position_count = 1

        # Build position info
        info = f"Name: {name}\n"
        if asset_class:
            info += f"Asset-Klasse: {asset_class}\n"
        if ticker:
            info += f"Ticker: {ticker}"

        # Determine task based on whether we're creating or updating
        if existing_story:
            task = f"Aktualisiere und verbessere diese bestehende Investment-These:\n\n{existing_story}"
        else:
            task = "Schreibe eine prägnante Investment-These (2–4 Sätze)."

        # System prompt
        prompt = (
            f"Du bist ein erfahrener Investmentanalyst.\n\n"
            f"Position:\n{info}\n\n"
            f"{task}\n\n"
            "Die These soll erklären: warum diese Position interessant ist, "
            "was die Kernthese ist (Wachstum, Value, Dividende, Absicherung …) "
            "und welche wichtigen Katalysatoren oder Risiken bestehen. "
            "Antworte NUR mit der These, keine Einleitung, keine Überschrift."
        )

        # Generate story
        result = await llm.complete(prompt, max_tokens=400)

        # Track usage if repo provided
        if self._usage_repo:
            # Calculate approximate token count (rough estimate: 4 chars ≈ 1 token)
            input_tokens = len(prompt) // 4
            output_tokens = len(result) // 4
            self._usage_repo.record(
                agent="position_story_service",
                model=self._model,
                skill="position_story",
                source="manual",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                position_count=1,
            )

        return result
