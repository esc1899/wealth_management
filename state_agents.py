"""
Agent factories — all 15 agent singletons.
"""

import logging
import streamlit as st

from config import config
from core.constants import CLAUDE_HAIKU, CLAUDE_SONNET
from core.llm.local import OllamaProvider
from agents.consensus_gap_agent import ConsensusGapAgent
from agents.fundamental_analyzer_agent import FundamentalAnalyzerAgent
from agents.market_data_agent import MarketDataAgent
from agents.market_data_fetcher import MarketDataFetcher, RateLimiter
from agents.news_agent import NewsAgent
from agents.portfolio_agent import PortfolioAgent
from agents.portfolio_story_agent_v2 import PortfolioStoryAgentV2
from agents.research_agent import ResearchAgent
from agents.search_agent import SearchAgent
from agents.storychecker_agent import StorycheckerAgent
from agents.structural_change_agent import StructuralChangeAgent
from agents.watchlist_checker_agent import WatchlistCheckerAgent
from agents.wealth_snapshot_agent import WealthSnapshotAgent
from core.scheduler import AgentSchedulerService
from core.strategy_config import get_strategy_registry
from state_db import get_db_connection
from state_repos import (
    get_positions_repo,
    get_market_repo,
    get_usage_repo,
    get_skills_repo,
    get_research_repo,
    get_news_repo,
    get_search_repo,
    get_storychecker_repo,
    get_analyses_repo,
    get_structural_scans_repo,
    get_wealth_snapshot_repo,
    get_portfolio_story_repo,
    get_agent_runs_repo,
    get_watchlist_checker_repo,
    get_dividend_snapshot_repo,
)
from state_llm import _make_claude_provider, _make_ollama_provider, _get_agent_model, _make_public_provider, _get_public_agent_model

# Default model values (overridable via app_config)
_DEFAULT_OLLAMA_MODEL = config.OLLAMA_MODEL
_DEFAULT_CLAUDE_MODEL = CLAUDE_HAIKU

logger = logging.getLogger(__name__)


@st.cache_resource
def get_portfolio_agent() -> PortfolioAgent:
    model = _get_agent_model("portfolio", "ollama", _DEFAULT_OLLAMA_MODEL)
    llm = OllamaProvider(host=config.OLLAMA_HOST, model=model, num_ctx=config.OLLAMA_NUM_CTX)
    llm.on_usage = lambda i, o, skill=None, dur=None, pos=None, cache_read=None, cache_write=None: get_usage_repo().record("portfolio_chat", model, i, o, skill=skill, duration_ms=dur, position_count=pos, cache_read_tokens=cache_read, cache_write_tokens=cache_write)
    fetcher = MarketDataFetcher(
        rate_limiter=RateLimiter(calls_per_second=config.RATE_LIMIT_RPS)
    )
    return PortfolioAgent(
        positions_repo=get_positions_repo(),
        llm=llm,
        skills_repo=get_skills_repo(),
        market_fetcher=fetcher,
        market_repo=get_market_repo(),
    )


def _safe_take_snapshot() -> None:
    """Helper: take wealth and dividend snapshots after market fetch, fail silently on errors."""
    agent = get_wealth_snapshot_agent()

    # Take wealth snapshot (overwrite so new/removed positions are reflected immediately)
    try:
        agent.take_snapshot(is_manual=False, overwrite=True)
    except Exception as e:
        logger.warning("Auto wealth snapshot failed: %s", e)

    # Take dividend snapshot (overwrite so new/removed positions are reflected immediately)
    try:
        agent.take_dividend_snapshot(is_manual=False, overwrite=True)
    except Exception as e:
        logger.warning("Auto dividend snapshot failed: %s", e)


@st.cache_resource
def get_market_agent() -> MarketDataAgent:
    fetcher = MarketDataFetcher(
        rate_limiter=RateLimiter(calls_per_second=config.RATE_LIMIT_RPS)
    )
    agent = MarketDataAgent(
        positions_repo=get_positions_repo(),
        market_repo=get_market_repo(),
        fetcher=fetcher,
        db_path=config.DB_PATH,
        encryption_key=config.ENCRYPTION_KEY,
    )
    scheduler = agent.setup_scheduler(fetch_hour=config.MARKET_DATA_FETCH_HOUR)
    scheduler.start()

    # Register post-fetch callback for automatic wealth snapshots
    agent.set_post_fetch_callback(lambda: _safe_take_snapshot())

    return agent


@st.cache_resource
def get_research_agent() -> ResearchAgent:
    model = _get_public_agent_model("research", _DEFAULT_CLAUDE_MODEL)
    llm = _make_public_provider(model, "research_chat")
    return ResearchAgent(
        positions_repo=get_positions_repo(),
        research_repo=get_research_repo(),
        llm=llm,
        strategy_registry=get_strategy_registry(),
    )


