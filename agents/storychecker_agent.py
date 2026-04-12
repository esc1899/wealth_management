"""
Story Checker Agent — checks if an investment thesis is still intact.

Cloud-only (ClaudeProvider). Watchlist positions only — no portfolio quantities
or purchase prices are passed to the API.

Uses Anthropic's built-in web search to find current news and data about the
company, then evaluates whether the original investment thesis still holds.

Persistent sessions: start_session() kicks off a new check, chat() allows
follow-up questions within the same session.

batch_check_all() runs all eligible positions sequentially (background thread).
"""

from __future__ import annotations
import logging


import asyncio
from typing import List, Tuple

from core.llm.claude import ClaudeProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.models import Position, StorycheckerSession
from core.storage.storychecker import StorycheckerRepository


logger = logging.getLogger(__name__)
# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------

# Server-side web search — Anthropic executes this, no client handling needed
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

MAX_TOOL_ITERATIONS = 8

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """Du bist ein kritischer Investment-Analyst der prüft ob eine Investment-These noch intakt ist.

Du erhältst:
- Name und Ticker des Unternehmens
- Die ursprüngliche Investment-These (Story) des Nutzers
- Optional: die verfolgte Anlage-Idee mit spezifischen Prüfkriterien

Deine Aufgabe: Nutze web_search um aktuelle Informationen zur Firma zu finden
(News, Quartalszahlen, Management-Aussagen, Wettbewerb). Beurteile dann ob die
These noch hält — nicht ob sie theoretisch "gut" ist, sondern ob sie heute noch zutrifft.

Antworte auf die erste Anfrage IMMER in diesem Format:

## Story-Check: {NAME} ({TICKER})
**Urteil:** {AMPEL}

> {EIN-SATZ-FAZIT}

### Was bestätigt die These
- ...

### Was schwächt die These
- ...

### Aktuelle Entwicklungen
- ...

### Fazit
{2–3 Sätze mit konkretem Urteil und Begründung.}

---

Ampel-Regeln (genau eines wählen):
- 🟢 **Intakt** — These hält stand, keine wesentlichen Gegenargumente
- 🟡 **Gemischt** — Teils bestätigt, teils geschwächt; Beobachtung empfohlen
- 🔴 **Gefährdet** — Wesentliche Thesen-Aspekte sind nicht mehr gültig oder neue Risiken

Sei direkt und konkret. Keine Allgemeinplätze. Antworte auf Deutsch.
Bei Rückfragen im Chat: kurz und präzise antworten, kein neues Ampel-Urteil."""


# ------------------------------------------------------------------
# Agent
# ------------------------------------------------------------------


