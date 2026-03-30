"""
Shared Streamlit cache resources — singletons for agents and repositories.
"""

import nest_asyncio
import streamlit as st

nest_asyncio.apply()

from config import config
from agents.market_data_agent import MarketDataAgent
from agents.market_data_fetcher import MarketDataFetcher, RateLimiter
from agents.news_agent import NewsAgent
from agents.portfolio_agent import PortfolioAgent
from agents.rebalance_agent import RebalanceAgent
from agents.research_agent import ResearchAgent
from agents.search_agent import SearchAgent
from core.asset_class_config import get_asset_class_registry, AssetClassRegistry
from core.llm.claude import ClaudeProvider
from core.llm.local import OllamaProvider
from core.encryption import PassthroughEncryptionService
from core.storage.base import build_encryption_service, get_connection, init_db
from core.storage.market_data import MarketDataRepository
from core.storage.positions import PositionsRepository
from core.storage.news import NewsRepository
from core.storage.rebalance import RebalanceRepository
from core.storage.research import ResearchRepository
from core.storage.search import SearchRepository
from core.storage.skills import SkillsRepository
from core.storage.usage import UsageRepository
from core.strategy_config import get_strategy_registry
from monitoring.langfuse_client import create_langfuse_client


@st.cache_resource
def get_db_connection():
    conn = get_connection(config.DB_PATH)
    init_db(conn)
    return conn


@st.cache_resource
def get_encryption_service():
    if config.DEMO_MODE:
        return PassthroughEncryptionService()
    return build_encryption_service(config.ENCRYPTION_KEY, "data/salt.bin")


@st.cache_resource
def get_positions_repo() -> PositionsRepository:
    return PositionsRepository(get_db_connection(), get_encryption_service())


@st.cache_resource
def get_market_repo() -> MarketDataRepository:
    return MarketDataRepository(get_db_connection())


@st.cache_resource
def get_asset_classes() -> AssetClassRegistry:
    return get_asset_class_registry()


@st.cache_resource
def get_portfolio_agent() -> PortfolioAgent:
    llm = _make_ollama_provider("portfolio_chat")
    return PortfolioAgent(positions_repo=get_positions_repo(), llm=llm)


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
    return agent


@st.cache_resource
def get_research_repo() -> ResearchRepository:
    return ResearchRepository(get_db_connection())


@st.cache_resource
def get_news_repo() -> NewsRepository:
    return NewsRepository(get_db_connection())


@st.cache_resource
def get_rebalance_repo() -> RebalanceRepository:
    return RebalanceRepository(get_db_connection())


@st.cache_resource
def get_search_repo() -> SearchRepository:
    return SearchRepository(get_db_connection())


@st.cache_resource
def get_usage_repo() -> UsageRepository:
    return UsageRepository(get_db_connection())


@st.cache_resource
def get_skills_repo() -> SkillsRepository:
    repo = SkillsRepository(get_db_connection())
    _seed_default_skills(repo)
    return repo


def _seed_default_skills(repo: SkillsRepository) -> None:
    """Seed all areas from config/default_skills.yaml on first startup."""
    import yaml
    from pathlib import Path
    path = Path(__file__).parent / "config" / "default_skills.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    for area, skills_list in (data.get("skills") or {}).items():
        repo.seed_if_empty(area, skills_list or [])


def _make_claude_provider(model: str, agent_name: str) -> ClaudeProvider:
    provider = ClaudeProvider(
        api_key=config.ANTHROPIC_API_KEY,
        model=model,
    )
    provider.on_usage = lambda i, o: get_usage_repo().record(agent_name, model, i, o)
    return provider


def _make_ollama_provider(agent_name: str) -> "OllamaProvider":
    provider = OllamaProvider(host=config.OLLAMA_HOST, model=config.OLLAMA_MODEL)
    provider.on_usage = lambda i, o: get_usage_repo().record(agent_name, config.OLLAMA_MODEL, i, o)
    return provider


@st.cache_resource
def get_research_agent() -> ResearchAgent:
    llm = _make_claude_provider("claude-haiku-4-5-20251001", "research_chat")
    return ResearchAgent(
        positions_repo=get_positions_repo(),
        research_repo=get_research_repo(),
        llm=llm,
        strategy_registry=get_strategy_registry(),
    )


@st.cache_resource
def get_news_agent() -> NewsAgent:
    llm = _make_claude_provider("claude-haiku-4-5-20251001", "news_digest")
    return NewsAgent(llm=llm)


@st.cache_resource
def get_search_agent() -> SearchAgent:
    llm = _make_claude_provider("claude-sonnet-4-6", "investment_search")
    return SearchAgent(
        positions_repo=get_positions_repo(),
        search_repo=get_search_repo(),
        llm=llm,
    )


@st.cache_resource
def get_rebalance_agent() -> RebalanceAgent:
    llm = _make_ollama_provider("rebalance_chat")
    return RebalanceAgent(
        positions_repo=get_positions_repo(),
        market_repo=get_market_repo(),
        llm=llm,
    )


@st.cache_resource
def get_langfuse_client():
    return create_langfuse_client(
        public_key=config.LANGFUSE_PUBLIC_KEY,
        secret_key=config.LANGFUSE_SECRET_KEY,
        host=config.LANGFUSE_HOST,
    )
