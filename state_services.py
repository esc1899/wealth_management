"""
Service factories — domain services beyond simple CRUD.
"""

import streamlit as st

from config import config
from core.constants import CLAUDE_HAIKU
from state_repos import get_usage_repo, get_analyses_repo, get_positions_repo
from state_llm import _get_agent_model, _get_public_agent_model, _make_ollama_provider, _make_public_provider

# Default model values
_DEFAULT_OLLAMA_MODEL = config.OLLAMA_MODEL
_DEFAULT_CLAUDE_MODEL = CLAUDE_HAIKU


@st.cache_resource
def get_position_story_service():
    """Service for generating individual position investment theses.

    Modell aus den Einstellungen ("Story-Entwurf"), je Aufruf gelesen und
    geroutet wie jeder Cloud-Agent -- bis 02.10.2026 umging der Service das
    und waehlte den Anbieter allein danach, ob OPENAI_BASE_URL gesetzt war.
    """
    from core.services.position_story_service import PositionStoryService
    return PositionStoryService(
        provider_factory=lambda: _make_public_provider(
            _get_public_agent_model("position_story", CLAUDE_HAIKU), "position_story"),
    )


def get_portfolio_comment_model() -> str:
    """Resolve the currently configured model for portfolio comments."""
    return _get_agent_model("portfolio_comment", "ollama", _DEFAULT_OLLAMA_MODEL)


def get_skill_generator_llm():
    """Lokales Modell fuer den Prompt-Generator der Skills-Seite -- je Aufruf
    gebaut, damit eine neue Auswahl in den Einstellungen sofort gilt."""
    model = _get_agent_model("skill_generator", "ollama", _DEFAULT_OLLAMA_MODEL)
    return _make_ollama_provider(model, "skill_generator")


@st.cache_resource
def get_portfolio_comment_service(model: str = ""):
    """Service for generating stylized financial commentary.

    model is passed explicitly so @st.cache_resource creates a new instance
    when the model changes (cache key includes model).
    """
    from core.services.portfolio_comment_service import PortfolioCommentService
    return PortfolioCommentService(
        provider_factory=lambda: _make_ollama_provider(model or _DEFAULT_OLLAMA_MODEL, "portfolio_comment"),
    )


@st.cache_resource
def get_analysis_service():
    """Service for centralized verdict analysis access."""
    from core.services.analysis_service import AnalysisService
    return AnalysisService(analyses_repo=get_analyses_repo())


@st.cache_resource
def get_portfolio_service():
    """Service for portfolio and position aggregation queries."""
    from core.services.portfolio_service import PortfolioService
    return PortfolioService(positions_repo=get_positions_repo())