@st.cache_resource
def get_news_agent() -> NewsAgent:
    model = _get_public_agent_model("news", _DEFAULT_CLAUDE_MODEL)
    llm = _make_public_provider(model, "news_digest")
    return NewsAgent(llm=llm)


@st.cache_resource
def get_search_agent() -> SearchAgent:
    model = _get_public_agent_model("search", CLAUDE_SONNET)
    llm = _make_public_provider(model, "investment_search")
    return SearchAgent(
        positions_repo=get_positions_repo(),
        search_repo=get_search_repo(),
        llm=llm,
    )


@st.cache_resource
def get_storychecker_agent() -> StorycheckerAgent:
    model = _get_public_agent_model("storychecker", _DEFAULT_CLAUDE_MODEL)
    llm = _make_public_provider(model, "storychecker")
    return StorycheckerAgent(
        positions_repo=get_positions_repo(),
        storychecker_repo=get_storychecker_repo(),
        analyses_repo=get_analyses_repo(),
        llm=llm,
        skills_repo=get_skills_repo(),
    )


@st.cache_resource
def get_structural_change_agent() -> StructuralChangeAgent:
    model = _get_public_agent_model("structural_scan", CLAUDE_SONNET)
    llm = _make_public_provider(model, "structural_scan")
    return StructuralChangeAgent(
        positions_repo=get_positions_repo(),
        llm=llm,
    )


@st.cache_resource
@st.cache_resource
def get_fundamental_analyzer_repo():
    from core.storage.fundamental_analyzer import FundamentalAnalyzerRepository
    return FundamentalAnalyzerRepository(get_db_connection())


@st.cache_resource
def get_fundamental_analyzer_agent() -> FundamentalAnalyzerAgent:
    model = _get_public_agent_model("fundamental_analyzer", _DEFAULT_CLAUDE_MODEL)
    llm = _make_public_provider(model, "fundamental_analyzer")
    return FundamentalAnalyzerAgent(
        positions_repo=get_positions_repo(),
        analyses_repo=get_analyses_repo(),
        fa_repo=get_fundamental_analyzer_repo(),
        llm=llm,
        skills_repo=get_skills_repo(),
    )


@st.cache_resource
def get_consensus_gap_agent() -> ConsensusGapAgent:
    model = _get_public_agent_model("consensus_gap", CLAUDE_SONNET)
    llm = _make_public_provider(model, "consensus_gap")
    return ConsensusGapAgent(
        llm=llm,
        analyses_repo=get_analyses_repo(),
    )


@st.cache_resource
def get_agent_scheduler() -> AgentSchedulerService:
    service = AgentSchedulerService(
        db_path=config.DB_PATH,
        encryption_key=config.ENCRYPTION_KEY,
        anthropic_api_key=config.LLM_API_KEY,
        default_claude_model=_DEFAULT_CLAUDE_MODEL,
        llm_base_url=config.LLM_BASE_URL,
        openai_api_key=config.OPENAI_API_KEY,
        openai_base_url=config.OPENAI_BASE_URL,
    )
    service.start()
    return service


@st.cache_resource
def get_wealth_snapshot_agent() -> WealthSnapshotAgent:
    return WealthSnapshotAgent(
        positions_repo=get_positions_repo(),
        market_repo=get_market_repo(),
        wealth_repo=get_wealth_snapshot_repo(),
        market_data_agent=get_market_agent(),
        dividend_repo=get_dividend_snapshot_repo(),
    )


@st.cache_resource
def get_portfolio_story_agent() -> PortfolioStoryAgentV2:
    model = _get_agent_model("portfolio_story", "ollama", _DEFAULT_OLLAMA_MODEL)
    # Portfolio story analysis has detailed prompt — needs longer timeout
    llm = _make_ollama_provider(model, "portfolio_story_check", timeout=300.0)
    return PortfolioStoryAgentV2(
        llm=llm,
        positions_repo=get_positions_repo(),
        market_repo=get_market_repo(),
        skills_repo=get_skills_repo(),
        portfolio_story_repo=get_portfolio_story_repo(),
        agent_runs_repo=get_agent_runs_repo(),
    )


@st.cache_resource
def get_watchlist_checker_agent() -> WatchlistCheckerAgent:
    model = _get_agent_model("watchlist_checker", "ollama", _DEFAULT_OLLAMA_MODEL)
    llm = _make_ollama_provider(model, "watchlist_checker", timeout=300.0)
    return WatchlistCheckerAgent(
        positions_repo=get_positions_repo(),
        analyses_repo=get_analyses_repo(),
        llm=llm,
        skills_repo=get_skills_repo(),
        wc_repo=get_watchlist_checker_repo(),
        agent_runs_repo=get_agent_runs_repo(),
    )
