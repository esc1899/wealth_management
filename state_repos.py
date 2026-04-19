"""
Repository factories — all 17 repository singletons.
"""

import streamlit as st

from state_db import get_db_connection, get_encryption_service
from core.storage.analyses import PositionAnalysesRepository
from core.storage.agent_runs import AgentRunsRepository
from core.storage.app_config import AppConfigRepository
from core.storage.market_data import MarketDataRepository
from core.storage.news import NewsRepository
from core.storage.portfolio_story import PortfolioStoryRepository
from core.storage.positions import PositionsRepository
from core.storage.research import ResearchRepository
from core.storage.scheduled_jobs import ScheduledJobsRepository
from core.storage.search import SearchRepository
from core.storage.skills import SkillsRepository
from core.storage.storychecker import StorycheckerRepository
from core.storage.structural_scans import StructuralScansRepository
from core.storage.usage import UsageRepository
from core.storage.watchlist_checker_repo import WatchlistCheckerRepository
from core.storage.wealth_snapshots import WealthSnapshotRepository
from core.storage.dividend_snapshots import DividendSnapshotRepository


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
def get_research_repo() -> ResearchRepository:
    return ResearchRepository(get_db_connection())


@st.cache_resource
def get_news_repo() -> NewsRepository:
    return NewsRepository(get_db_connection())


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
    repo.seed_new_skills("structural_scan", _skills_data.get("structural_scan", []))
    repo.seed_new_skills("consensus_gap", _skills_data.get("consensus_gap", []))
    repo.seed_new_skills("fundamental", _skills_data.get("fundamental", []))
    repo.seed_new_skills("portfolio_story", _skills_data.get("portfolio_story", []))
    repo.seed_new_skills("watchlist_checker", _skills_data.get("watchlist_checker", []))
    # Load private skills if config/private_skills.yaml exists (gitignored)
    private_path = Path(__file__).parent / "config" / "private_skills.yaml"
    if private_path.exists():
        with open(private_path) as f:
            private_data = yaml.safe_load(f) or {}
        for area, skills_list in (private_data.get("skills") or {}).items():
            repo.seed_new_skills(area, skills_list or [])


@st.cache_resource
def get_storychecker_repo() -> StorycheckerRepository:
    return StorycheckerRepository(get_db_connection())


@st.cache_resource
def get_analyses_repo() -> PositionAnalysesRepository:
    return PositionAnalysesRepository(get_db_connection())


@st.cache_resource
def get_scheduled_jobs_repo() -> ScheduledJobsRepository:
    return ScheduledJobsRepository(get_db_connection())


@st.cache_resource
def get_structural_scans_repo() -> StructuralScansRepository:
    return StructuralScansRepository(get_db_connection())


@st.cache_resource
def get_dividend_snapshot_repo() -> DividendSnapshotRepository:
    return DividendSnapshotRepository(get_db_connection())


@st.cache_resource
def get_watchlist_checker_repo() -> WatchlistCheckerRepository:
    return WatchlistCheckerRepository(get_db_connection())


@st.cache_resource
def get_wealth_snapshot_repo() -> WealthSnapshotRepository:
    return WealthSnapshotRepository(get_db_connection())


@st.cache_resource
def get_portfolio_story_repo() -> PortfolioStoryRepository:
    return PortfolioStoryRepository(get_db_connection(), get_encryption_service())


@st.cache_resource
def get_agent_runs_repo() -> AgentRunsRepository:
    return AgentRunsRepository(get_db_connection())


def load_cash_rule() -> dict:
    """Load cash rule configuration from config/cash_rule.yaml or defaults."""
    from pathlib import Path
    import yaml
    rule_path = Path(__file__).parent / "config" / "cash_rule.yaml"
    if rule_path.exists():
        with open(rule_path) as f:
            data = yaml.safe_load(f) or {}
            return data.get("bargeld_rule", _default_cash_rule())
    return _default_cash_rule()


def _default_cash_rule() -> dict:
    """Default cash rule if no config file exists."""
    return {
        "enabled": True,
        "target_pct": 5.0,
        "min_eur": 10000,
        "max_eur": 100000,
    }
