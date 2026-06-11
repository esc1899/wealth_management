"""
Streamlit cache resource facade — singletons for agents and repositories.

All implementation details are in state_* modules. This file re-exports them
for zero-disruption migration from monolithic state.py.
"""

import nest_asyncio

nest_asyncio.apply()

# Database and encryption
from state_db import get_db_connection, get_encryption_service

# Repositories (18 total)
from state_repos import (
    get_positions_repo,
    get_market_repo,
    get_app_config_repo,
    get_research_repo,
    get_news_repo,
    get_search_repo,
    get_usage_repo,
    get_skills_repo,
    get_storychecker_repo,
    get_analyses_repo,
    get_scheduled_jobs_repo,
    get_scheduled_job_runs_repo,
    get_structural_scans_repo,
    get_dividend_snapshot_repo,
    get_watchlist_checker_repo,
    get_wealth_snapshot_repo,
    get_portfolio_story_repo,
    get_agent_runs_repo,
    get_cowork_repo,
    get_monthly_digest_repo,
    get_yearly_digest_repo,
    get_sector_rotation_repo,
    get_research_queue_repo,
)

# Agents
from state_agents import (
    get_portfolio_agent,
    get_market_agent,
    get_research_agent,
    get_news_agent,
    get_search_agent,
    get_storychecker_agent,
    get_structural_change_agent,
    get_fundamental_analyzer_agent,
    get_consensus_gap_agent,
    get_capital_allocator_agent,
    get_capital_allocator_repo,
    get_devils_advocate_agent,
    get_devils_advocate_repo,
    get_portfolio_robustness_agent,
    get_portfolio_robustness_repo,
    get_agent_scheduler,
    get_wealth_snapshot_agent,
    get_portfolio_story_agent,
    get_watchlist_checker_agent,
    get_tax_loss_harvesting_agent,
    get_dividend_calendar_agent,
    get_cowork_watcher,
    get_sector_rotation_agent,
)

# Services
from state_services import (
    get_position_story_service,
    get_portfolio_comment_model,
    get_portfolio_comment_service,
    get_analysis_service,
    get_portfolio_service,
)

__all__ = [
    "get_db_connection",
    "get_encryption_service",
    "get_positions_repo",
    "get_market_repo",
    "get_app_config_repo",
    "get_research_repo",
    "get_news_repo",
    "get_search_repo",
    "get_usage_repo",
    "get_skills_repo",
    "get_storychecker_repo",
    "get_analyses_repo",
    "get_scheduled_jobs_repo",
    "get_scheduled_job_runs_repo",
    "get_structural_scans_repo",
    "get_dividend_snapshot_repo",
    "get_watchlist_checker_repo",
    "get_wealth_snapshot_repo",
    "get_portfolio_story_repo",
    "get_agent_runs_repo",
    "get_cowork_repo",
    "get_monthly_digest_repo",
    "get_yearly_digest_repo",
    "get_sector_rotation_repo",
    "get_research_queue_repo",
    "get_portfolio_agent",
    "get_market_agent",
    "get_research_agent",
    "get_news_agent",
    "get_search_agent",
    "get_storychecker_agent",
    "get_structural_change_agent",
    "get_fundamental_analyzer_agent",
    "get_consensus_gap_agent",
    "get_capital_allocator_agent",
    "get_capital_allocator_repo",
    "get_devils_advocate_agent",
    "get_devils_advocate_repo",
    "get_portfolio_robustness_agent",
    "get_portfolio_robustness_repo",
    "get_agent_scheduler",
    "get_wealth_snapshot_agent",
    "get_portfolio_story_agent",
    "get_watchlist_checker_agent",
    "get_tax_loss_harvesting_agent",
    "get_dividend_calendar_agent",
    "get_cowork_watcher",
    "get_sector_rotation_agent",
    "get_position_story_service",
    "get_portfolio_comment_model",
    "get_portfolio_comment_service",
    "get_analysis_service",
    "get_portfolio_service",
]
