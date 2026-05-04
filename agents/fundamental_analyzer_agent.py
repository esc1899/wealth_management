"""
Fundamental Analyzer Agent — in-depth fundamental analysis of individual positions.

Cloud-only (ClaudeProvider). Works with portfolio and watchlist positions.

Interactive chat interface with multi-turn conversations about valuation,
business quality, risk assessment, competitive position, etc.

Sessions are persisted in DB, verdicts in position_analyses.
"""

from __future__ import annotations
import asyncio
import logging

from typing import List, Optional, Tuple

from core.llm.claude import ClaudeProvider
from core.storage.analyses import PositionAnalysesRepository
from core.storage.fundamental_analyzer import FundamentalAnalyzerRepository
from core.storage.models import PublicPosition, FundamentalAnalyzerSession, FundamentalAnalyzerMessage
from agents.agent_language import response_language_instruction


logger = logging.getLogger(__name__)
AGENT_NAME = "fundamental_analyzer"

VALID_VERDICTS = {"unterbewertet", "fair", "überbewertet", "unbekannt"}

# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------

WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}

# ------------------------------------------------------------------
# System prompt
# ------------------------------------------------------------------

BASE_SYSTEM_PROMPT = """Du bist ein erfahrener Fundamental-Analyst.

Analysiere die Position tiefgehend. Nutze web_search für aktuelle Daten.

Beginne deine Antwort IMMER mit:
**ZUSAMMENFASSUNG:** [1 Satz — die wichtigste Kernaussage]

Dann die Analyse. Schließe ab mit genau einem:
**Fazit: unterbewertet** oder **Fazit: fair** oder **Fazit: überbewertet**"""


# ------------------------------------------------------------------
# Agent
# ------------------------------------------------------------------


class FundamentalAnalyzerAgent:
    """
    Cloud agent for in-depth fundamental analysis of individual positions.
    Sessions are persisted in DB; verdicts are persisted to position_analyses.
    """

    def __init__(
        self,
        positions_repo,
        analyses_repo: PositionAnalysesRepository,
        fa_repo: FundamentalAnalyzerRepository,
        llm: ClaudeProvider,
        skills_repo=None,
    ) -> None:
        self._positions = positions_repo
        self._analyses = analyses_repo
        self._fa_repo = fa_repo
        self._llm = llm
        self._skills_repo = skills_repo

    @property
    def model(self) -> str:
        return self._llm.model

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def start_session(self, position: PublicPosition, language: str = "de", skill: Optional[str] = None, skill_prompt: Optional[str] = None) -> FundamentalAnalyzerSession:
        """Create a new session and run the initial analysis.

        Args:
            position: The position to analyze
            language: Language code for LLM output (default: "de")
            skill: Override skill name (optional)
            skill_prompt: Override skill prompt (optional)
        """
        # Resolve skill context
        if skill is not None:
            skill_name = skill
        else:
            skill_name, _ = self._resolve_skill(position)

        # Create session in DB
        session = self._fa_repo.create_session(
            position_id=position.id,
            ticker=position.ticker,
            position_name=position.name,
            skill_name=skill_name,
        )

        # Build initial message and run analysis
        if skill is not None:
            resolved_prompt = skill_prompt
        else:
            _, resolved_prompt = self._resolve_skill(position)
        initial_msg = _build_initial_message(position, skill_name, resolved_prompt)

        # Persist user message
        self._fa_repo.add_message(session.id, "user", initial_msg)

        # Get response from LLM
        response = self._run_llm(session.id, language=language)

        # Persist assistant response
        self._fa_repo.add_message(session.id, "assistant", response)

        # Save verdict for tracking (always, since _extract_verdict defaults to 'unbekannt')
        verdict = _extract_verdict(response)
        summary = _extract_summary(response)
        self._analyses.save(
            position_id=position.id,
            agent="fundamental_analyzer",
            skill_name=skill_name,
            verdict=verdict,
            summary=summary,
            session_id=session.id,
        )

        return session

    def get_session(self, session_id: Optional[int]) -> Optional[FundamentalAnalyzerSession]:
        """Retrieve a session by ID."""
        if not session_id:
            return None
        return self._fa_repo.get_session(session_id)

    def list_sessions(self, limit: int = 10) -> List[FundamentalAnalyzerSession]:
        """List recent sessions (up to limit)."""
        return self._fa_repo.list_sessions(limit=limit)

    # ------------------------------------------------------------------
    # Chat interface
    # ------------------------------------------------------------------

    def chat(self, session_id: int, user_message: str) -> str:
        """Send a follow-up message and get response."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Persist user message
        self._fa_repo.add_message(session_id, "user", user_message)

        # Get response from LLM
        response = self._run_llm(session_id)

        # Persist assistant response
        self._fa_repo.add_message(session_id, "assistant", response)

        return response

    # ------------------------------------------------------------------
    # LLM execution
    # ------------------------------------------------------------------

    def _run_llm(self, session_id: int, language: str = "de") -> str:
        """Execute LLM call with web_search and caching enabled."""
        self._llm.skill_context = "fundamental_analyzer"

        # Load all messages for this session
        messages = self._fa_repo.get_messages(session_id)
        api_messages = []
        for msg in messages:
            api_messages.append({"role": msg.role, "content": msg.content})

        # Build system prompt with language instruction
        system = BASE_SYSTEM_PROMPT + "\n" + response_language_instruction(language)

        # Use chat_with_tools: enables web_search
        cr = asyncio.run(
            self._llm.chat_with_tools(
                messages=api_messages,
                tools=[WEB_SEARCH_TOOL],
                system=system,
                max_tokens=1500,
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

    def get_messages(self, session_id: int) -> List[FundamentalAnalyzerMessage]:
        """Get all messages in a session."""
        return self._fa_repo.get_messages(session_id)

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
            updated_session = self.get_session(session.id)
            if updated_session:
                verdict = updated_session.verdict or "unbekannt"
                summary = ""
                # Extract summary from first message
                messages = self.get_messages(session.id)
                for msg in messages:
                    if msg.role == "assistant":
                        summary = _extract_summary(msg.content) or ""
                        break
                output.append((pos.id, verdict, summary))
            await asyncio.sleep(0.3)

        # Cleanup: remove sessions older than 365 days
        self._fa_repo.cleanup_old_sessions(days=365)

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
    """Extract verdict from LLM response. Looks for **Fazit: <verdict>** pattern first."""
    # Look for mandated format: **Fazit: unterbewertet/fair/überbewertet**
    if "**Fazit:" in response or "**fazit:" in response.lower():
        response_lower = response.lower()
        for verdict in VALID_VERDICTS:
            if verdict in response_lower:
                return verdict
    # Fallback: simple keyword search in entire response
    response_lower = response.lower()
    for verdict in VALID_VERDICTS:
        if verdict in response_lower:
            return verdict
    return "unbekannt"


def _extract_summary(response: str) -> Optional[str]:
    """Extract one-line summary from LLM response. Looks for **ZUSAMMENFASSUNG:** marker first."""
    lines = response.split("\n")
    # Primary: Look for explicit **ZUSAMMENFASSUNG:** marker
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("**ZUSAMMENFASSUNG:**"):
            summary = stripped.removeprefix("**ZUSAMMENFASSUNG:**").strip()
            return summary if summary else None
    # Fallback: First non-Markdown line (backward compat)
    for line in lines:
        stripped = line.strip()
        if stripped and len(stripped) < 200 and not stripped.startswith("#") and not all(c in "-_=*~" for c in stripped):
            return stripped
    return None
