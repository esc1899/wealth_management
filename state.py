"""
Shared Streamlit cache resources — singletons for agents and repositories.
"""

import nest_asyncio
import streamlit as st

nest_asyncio.apply()

from config import config
from agents.consensus_gap_agent import ConsensusGapAgent
from agents.fundamental_agent import FundamentalAgent
from agents.market_data_agent import MarketDataAgent
from agents.market_data_fetcher import MarketDataFetcher, RateLimiter
from agents.news_agent import NewsAgent
from agents.portfolio_agent import PortfolioAgent
from agents.rebalance_agent import RebalanceAgent
from agents.research_agent import ResearchAgent
from agents.search_agent import SearchAgent
from agents.storychecker_agent import StorycheckerAgent
from agents.structural_change_agent import StructuralChangeAgent
from core.storage.analyses import PositionAnalysesRepository
from core.storage.storychecker import StorycheckerRepository
from core.storage.structural_scans import StructuralScansRepository
from core.asset_class_config import get_asset_class_registry, AssetClassRegistry
from core.llm.claude import ClaudeProvider
from core.llm.local import OllamaProvider
from core.encryption import PassthroughEncryptionService
from core.storage.app_config import AppConfigRepository
from core.storage.base import build_encryption_service, get_connection, init_db, migrate_db
from core.storage.market_data import MarketDataRepository
from core.storage.positions import PositionsRepository
from core.storage.news import NewsRepository
from core.storage.rebalance import RebalanceRepository
from core.storage.research import ResearchRepository
from core.storage.scheduled_jobs import ScheduledJobsRepository
from core.storage.search import SearchRepository
from core.storage.skills import SkillsRepository
from core.storage.usage import UsageRepository
from core.scheduler import AgentSchedulerService
from core.strategy_config import get_strategy_registry
from monitoring.langfuse_client import create_langfuse_client

# Default model values (overridable via app_config)
_DEFAULT_OLLAMA_MODEL = config.OLLAMA_MODEL
_DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5-20251001"


@st.cache_resource
def get_db_connection():
    conn = get_connection(config.DB_PATH)
    init_db(conn)
    migrate_db(conn)
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
def get_app_config_repo() -> AppConfigRepository:
    return AppConfigRepository(get_db_connection())


@st.cache_resource
def get_asset_classes() -> AssetClassRegistry:
    return get_asset_class_registry()


@st.cache_resource
def get_portfolio_agent() -> PortfolioAgent:
    model = _get_agent_model("portfolio", "ollama", _DEFAULT_OLLAMA_MODEL)
    llm = OllamaProvider(host=config.OLLAMA_HOST, model=model)
    llm.on_usage = lambda i, o, skill=None, dur=None: get_usage_repo().record("portfolio_chat", model, i, o, skill=skill, duration_ms=dur)
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
    # Seed hidden system skills (INSERT OR IGNORE — safe to run every startup)
    system_skills = data.get("system") or []
    repo.seed_system_skills(system_skills)
    # Seed new visible skills that may not be in existing installations
    # (INSERT OR IGNORE per name+area — never overwrites user edits)
    _skills_data = data.get("skills") or {}
    repo.seed_new_skills("rebalance", [
        s for s in _skills_data.get("rebalance", [])
        if s["name"] in {
            "Wu-Wei Strategie",
        }
    ])
    repo.seed_new_skills("storychecker", [
        s for s in _skills_data.get("storychecker", [])
        if s["name"] in {
            "Lindy + Potential",
        }
    ])
    repo.seed_new_skills("structural_scan", _skills_data.get("structural_scan", []))
    repo.seed_new_skills("consensus_gap", _skills_data.get("consensus_gap", []))
    repo.seed_new_skills("fundamental", _skills_data.get("fundamental", []))


def _make_claude_provider(model: str, agent_name: str) -> ClaudeProvider:
    provider = ClaudeProvider(
        api_key=config.ANTHROPIC_API_KEY,
        model=model,
    )
    provider.on_usage = lambda i, o, skill=None, dur=None: get_usage_repo().record(agent_name, model, i, o, skill=skill, duration_ms=dur)
    return provider


def _make_ollama_provider(model: str, agent_name: str) -> "OllamaProvider":
    provider = OllamaProvider(host=config.OLLAMA_HOST, model=model)
    provider.on_usage = lambda i, o, skill=None, dur=None: get_usage_repo().record(agent_name, model, i, o, skill=skill, duration_ms=dur)
    return provider


