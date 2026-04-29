"""
Fundamental Analyzer Agent — in-depth fundamental analysis of individual positions.

Cloud-only (ClaudeProvider). Works with portfolio and watchlist positions.

Interactive chat interface with multi-turn conversations about valuation,
business quality, risk assessment, competitive position, etc.

Sessions are stored in memory (Streamlit session_state), verdicts in position_analyses.
"""

from __future__ import annotations
import asyncio
import logging

import re
from typing import List, Optional, Tuple, Dict, Any

from core.llm.base import Message, Role
from core.llm.claude import ClaudeProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.models import PublicPosition
from agents.agent_language import response_language_instruction


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

Präzise und konkret. Nutze Zahlen wenn möglich.
Auf Follow-up-Fragen: kurz und fokussiert antworten."""


# ------------------------------------------------------------------
# Session models (in-memory, not persisted)
# ------------------------------------------------------------------

class AnalyzerSession:
    """In-memory session for fundamental analyzer chat."""

    def __init__(self, session_id: str, position_id: int, position_name: str, ticker: Optional[str], language: str = "de"):
        self.id = session_id
        self.position_id = position_id
        self.position_name = position_name
        self.ticker = ticker
        self.language = language
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

    def start_session(self, position: PublicPosition, language: str = "de", skill: Optional[str] = None, skill_prompt: Optional[str] = None) -> AnalyzerSession:
        """Create a new session and run the initial analysis.

        Args:
            position: The position to analyze
            language: Language code for LLM output (default: "de")
            skill: Override skill name (optional)
            skill_prompt: Override skill prompt (optional)
        """
        import uuid
        from datetime import datetime

        session_id = str(uuid.uuid4())[:8]
        session = AnalyzerSession(
            session_id=session_id,
            position_id=position.id,
            position_name=position.name,
            ticker=position.ticker,
            language=language,
        )

        # Build initial message
        if skill is not None:
            skill_name, resolved_prompt = skill, skill_prompt
        else:
            skill_name, resolved_prompt = self._resolve_skill(position)
        initial_msg = _build_initial_message(position, skill_name, resolved_prompt)

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
        """Execute LLM call with web_search and caching enabled."""
        import asyncio

        self._llm.skill_context = "fundamental_analyzer"

        # Build message list in chat_with_tools format (dict, no system message in list)
        api_messages = []
        for msg in session.messages:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

        # Build system prompt with language instruction
        system = BASE_SYSTEM_PROMPT + "\n" + response_language_instruction(session.language)

        # Use chat_with_tools: enables web_search
        cr = asyncio.run(
            self._llm.chat_with_tools(
                messages=api_messages,
                tools=[WEB_SEARCH_TOOL],
                system=system,
                max_tokens=4096,
            )
        )
        return cr.content

    def _resolve_skill(self, position: PublicPosition) -> Tuple[str, Optional[str]]:
        """Resolve skill context if available. Returns (skill_name, skill_prompt) where skill_name is never None."""
        if not self._skills_repo or not position.story_skill:
            return "Standard", None
        skill = self._skills_repo.get_by_name(position.story_skill)
        if skill:
            return skill.name, skill.prompt
        return "Standard", None

    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        """Get all messages in a session."""
        session = self.get_session(session_id)
        if not session:
            return []
        return session.messages

    async def analyze_portfolio(
        self,
        positions: List[PublicPosition],
        skill_name: str,
        skill_prompt: str,
        language: str = "de",
    ) -> List[Tuple[int, str, str]]:
        """
        Analyze all eligible positions. Returns list of (position_id, verdict, summary).
        Verdicts are persisted in position_analyses under "fundamental_analyzer" agent.

        Args:
            positions: List of PublicPosition objects to analyze
            skill_name: Name of the configured skill
            skill_prompt: Custom skill prompt
            language: Language code for LLM output (default: "de")
        """
        # Only positions with tickers are fundamentally analysable
        eligible = [p for p in positions if p.ticker and p.id is not None]
        if not eligible:
            return []

        output: List[Tuple[int, str, str]] = []

        # Process one position at a time
        for pos in eligible:
            session = self.start_session(
                position=pos,
                language=language,
                skill=skill_name,
                skill_prompt=skill_prompt,
            )
            # Verdict + summary already persisted in start_session()
            output.append((pos.id, session.verdict or "unbekannt", session.summary or ""))
            await asyncio.sleep(0.3)

        return output

    async def generate_analysis_proposal(self, position: PublicPosition) -> str:
        """Generate an AI proposal for deeper analysis of a position."""
        prompt = f"""Erstelle eine strukturierte Analyse-Agenda für {position.name} ({position.ticker or 'N/A'}):

Welche Dimensionen sollten wir in der Tiefe analysieren?
- Geschäftsmodell-Risiken
- Bewertungs-Opportunitäten
- Konkurrenz-Bedrohungen
- Wachstums-Katalysatoren

Gib eine prägnante, fokussierte Agenda (4–6 Punkte).
"""
        return await self._llm.complete(
            prompt,
            system="Du bist ein Investmentanalyst. Antworte auf Deutsch.",
            max_tokens=512,
        )


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------


def _build_initial_message(position: PublicPosition, skill_name: Optional[str], skill_prompt: Optional[str]) -> str:
    """Build the initial analysis request message."""
    msg = f"Analysiere folgende Position tiefgehend:\n\n"
    msg += f"**Name:** {position.name}\n"
    if position.ticker:
        msg += f"**Ticker:** {position.ticker}\n"
    msg += f"**Anlageklasse:** {position.asset_class}\n"
    if position.anlageart:
        msg += f"**Anlage-Art:** {position.anlageart}\n"

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
