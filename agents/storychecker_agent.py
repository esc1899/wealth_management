"""
Story Checker Agent — checks if an investment thesis is still intact.

Cloud-only (ClaudeProvider). Watchlist positions only — no portfolio quantities
or purchase prices are passed to the API.

Uses Anthropic's built-in web search to find current news and data about the
company, then evaluates whether the original investment thesis still holds.

Persistent sessions: start_session() kicks off a new check, chat() allows
follow-up questions within the same session.
"""

from __future__ import annotations

from core.llm.claude import ClaudeProvider
from core.storage.models import Position, StorycheckerSession
from core.storage.storychecker import StorycheckerRepository

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
- Die verfolgte Anlage-Idee (z.B. "Megatrend-Play", "Qualitäts-Compounder")
- Spezifische Prüfkriterien zur Anlage-Idee

Deine Aufgabe: Nutze web_search um aktuelle Informationen zur Firma zu finden
(News, Quartalszahlen, Management-Aussagen, Wettbewerb). Beurteile dann ob die
These noch hält — nicht ob sie theoretisch "gut" ist, sondern ob sie heute noch zutrifft.

Antworte auf die erste Anfrage IMMER in diesem Format:

## Story-Check: {NAME} ({TICKER})
**Anlage-Idee:** {SKILL} · **Urteil:** {AMPEL}

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
        positions_repo,  # PositionsRepository — kept for future use
        storychecker_repo: StorycheckerRepository,
        llm: ClaudeProvider,
    ) -> None:
        self._positions = positions_repo
        self._storychecker = storychecker_repo
        self._llm = llm

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def start_session(
        self,
        position: Position,
        skill_name: str,
        skill_prompt: str,
    ) -> StorycheckerSession:
        """Create a new session and run the initial story check."""
        session = self._storychecker.create_session(
            position_id=position.id,
            ticker=position.ticker,
            position_name=position.name,
            skill_name=skill_name,
            skill_prompt=skill_prompt,
        )
        # Auto-send the initial analysis request
        initial_msg = _build_initial_message(position, skill_name, skill_prompt)
        self._storychecker.add_message(session.id, "user", initial_msg)
        self._run_llm(session.id, [{"role": "user", "content": initial_msg}])
        return session

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

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

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
                max_tokens=2048,
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


def _build_initial_message(position: Position, skill_name: str, skill_prompt: str) -> str:
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

    lines.append(f"")
    lines.append(f"**Anlage-Idee:** {skill_name}")
    lines.append(f"**Prüfkriterien:** {skill_prompt}")
    lines.append(f"")
    lines.append(f"Bitte suche aktuelle Informationen und erstelle deine Bewertung.")

    return "\n".join(lines)
