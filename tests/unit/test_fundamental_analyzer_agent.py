"""Unit tests for FundamentalAnalyzerAgent."""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch

from agents.fundamental_analyzer_agent import (
    FundamentalAnalyzerAgent,
    AnalyzerSession,
    _extract_verdict,
    _extract_summary,
    _build_initial_message,
)
from core.storage.models import Position


@pytest.fixture
def mock_position():
    """Create a mock position."""
    from datetime import date
    return Position(
        id=1,
        name="Apple Inc.",
        ticker="AAPL",
        asset_class="Aktie",
        anlageart="Einzelaktie",
        investment_type="Wertpapiere",
        unit="Stück",
        added_date=date.today(),
        purchase_price=150.50,
        quantity=10,
        story="Tech leader with strong ecosystem lock-in",
        story_skill=None,
        in_portfolio=True,
    )


@pytest.fixture
def mock_llm():
    """Create a mock LLM provider."""
    mock = Mock()
    mock.model = "claude-sonnet-4-6"
    mock.chat = AsyncMock(return_value="🟢 **Intakt** — Das Geschäftsmodell ist stabil")
    return mock


@pytest.fixture
def mock_repos():
    """Create mock repositories."""
    return {
        "positions_repo": Mock(),
        "analyses_repo": Mock(),
        "skills_repo": Mock(),
    }


@pytest.fixture
def agent(mock_llm, mock_repos):
    """Create a FundamentalAnalyzerAgent instance."""
    return FundamentalAnalyzerAgent(
        positions_repo=mock_repos["positions_repo"],
        analyses_repo=mock_repos["analyses_repo"],
        llm=mock_llm,
        skills_repo=mock_repos["skills_repo"],
    )


# ------------------------------------------------------------------
# Test AnalyzerSession
# ------------------------------------------------------------------


def test_analyzer_session_creation():
    """Test creating an AnalyzerSession."""
    session = AnalyzerSession(
        session_id="abc123",
        position_id=1,
        position_name="Apple",
        ticker="AAPL",
    )
    assert session.id == "abc123"
    assert session.position_id == 1
    assert session.position_name == "Apple"
    assert session.ticker == "AAPL"
    assert len(session.messages) == 0


def test_analyzer_session_add_message():
    """Test adding messages to a session."""
    session = AnalyzerSession("s1", 1, "Apple", "AAPL")
    session.add_message("user", "Analyse Apple")
    session.add_message("assistant", "Hier ist die Analyse...")

    assert len(session.messages) == 2
    assert session.messages[0] == {"role": "user", "content": "Analyse Apple"}
    assert session.messages[1] == {"role": "assistant", "content": "Hier ist die Analyse..."}


def test_analyzer_session_to_messages_api():
    """Test converting session to API format."""
    session = AnalyzerSession("s1", 1, "Apple", "AAPL")
    session.add_message("user", "Test")
    session.add_message("assistant", "Response")

    api_messages = session.to_messages_api()
    assert api_messages == session.messages


# ------------------------------------------------------------------
# Test Agent initialization
# ------------------------------------------------------------------


def test_agent_initialization(agent, mock_llm):
    """Test agent initialization."""
    assert agent.model == "claude-sonnet-4-6"
    assert agent._llm == mock_llm


# ------------------------------------------------------------------
# Test session management
# ------------------------------------------------------------------


def test_start_session(agent, mock_position, mock_llm):
    """Test starting a new session."""
    session = agent.start_session(mock_position)

    assert session is not None
    assert session.position_id == 1
    assert session.position_name == "Apple Inc."
    assert len(session.messages) >= 1  # At least initial message
    assert mock_llm.chat.called


def test_get_session(agent, mock_position, mock_llm):
    """Test retrieving a session."""
    session = agent.start_session(mock_position)
    retrieved = agent.get_session(session.id)

    assert retrieved is not None
    assert retrieved.id == session.id
    assert retrieved.position_id == 1


