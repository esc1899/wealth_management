"""
Service factories — domain services beyond simple CRUD.
"""

import streamlit as st

from config import config
from core.constants import CLAUDE_HAIKU
from state_repos import get_usage_repo, get_analyses_repo, get_positions_repo
from state_llm import _get_agent_model, _get_public_agent_model

# Default model values
_DEFAULT_OLLAMA_MODEL = config.OLLAMA_MODEL
_DEFAULT_CLAUDE_MODEL = CLAUDE_HAIKU


@st.cache_resource
def get_position_story_service():
    """Service for generating individual position investment theses."""
    from core.services.position_story_service import PositionStoryService
    return PositionStoryService(
        api_key=config.LLM_API_KEY,
        usage_repo=get_usage_repo(),
        model=_get_public_agent_model("position_story", CLAUDE_HAIKU),
        base_url=config.LLM_BASE_URL,
        openai_api_key=config.OPENAI_API_KEY,
        openai_base_url=config.OPENAI_BASE_URL,
    )


def get_portfolio_comment_model() -> str:
    """Resolve the currently configured model for portfolio comments."""
    return _get_agent_model("portfolio_comment", "ollama", _DEFAULT_OLLAMA_MODEL)


@st.cache_resource
def get_portfolio_comment_service(model: str = ""):
    """Service for generating stylized financial commentary.

    model is passed explicitly so @st.cache_resource creates a new instance
    when the model changes (cache key includes model).
    """
    from core.services.portfolio_comment_service import PortfolioCommentService
    return PortfolioCommentService(
        host=config.OLLAMA_HOST,
        model=model or _DEFAULT_OLLAMA_MODEL,
        usage_repo=get_usage_repo(),
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
