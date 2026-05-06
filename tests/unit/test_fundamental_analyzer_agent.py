"""Unit tests for FundamentalAnalyzerAgent."""

import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import date, datetime, timezone

from agents.fundamental_analyzer_agent import (
    FundamentalAnalyzerAgent,
    _extract_verdict,
    _extract_summary,
    _build_initial_message,
)
from core.storage.models import Position, FundamentalAnalyzerSession, FundamentalAnalyzerMessage


@pytest.fixture
def mock_position():
    """Create a mock position."""
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
    mock_response = Mock()
    mock_response.content = "🟢 **Intakt** — Das Geschäftsmodell ist stabil"
    mock.chat_with_tools = AsyncMock(return_value=mock_response)
    return mock


@pytest.fixture
def mock_fa_repo():
    """Create a mock FundamentalAnalyzerRepository."""
    mock = Mock()

    # Mock session creation
    def create_session_side_effect(position_id, ticker, position_name, skill_name):
        return FundamentalAnalyzerSession(
            id=1,
            position_id=position_id,
            ticker=ticker,
            position_name=position_name,
            skill_name=skill_name,
            created_at=datetime.now(timezone.utc),
        )

    mock.create_session = Mock(side_effect=create_session_side_effect)

    # Mock session retrieval
    def get_session_side_effect(session_id):
        if session_id == 1:
            return FundamentalAnalyzerSession(
                id=1,
                position_id=1,
                ticker="AAPL",
                position_name="Apple Inc.",
                skill_name="Standard",
                created_at=datetime.now(timezone.utc),
            )
        return None

    mock.get_session = Mock(side_effect=get_session_side_effect)

    # Mock list sessions
    mock.list_sessions = Mock(return_value=[
        FundamentalAnalyzerSession(
            id=i,
            position_id=1,
            ticker="AAPL",
            position_name="Apple Inc.",
            skill_name="Standard",
            created_at=datetime.now(timezone.utc),
        )
        for i in range(1, 4)
    ])

    # Mock messages
    def add_message_side_effect(session_id, role, content):
        return FundamentalAnalyzerMessage(
            id=1,
            session_id=session_id,
            role=role,
            content=content,
            created_at=datetime.now(timezone.utc),
        )

    mock.add_message = Mock(side_effect=add_message_side_effect)

    def get_messages_side_effect(session_id):
        return [
            FundamentalAnalyzerMessage(
                id=1,
                session_id=session_id,
                role="user",
                content="Test user message",
                created_at=datetime.now(timezone.utc),
            ),
            FundamentalAnalyzerMessage(
                id=2,
                session_id=session_id,
                role="assistant",
                content="Test assistant message",
                created_at=datetime.now(timezone.utc),
            ),
        ]

    mock.get_messages = Mock(side_effect=get_messages_side_effect)

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
def agent(mock_llm, mock_fa_repo, mock_repos):
    """Create a FundamentalAnalyzerAgent instance."""
    return FundamentalAnalyzerAgent(
        positions_repo=mock_repos["positions_repo"],
        analyses_repo=mock_repos["analyses_repo"],
        fa_repo=mock_fa_repo,
        llm=mock_llm,
        skills_repo=mock_repos["skills_repo"],
    )


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


def test_start_session(agent, mock_position, mock_llm, mock_fa_repo):
    """Test starting a new session."""
    session = agent.start_session(mock_position)

    assert session is not None
    assert session.position_id == 1
    assert session.position_name == "Apple Inc."
    assert mock_llm.chat_with_tools.called
    assert mock_fa_repo.create_session.called
    assert mock_fa_repo.add_message.called


def test_get_session(agent, mock_position, mock_llm, mock_fa_repo):
    """Test retrieving a session."""
    session = agent.start_session(mock_position)
    retrieved = agent.get_session(session.id)

    assert retrieved is not None
    assert retrieved.id == session.id
    assert retrieved.position_id == 1


def test_get_session_not_found(agent, mock_fa_repo):
    """Test retrieving a non-existent session."""
    mock_fa_repo.get_session.return_value = None
    session = agent.get_session(999)
    assert session is None


def test_get_session_with_none_id(agent):
    """Test getting session with None ID."""
    session = agent.get_session(None)
    assert session is None


def test_list_sessions(agent, mock_position, mock_llm, mock_fa_repo):
    """Test listing sessions."""
    # Start a session
    agent.start_session(mock_position)

    sessions = agent.list_sessions(limit=10)
    assert len(sessions) == 3  # mock returns 3 sessions
    assert mock_fa_repo.list_sessions.called


def test_list_sessions_respects_limit(agent, mock_fa_repo):
    """Test that list_sessions respects the limit."""
    agent.list_sessions(limit=2)

    # Verify that limit was passed to repo
    call_args = mock_fa_repo.list_sessions.call_args
    assert call_args.kwargs.get("limit") == 2 or call_args.args[0] == 2


# ------------------------------------------------------------------
# Test chat interface
# ------------------------------------------------------------------


def test_chat(agent, mock_position, mock_llm, mock_fa_repo):
    """Test sending a chat message."""
    session = agent.start_session(mock_position)
    mock_response = Mock()
    mock_response.content = "Follow-up analysis response"
    mock_llm.chat_with_tools.return_value = mock_response

    response = agent.chat(session.id, "Welche Risiken sehen Sie?")

    assert response == "Follow-up analysis response"
    assert mock_fa_repo.add_message.called


def test_chat_session_not_found(agent, mock_fa_repo):
    """Test chat with non-existent session."""
    mock_fa_repo.get_session.return_value = None
    with pytest.raises(ValueError):
        agent.chat(999, "Message")


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
    assert "Einzelaktie" in msg  # From anlageart
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

    # Check that chat_with_tools was called with web_search enabled
    assert mock_llm.chat_with_tools.called
    call_args = mock_llm.chat_with_tools.call_args
    assert "messages" in call_args.kwargs
    assert "tools" in call_args.kwargs
    assert "system" in call_args.kwargs