def test_get_session_not_found(agent):
    """Test retrieving a non-existent session."""
    session = agent.get_session("nonexistent")
    assert session is None


def test_get_session_with_none_id(agent):
    """Test getting session with None ID."""
    session = agent.get_session(None)
    assert session is None


def test_list_sessions(agent, mock_position, mock_llm):
    """Test listing sessions."""
    # Start multiple sessions
    for _ in range(3):
        agent.start_session(mock_position)

    sessions = agent.list_sessions(limit=10)
    assert len(sessions) == 3


def test_list_sessions_respects_limit(agent, mock_position, mock_llm):
    """Test that list_sessions respects the limit."""
    for _ in range(5):
        agent.start_session(mock_position)

    sessions = agent.list_sessions(limit=2)
    assert len(sessions) == 2


# ------------------------------------------------------------------
# Test chat interface
# ------------------------------------------------------------------


def test_chat(agent, mock_position, mock_llm):
    """Test sending a chat message."""
    session = agent.start_session(mock_position)
    mock_llm.chat.return_value = "Follow-up analysis response"

    response = agent.chat(session.id, "Welche Risiken sehen Sie?")

    assert response == "Follow-up analysis response"
    assert len(session.messages) >= 2  # Initial + response + follow-up


def test_chat_session_not_found(agent):
    """Test chat with non-existent session."""
    with pytest.raises(ValueError):
        agent.chat("nonexistent", "Message")


# ------------------------------------------------------------------
# Test helper functions
# ------------------------------------------------------------------


def test_extract_verdict_simple():
    """Test verdict extraction from response."""
    assert _extract_verdict("Das ist unterbewertet") == "unterbewertet"
    assert _extract_verdict("fair bewertete Aktie") == "fair"
    assert _extract_verdict("überbewertet aktuell") == "überbewertet"
    assert _extract_verdict("unbekannt momentan") == "unbekannt"


def test_extract_verdict_case_insensitive():
    """Test verdict extraction is case-insensitive."""
    assert _extract_verdict("Das ist UNTERBEWERTET") == "unterbewertet"
    assert _extract_verdict("FAIR bewertet") == "fair"


def test_extract_verdict_not_found():
    """Test extraction when no verdict is present. Defaults to 'unbekannt'."""
    result = _extract_verdict("Keine verwandten Wörter hier")
    assert result == "unbekannt"


def test_extract_summary():
    """Test summary extraction."""
    text = "Dies ist eine wichtige Zusammenfassung\nZweite Zeile\n# Header"
    summary = _extract_summary(text)

    assert summary == "Dies ist eine wichtige Zusammenfassung"


def test_extract_summary_skips_headers():
    """Test that summary extraction skips headers."""
    text = "# Header\nAktueller Preis ist wichtig"
    summary = _extract_summary(text)

    assert summary == "Aktueller Preis ist wichtig"


def test_extract_summary_empty_response():
    """Test summary extraction from empty response."""
    summary = _extract_summary("")
    assert summary is None


def test_build_initial_message(mock_position):
    """Test building initial analysis message."""
    msg = _build_initial_message(mock_position, None, None)

    assert "Apple Inc." in msg
    assert "AAPL" in msg
    assert "Aktie" in msg
    assert "Tech leader" in msg  # From story
    assert "web_search" in msg.lower() or "daten" in msg.lower()


def test_build_initial_message_with_skill(mock_position):
    """Test initial message includes skill prompt."""
    msg = _build_initial_message(mock_position, "growth", "Focus on revenue growth")

    assert "growth" in msg
    assert "Focus on revenue growth" in msg


# ------------------------------------------------------------------
# Test LLM integration
# ------------------------------------------------------------------


def test_llm_called_with_correct_format(agent, mock_position, mock_llm):
    """Test that LLM is called with correct message format."""
    agent.start_session(mock_position)

    # Check that chat was called
    assert mock_llm.chat.called

    # Get the call arguments
    call_args = mock_llm.chat.call_args
    assert "messages" in call_args.kwargs or len(call_args.args) > 0