def _get_agent_model(agent_key: str, model_type: str, default: str) -> str:
    """Return model for a specific agent. Falls back to global setting then env default."""
    repo = get_app_config_repo()
    return (
        repo.get(f"model_{model_type}_{agent_key}")
        or repo.get(f"model_{model_type}")
        or default
    )


@st.cache_resource
def get_research_agent() -> ResearchAgent:
    model = _get_agent_model("research", "claude", _DEFAULT_CLAUDE_MODEL)
    llm = _make_claude_provider(model, "research_chat")
    return ResearchAgent(
        positions_repo=get_positions_repo(),
        research_repo=get_research_repo(),
        llm=llm,
        strategy_registry=get_strategy_registry(),
    )


@st.cache_resource
def get_news_agent() -> NewsAgent:
    model = _get_agent_model("news", "claude", _DEFAULT_CLAUDE_MODEL)
    llm = _make_claude_provider(model, "news_digest")
    return NewsAgent(llm=llm)


@st.cache_resource
def get_search_agent() -> SearchAgent:
    model = _get_agent_model("search", "claude", "claude-sonnet-4-6")
    llm = _make_claude_provider(model, "investment_search")
    return SearchAgent(
        positions_repo=get_positions_repo(),
        search_repo=get_search_repo(),
        llm=llm,
    )


@st.cache_resource
def get_storychecker_repo() -> StorycheckerRepository:
    return StorycheckerRepository(get_db_connection())


@st.cache_resource
def get_analyses_repo() -> PositionAnalysesRepository:
    return PositionAnalysesRepository(get_db_connection())


@st.cache_resource
def get_storychecker_agent() -> StorycheckerAgent:
    model = _get_agent_model("storychecker", "claude", _DEFAULT_CLAUDE_MODEL)
    llm = _make_claude_provider(model, "storychecker")
    return StorycheckerAgent(
        positions_repo=get_positions_repo(),
        storychecker_repo=get_storychecker_repo(),
        analyses_repo=get_analyses_repo(),
        llm=llm,
    )


@st.cache_resource
def get_rebalance_agent() -> RebalanceAgent:
    model = _get_agent_model("rebalance", "ollama", _DEFAULT_OLLAMA_MODEL)
    llm = _make_ollama_provider(model, "rebalance_chat")
    return RebalanceAgent(
        positions_repo=get_positions_repo(),
        market_repo=get_market_repo(),
        analyses_repo=get_analyses_repo(),
        llm=llm,
        skills_repo=get_skills_repo(),
    )


@st.cache_resource
def get_scheduled_jobs_repo() -> ScheduledJobsRepository:
    return ScheduledJobsRepository(get_db_connection())


@st.cache_resource
def get_structural_scans_repo() -> StructuralScansRepository:
    return StructuralScansRepository(get_db_connection())


@st.cache_resource
def get_structural_change_agent(claude_model: str = "") -> StructuralChangeAgent:
    model = _get_agent_model("structural_scan", "claude", "claude-sonnet-4-6")
    llm = _make_claude_provider(model, "structural_scan")
    return StructuralChangeAgent(
        positions_repo=get_positions_repo(),
        llm=llm,
    )


@st.cache_resource
def get_fundamental_agent() -> FundamentalAgent:
    model = _get_agent_model("fundamental", "claude", "claude-sonnet-4-6")
    llm = _make_claude_provider(model, "fundamental")
    return FundamentalAgent(llm=llm)


@st.cache_resource
def get_consensus_gap_agent(claude_model: str = "") -> ConsensusGapAgent:
    model = _get_agent_model("consensus_gap", "claude", "claude-sonnet-4-6")
    llm = _make_claude_provider(model, "consensus_gap")
    return ConsensusGapAgent(llm=llm)


@st.cache_resource
def get_agent_scheduler() -> AgentSchedulerService:
    service = AgentSchedulerService(
        db_path=config.DB_PATH,
        encryption_key=config.ENCRYPTION_KEY,
        anthropic_api_key=config.ANTHROPIC_API_KEY,
        default_claude_model=_DEFAULT_CLAUDE_MODEL,
    )
    service.start()
    return service


@st.cache_resource
def get_langfuse_client():
    return create_langfuse_client(
        public_key=config.LANGFUSE_PUBLIC_KEY,
        secret_key=config.LANGFUSE_SECRET_KEY,
        host=config.LANGFUSE_HOST,
    )
