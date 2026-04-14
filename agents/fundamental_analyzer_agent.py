"""
Fundamental Analyzer Agent — in-depth fundamental analysis of individual positions.

Cloud-only (ClaudeProvider). Works with portfolio and watchlist positions.

Interactive chat interface with multi-turn conversations about valuation,
business quality, risk assessment, competitive position, etc.

Sessions are stored in memory (Streamlit session_state), verdicts in position_analyses.
"""

from __future__ import annotations
import logging

import re
from typing import List, Optional, Tuple, Dict, Any

from core.llm.claude import ClaudeProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.models import Position


logger = logging.getLogger(__name__)
AGENT_NAME = "fundamental_analyzer"

VALID_VERDICTS = {"unterbewertet", "fair", "überbewertet", "unbekannt"}

# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}
MAX_TOOL_ITERATIONS = 8

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """Du bist ein erfahrener Fundamental-Analyst mit 20+ Jahren Erfahrung.

Deine Aufgabe: Analysiere einzelne Investitionen tiefgehend — nicht nur oberflächlich.

Nutze bei Bedarf web_search für:
- Aktuelle Finanzkennzahlen (KGV, KBV, EBITDA, Renditen)
- Management-Qualität und Strategie
- Competitive advantages / Moats
- Industrietrends und Risiken
- Bewertungsvergleiche mit Peers

Analysiere diese Dimensionen (je nach Position relevant):

### 1. GESCHÄFTSMODELL & STRATEGIE
- Kerngeschäft und Umsatztreiber
- Profitabilität (Marge, ROIC)
- Management-Quality: Track Record, Incentives

### 2. BEWERTUNG
- KGV, EV/EBITDA, andere Multiples vs. historisch und Peers
- Fair Value — DCF-basiert oder Multiple-Ansatz
- Sicherheitsmarge / Margin of Safety

### 3. WACHSTUM & POTENZIAL
- Historisches Wachstum vs. Erwartungen
- TAM (Total Addressable Market) Expansion
- Emerging Opportunities

### 4. RISIKEN
- Finanzielle Risiken (Verschuldung, Cashflow)
- Operative Risiken (Konkurrenz, Regulierung, Technologie)
- Makro-Risiken (Rezession, Währung, Inflation)
- Klumpenrisiken (Kunden, Lieferanten, Märkte)

### 5. KATALYSATOREN & ZEITHORIZONT
- Was könnte sich in den nächsten 1–3 Jahren ändern?
- Wann wird die Bewertung gerecht?

Antworte auf Deutsch, präzise und konkret. Nutze Zahlen wenn möglich.
Auf Follow-up-Fragen: kurz und fokussiert antworten."""


# ------------------------------------------------------------------
# Session models (in-memory, not persisted)
# ------------------------------------------------------------------

class AnalyzerSession:
    """In-memory session for fundamental analyzer chat."""

    def __init__(self, session_id: str, position_id: int, position_name: str, ticker: Optional[str]):
        self.id = session_id
        self.position_id = position_id
        self.position_name = position_name
        self.ticker = ticker
        self.messages: List[Dict[str, str]] = []
        self.verdict: Optional[str] = None
        self.summary: Optional[str] = None

    def add_message(self, role: str, content: str):
        """Add a message to the session."""
        self.messages.append({"role": role, "content": content})

    def to_messages_api(self) -> List[Dict[str, str]]:
        """Convert to Claude API format."""
        return self.messages


# ------------------------------------------------------------------
# Agent
# ------------------------------------------------------------------


