"""
Portfolio Comment Service — generates stylized financial commentary on portfolio analysis results.

Uses local Ollama LLM for privacy (portfolio data stays local).
Provides multiple comment styles with different personalities and tones.
Reusable across different contexts (portfolio story, position analysis, etc.).
"""

import asyncio
import logging
from typing import Optional

from core.llm.base import Message, Role
from core.llm.local import OllamaProvider
from core.storage.usage import UsageRepository

logger = logging.getLogger(__name__)


# Predefined comment styles — easily extensible
COMMENT_STYLES = [
    {
        "id": "humorvoll",
        "name": "Humorvoll",
        "emoji": "😄",
        "instruction": "Antworte witzig und humorvoll. Nutze Ironie und lockere Sprache. Bleib dabei respektvoll aber unterhaltsam.",
    },
    {
        "id": "freundlich",
        "name": "Freundlich-Analytisch",
        "emoji": "🤝",
        "instruction": "Antworte freundlich, sachlich und aufbauend. Fokussiere auf Stärken und konstruktive Hinweise.",
    },
    {
        "id": "kostolany",
        "name": "André Kostolany",
        "emoji": "🎲",
        "instruction": "Antworte im Stil von André Kostolany. Verwende seine typischen Metaphern über Spekulation, Geduld und Psychologie. Sei provokant und weise zugleich.",
    },
    {
        "id": "buffett",
        "name": "Warren Buffett",
        "emoji": "💎",
        "instruction": "Antworte im Stil von Warren Buffett. Fokus auf Fundamentals, langfristiges Denken, einfache Wahrheiten. Nutze seine typischen Analogien (Supermarkt, Circle of Competence).",
    },
    {
        "id": "sarkastisch",
        "name": "Sarkastisch-Weise",
        "emoji": "😏",
        "instruction": "Antworte sanft sarkastisch aber weise. Zeige mit einem Augenzwinkern die Schwächen auf, ohne gemein zu sein.",
    },
    {
        "id": "analytisch",
        "name": "Kritischer Analyst",
        "emoji": "🔬",
        "instruction": "Antworte wie ein nüchterner, kritischer Analyst. Faktenorientiert, keine Emotion, klare Schlussfolgerungen. Nenne Risiken explizit.",
    },
]


class PortfolioCommentService:
    """Service for generating stylized commentary on portfolio analysis results."""

    def __init__(
        self,
        host: str,
        model: str,
        usage_repo: Optional[UsageRepository] = None,
    ):
        """
        Initialize the service.

        Args:
            host: Ollama host (e.g., 'http://localhost:11434')
            model: Ollama model to use
            usage_repo: Optional UsageRepository for tracking token usage
        """
        self._host = host
        self._model = model
        self._usage_repo = usage_repo

    def generate_comment(
        self,
        context: str,
        style_id: str = "humorvoll",
    ) -> str:
        """
        Generate a stylized comment on the given context (sync wrapper).

        Args:
            context: Portfolio analysis context (storycheck result, verdicts, etc.)
            style_id: Comment style ID (see COMMENT_STYLES)

        Returns:
            Generated comment string
        """
        return asyncio.run(self._generate_comment_async(context, style_id))

    async def _generate_comment_async(
        self,
        context: str,
        style_id: str,
    ) -> str:
        """
        Async implementation of comment generation.
        Uses temperature=0.9 for creative, non-deterministic responses.
        """
        style = get_style_by_id(style_id)

        llm = OllamaProvider(host=self._host, model=self._model)

        # Wire usage tracking if repo provided
        if self._usage_repo:
            repo, model = self._usage_repo, self._model

            def _on_usage(inp, out, skill=None, dur=None, pos=None, cache_read=None, cache_write=None, web_search=None):
                repo.record(
                    "portfolio_comment",
                    model,
                    inp,
                    out,
                    skill=style_id,
                    source="manual",
                    duration_ms=dur,
                    cache_read_tokens=cache_read,
                    cache_write_tokens=cache_write,
                    web_search_requests=web_search,
                )

            llm.on_usage = _on_usage

        llm.skill_context = style_id

        prompt = (
            f"Du bist ein Finanz-Kommentator. {style['instruction']}\n\n"
            f"Gib einen kurzen Kommentar (3–5 Sätze) auf Basis dieses "
            f"Portfolio-Storycheck-Ergebnisses:\n\n{context}\n\n"
            "Antworte nur mit dem Kommentar, keine Überschrift."
        )

        messages = [Message(role=Role.USER, content=prompt)]
        return await llm.chat(messages, max_tokens=300, temperature=0.9)


# Public helpers for settings page and other components
def get_style_by_id(style_id: str) -> dict:
    """Get a comment style by ID, fallback to first style if not found."""
    return next(
        (s for s in COMMENT_STYLES if s["id"] == style_id),
        COMMENT_STYLES[0],
    )


def get_style_options() -> list[dict]:
    """Get all available comment styles."""
    return COMMENT_STYLES
