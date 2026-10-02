"""
Position Story Service — generates investment theses for individual positions.

Encapsulates LLM calls with proper usage tracking and configuration management.
Replaces inline _generate_story_proposal() calls from pages.
"""

import asyncio
import logging
import re
from datetime import date
from typing import Callable, Optional

from core.llm.base import LLMProvider
from core.constants import WEB_SEARCH_TYPE

logger = logging.getLogger(__name__)

# Ohne Suche schreibt das Modell aus seinem Trainingsstand: Abspaltungen,
# Uebernahmen und Kursbewegungen danach fehlen (Kongsberg, Samsung, 02.10.2026).
WEB_SEARCH_TOOL = {"type": WEB_SEARCH_TYPE, "name": "web_search", "max_uses": 3}


def _these_aus(text: str) -> str:
    """Nur die These: Der Text aller Suchrunden kommt gesammelt zurueck,
    Zwischensaetze wie "Ich suche ..." gehoeren nicht in die Story."""
    treffer = re.findall(r"<these>(.*?)</these>", text, flags=re.DOTALL)
    return (treffer[-1] if treffer else text).strip()


class PositionStoryService:
    """Service for generating and updating investment theses for positions."""

    def __init__(self, provider_factory: Callable[[], LLMProvider]):
        """provider_factory baut je Aufruf den Provider -- so wirkt eine neue
        Modellwahl in den Einstellungen ohne Neustart, und Routing (Anthropic,
        OpenRouter, DeepSeek) und Verbrauch laufen wie bei allen Cloud-Agenten."""
        self._provider_factory = provider_factory

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
        llm = self._provider_factory()

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

        heute = date.today()
        system = (
            "Du bist ein erfahrener Investmentanalyst. "
            f"Heute ist der {heute:%d.%m.%Y}. Dein Trainingswissen ist veraltet: "
            "Suche zuerst im Web nach den wichtigsten Entwicklungen der letzten zwölf "
            "Monate (Abspaltungen, Übernahmen, Umbauten, Kursentwicklung seit "
            "Jahresbeginn, Ergebnisse, Ausblick) und stütze die These auf diesen Stand. "
            "Passt etwas in einer bestehenden These nicht mehr, korrigiere es."
        )
        prompt = (
            f"Position:\n{info}\n\n"
            f"{task}\n\n"
            "Die These soll erklären: warum diese Position interessant ist, "
            "was die Kernthese ist (Wachstum, Value, Dividende, Absicherung …) "
            "und welche wichtigen Katalysatoren oder Risiken bestehen. "
            "Schreib die fertige These zwischen <these> und </these> – ohne "
            "Einleitung, Überschrift oder Quellenangaben."
        )

        # Websuche laeuft in beiden Providern intern (Anthropic nativ, sonst Tavily);
        # zurueck kommt nur der Text. Grosszuegiges Budget: Suche und Denken
        # verbrauchen Tokens -- bei 400 blieb die Antwort leer und loeschte die Story.
        response = await llm.chat_with_tools(
            messages=[{"role": "user", "content": prompt}],
            tools=[WEB_SEARCH_TOOL],
            system=system,
            max_tokens=4000,
        )
        result = _these_aus(response.content or "")
        if not result:
            modell = getattr(llm, "_model", "")
            raise RuntimeError(
                f"Das Modell {modell} hat keinen Text geliefert – die bestehende Story bleibt unverändert."
            )

        return result