class StorycheckerAgent:
    """
    Cloud agent that checks whether an investment thesis is still valid.
    Sessions are persisted in DB; supports multi-turn follow-up chat.
    """

    def __init__(
        self,
        positions_repo,
        storychecker_repo: StorycheckerRepository,
        analyses_repo: PositionAnalysesRepository,
        llm: ClaudeProvider,
        skills_repo=None,
    ) -> None:
        self._positions = positions_repo
        self._storychecker = storychecker_repo
        self._analyses = analyses_repo
        self._llm = llm
        self._skills_repo = skills_repo

    @property
    def model(self) -> str:
        return self._llm.model

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def start_session(self, position: Position) -> StorycheckerSession:
        """Create a new session and run the initial story check."""
        skill_name, skill_prompt = self._resolve_skill(position)
        session = self._storychecker.create_session(
            position_id=position.id,
            ticker=position.ticker,
            position_name=position.name,
            skill_name=skill_name,
            skill_prompt=skill_prompt,
        )
        # Auto-send the initial analysis request
        self._llm.skill_context = skill_name or "storychecker"
        initial_msg = _build_initial_message(position, skill_name, skill_prompt)
        self._storychecker.add_message(session.id, "user", initial_msg)
        response = self._run_llm(session.id, [{"role": "user", "content": initial_msg}])
        # Persist structured result for trend tracking
        self._analyses.save(
            position_id=position.id,
            agent="storychecker",
            skill_name=skill_name,
            verdict=_extract_verdict(response),
            summary=_extract_summary(response),
            session_id=session.id,
        )
        return session

    async def start_session_async(self, position: Position) -> StorycheckerSession:
        """Async version of start_session — for use in batch_check_all."""
        skill_name, skill_prompt = self._resolve_skill(position)
        session = self._storychecker.create_session(
            position_id=position.id,
            ticker=position.ticker,
            position_name=position.name,
            skill_name=skill_name,
            skill_prompt=skill_prompt,
        )
        self._llm.skill_context = skill_name or "storychecker"
        initial_msg = _build_initial_message(position, skill_name, skill_prompt)
        self._storychecker.add_message(session.id, "user", initial_msg)
        response = await self._run_llm_async(session.id, [{"role": "user", "content": initial_msg}])
        self._analyses.save(
            position_id=position.id,
            agent="storychecker",
            skill_name=skill_name,
            verdict=_extract_verdict(response),
            summary=_extract_summary(response),
            session_id=session.id,
        )
        return session

    async def batch_check_all(self, positions: List[Position]) -> List[Tuple[str, str | None]]:
        """
        Run story checks for all eligible positions sequentially.
        Each position uses its own story_skill (or none if not set).
        Returns list of (position_name, error_or_None).
        """
        eligible = [p for p in positions if p.story and p.id is not None]
        self._llm.position_count = len(eligible)  # Track how many positions in this batch
        results: List[Tuple[str, str | None]] = []
        for i, pos in enumerate(eligible):
            try:
                await self.start_session_async(pos)
                results.append((pos.name, None))
            except Exception as exc:
                results.append((pos.name, str(exc)))
            if i < len(eligible) - 1:
                await asyncio.sleep(15)  # rate limit
        return results

    def chat(self, session_id: int, user_message: str) -> str:
        """Send a follow-up message and return the assistant reply."""
        self._storychecker.add_message(session_id, "user", user_message)
        api_messages = self._build_api_messages(session_id)
        return self._run_llm(session_id, api_messages)

    def get_session(self, session_id: int) -> StorycheckerSession | None:
        return self._storychecker.get_session(session_id)

    def list_sessions(self, limit: int = 50):
        return self._storychecker.list_sessions(limit=limit)

    def get_messages(self, session_id: int):
        return self._storychecker.get_messages(session_id)

    def delete_session(self, session_id: int) -> None:
        self._storychecker.delete_session(session_id)

    async def generate_story_proposal(self, session_id: int | None = None, position: Position | None = None) -> str:
        """
        Generate an updated investment story.

        Can work in two modes:
        - With session_id: uses check messages as context
        - With position: generates from position info alone (no session context)

        One of session_id or position must be provided.
        """
        import asyncio

        if session_id is not None:
            # Mode 1: Use session context
            session = self.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            position = self._positions.get(session.position_id)
            if not position:
                raise ValueError(f"Position {session.position_id} not found")

            messages = self.get_messages(session_id)
            context_block = "\n".join([f"{m.role.upper()}: {m.content[:200]}" for m in messages[-4:]])
            context_text = f"**Analyse-Auszug:**\n{context_block}"
        elif position is not None:
            # Mode 2: Direct position, no session context
            context_text = "(kein aktueller Check — Story wird auf Basis der Positionsdaten generiert)"
        else:
            raise ValueError("Entweder session_id oder position muss angegeben werden")

        prompt = f"""Du bist ein Vermögensberater der Investment-Thesen schreibt.

**Position:** {position.name} ({position.ticker or 'N/A'})
**Asset-Klasse:** {position.asset_class}
**Bestehende Story:**
{position.story or '(keine)'}

{context_text}

**Aufgabe:** Schreibe eine kurze, prägnante Investment-These (2-3 Sätze) für diese Position.
Erkläre prägnant:
- Warum diese Position im Portfolio?
- Welche Rolle spielt sie?
- Was sind die Key Points?

Schreibe nur die These selbst, keine Einleitung oder Überschrift."""

        self._llm.skill_context = "storychecker_story_update"
        return await self._llm.complete(prompt, max_tokens=300)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_skill(self, position: Position) -> tuple[str, str]:
        """Return (skill_name, skill_prompt) from the position's story_skill, or ('', '') if none."""
        if not position.story_skill or not self._skills_repo:
            return "", ""
        skill = self._skills_repo.get_by_name(position.story_skill)
        if skill:
            return skill.name, skill.prompt
        return "", ""

    def _run_llm(self, session_id: int, api_messages: list[dict]) -> str:
        """Run the tool-calling loop and persist the final assistant response."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._run_llm_async(session_id, api_messages)
        )

    async def _run_llm_async(self, session_id: int, api_messages: list[dict]) -> str:
        messages = list(api_messages)
        for _ in range(MAX_TOOL_ITERATIONS):
            response = await self._llm.chat_with_tools(
                messages=messages,
                tools=[WEB_SEARCH_TOOL],
                system=BASE_SYSTEM_PROMPT,
                max_tokens=4096,
            )
            # Web search is server-side — no client tool calls to handle.
            # Loop exits when there are no remaining tool calls (stop_reason != "tool_use")
            # or when content is present and no client-side tools remain.
            if response.stop_reason != "tool_use" or not response.tool_calls:
                if response.content:
                    self._storychecker.add_message(session_id, "assistant", response.content)
                    return response.content
                # Unexpected: no content — append raw blocks and continue
                messages.append({"role": "assistant", "content": response.raw_blocks})
            else:
                # Client-side tool calls (none expected for web_search, but handle gracefully)
                messages.append({"role": "assistant", "content": response.raw_blocks})
        # Fallback: return whatever content we have
        self._storychecker.add_message(session_id, "assistant", response.content)
        return response.content

    def _build_api_messages(self, session_id: int) -> list[dict]:
        db_messages = self._storychecker.get_messages(session_id)
        return [
            {"role": m.role, "content": m.content}
            for m in db_messages
            if m.role in ("user", "assistant")
        ]


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _extract_verdict(text: str) -> str:
    """Extract traffic-light verdict from the agent response."""
    if "🟢" in text:
        return "intact"
    if "🟡" in text:
        return "gemischt"
    if "🔴" in text:
        return "gefaehrdet"
    return "unknown"


def _extract_summary(text: str) -> str | None:
    """Extract the one-sentence blockquote summary from the agent response."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("> ") and len(stripped) > 2:
            return stripped[2:].strip()
    return None


def _build_initial_message(position: Position, skill_name: str = "", skill_prompt: str = "") -> str:
    ticker_str = f" ({position.ticker})" if position.ticker else ""
    lines = [
        f"Bitte prüfe ob die folgende Investment-These noch intakt ist.",
        f"",
        f"**Unternehmen:** {position.name}{ticker_str}",
        f"**Asset-Klasse:** {position.asset_class}",
    ]
    if position.empfehlung:
        lines.append(f"**Aktuelle Empfehlung:** {position.empfehlung}")

    if position.story:
        lines.append(f"")
        lines.append(f"**Investment-These (Story):**")
        lines.append(position.story)
    else:
        lines.append(f"")
        lines.append(f"**Investment-These:** (keine Story hinterlegt — bitte allgemein für {position.name} prüfen)")

    if skill_name and skill_prompt:
        lines.append(f"")
        lines.append(f"**Anlage-Idee:** {skill_name}")
        lines.append(f"**Prüfkriterien:** {skill_prompt}")

    lines.append(f"")
    lines.append(f"Bitte suche aktuelle Informationen und erstelle deine Bewertung.")

    return "\n".join(lines)