class FundamentalAnalyzerAgent:
    """
    Cloud agent for in-depth fundamental analysis of individual positions.
    Sessions are in-memory; verdicts are persisted to position_analyses.
    """

    def __init__(
        self,
        positions_repo,
        analyses_repo: PositionAnalysesRepository,
        llm: ClaudeProvider,
        skills_repo=None,
    ) -> None:
        self._positions = positions_repo
        self._analyses = analyses_repo
        self._llm = llm
        self._skills_repo = skills_repo
        self._sessions: Dict[str, AnalyzerSession] = {}

    @property
    def model(self) -> str:
        return self._llm.model

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def start_session(self, position: Position) -> AnalyzerSession:
        """Create a new session and run the initial analysis."""
        import uuid
        from datetime import datetime

        session_id = str(uuid.uuid4())[:8]
        session = AnalyzerSession(
            session_id=session_id,
            position_id=position.id,
            position_name=position.name,
            ticker=position.ticker,
        )

        # Build initial message
        skill_name, skill_prompt = self._resolve_skill(position)
        initial_msg = _build_initial_message(position, skill_name, skill_prompt)

        # Add to session and get response
        session.add_message("user", initial_msg)
        response = self._run_llm(session)

        session.add_message("assistant", response)

        # Save verdict for tracking (always, since _extract_verdict defaults to 'unbekannt')
        verdict = _extract_verdict(response)
        summary = _extract_summary(response)
        self._analyses.save(
            position_id=position.id,
            agent="fundamental_analyzer",
            skill_name=skill_name,
            verdict=verdict,
            summary=summary,
            session_id=session_id,
        )
        session.verdict = verdict
        session.summary = summary

        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: Optional[str]) -> Optional[AnalyzerSession]:
        """Retrieve a session by ID."""
        if not session_id:
            return None
        return self._sessions.get(session_id)

    def list_sessions(self, limit: int = 10) -> List[AnalyzerSession]:
        """List recent sessions (up to limit)."""
        # Return sessions in reverse order (newest first)
        return list(reversed(list(self._sessions.values())[-limit:]))

    # ------------------------------------------------------------------
    # Chat interface
    # ------------------------------------------------------------------

    def chat(self, session_id: str, user_message: str) -> str:
        """Send a follow-up message and get response."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        session.add_message("user", user_message)
        response = self._run_llm(session)
        session.add_message("assistant", response)
        return response

    # ------------------------------------------------------------------
    # LLM execution
    # ------------------------------------------------------------------

    def _run_llm(self, session: AnalyzerSession) -> str:
        """Execute LLM call with web search tool."""
        self._llm.skill_context = "fundamental_analyzer"
        response = self._llm.chat(
            messages=session.to_messages_api(),
            system=BASE_SYSTEM_PROMPT,
            tools=[WEB_SEARCH_TOOL],
            max_tool_calls=MAX_TOOL_ITERATIONS,
        )
        return response

    def _resolve_skill(self, position: Position) -> Tuple[Optional[str], Optional[str]]:
        """Resolve skill context if available."""
        if not self._skills_repo or not position.story_skill:
            return None, None
        skill = self._skills_repo.get_by_name(position.story_skill)
        if skill:
            return skill.name, skill.prompt
        return None, None

    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        """Get all messages in a session."""
        session = self.get_session(session_id)
        if not session:
            return []
        return session.messages

    async def generate_analysis_proposal(self, position: Position) -> str:
        """Generate an AI proposal for deeper analysis of a position."""
        prompt = f"""Erstelle eine strukturierte Analyse-Agenda für {position.name} ({position.ticker or 'N/A'}):

Welche Dimensionen sollten wir in der Tiefe analysieren?
- Geschäftsmodell-Risiken
- Bewertungs-Opportunitäten
- Konkurrenz-Bedrohungen
- Wachstums-Katalysatoren

Gib eine prägnante, fokussierte Agenda (4–6 Punkte).
"""
        # Simple LLM call without session context
        response = self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system="Du bist ein Investmentanalyst. Antworte auf Deutsch.",
        )
        return response


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------


def _build_initial_message(position: Position, skill_name: Optional[str], skill_prompt: Optional[str]) -> str:
    """Build the initial analysis request message."""
    msg = f"Analysiere folgende Position tiefgehend:\n\n"
    msg += f"**Name:** {position.name}\n"
    if position.ticker:
        msg += f"**Ticker:** {position.ticker}\n"
    msg += f"**Anlageklasse:** {position.asset_class}\n"
    if position.anlageart:
        msg += f"**Anlage-Art:** {position.anlageart}\n"
    if position.purchase_price:
        msg += f"**Kaufpreis:** €{position.purchase_price:,.2f}\n"

    if position.story:
        msg += f"\n**Investment-These:**\n{position.story}\n"

    if skill_name and skill_prompt:
        msg += f"\n**Fokus-Bereich ({skill_name}):**\n{skill_prompt}\n"

    msg += "\nStarte mit einer strukturierten Analyse dieser Position. Nutze web_search um aktuelle Daten zu finden."
    return msg


def _extract_verdict(response: str) -> Optional[str]:
    """Extract verdict from LLM response. Defaults to 'unbekannt' if no verdict found."""
    response_lower = response.lower()
    for verdict in VALID_VERDICTS:
        if verdict in response_lower:
            return verdict
    return "unbekannt"


def _extract_summary(response: str) -> Optional[str]:
    """Extract a one-line summary from LLM response."""
    lines = response.split("\n")
    for line in lines:
        if line.strip() and len(line) < 200 and not line.startswith("#"):
            return line.strip()
    return None
