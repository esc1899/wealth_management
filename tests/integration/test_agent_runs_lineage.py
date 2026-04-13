"""Integration tests for agent execution lineage tracking."""

import pytest
from datetime import date
from core.storage.base import get_connection, init_db, migrate_db
from core.storage.agent_runs import AgentRunsRepository
from core.storage.analyses import PositionAnalysesRepository
from core.storage.positions import PositionsRepository
from core.storage.models import Position


@pytest.fixture
def db_conn():
    """Real in-memory SQLite connection."""
    conn = get_connection(":memory:")
    init_db(conn)
    migrate_db(conn)
    return conn


@pytest.fixture
def agent_runs_repo(db_conn):
    return AgentRunsRepository(db_conn)


@pytest.fixture
def positions_repo(db_conn):
    from core.encryption import PassthroughEncryptionService
    return PositionsRepository(db_conn, PassthroughEncryptionService())


@pytest.fixture
def analyses_repo(db_conn):
    return PositionAnalysesRepository(db_conn)


class TestAgentRunsLineageIntegration:
    """Integration: agent_runs table with real DB and repositories."""

    def test_log_and_retrieve_agent_run(self, agent_runs_repo):
        """Log an agent run and retrieve it."""
        run_id = agent_runs_repo.log_run(
            agent_name="watchlist_checker",
            model="llama3.3:70b",
            skills_used=["Check"],
            agent_deps=["portfolio_data"],
            output_summary="Checked 5 positions",
        )

        run = agent_runs_repo.get_latest_run("watchlist_checker")
        assert run is not None
        assert run["agent_name"] == "watchlist_checker"
        assert run["model"] == "llama3.3:70b"
        assert run["skills_used"] == ["Check"]
        assert run["agent_deps"] == ["portfolio_data"]

    def test_multiple_agent_runs_ordering(self, agent_runs_repo):
        """Multiple runs are ordered by id (newest first)."""
        # Log 3 runs
        for i in range(3):
            agent_runs_repo.log_run(
                agent_name="portfolio_story",
                output_summary=f"Run {i}",
            )

        recent = agent_runs_repo.get_recent_runs(limit=3)
        assert len(recent) == 3
        # Most recent first (highest ID)
        assert recent[0]["output_summary"] == "Run 2"
        assert recent[1]["output_summary"] == "Run 1"
        assert recent[2]["output_summary"] == "Run 0"

    def test_agent_lineage_across_repos(
        self, agent_runs_repo, positions_repo, analyses_repo
    ):
        """Full lineage: Position → Analysis → Agent Run."""
        # Create a position
        pos = Position(
            asset_class="Aktie",
            investment_type="Stock",
            name="Apple",
            ticker="AAPL",
            unit="EUR",
            added_date=date.today(),
            in_portfolio=True,
        )
        pos = positions_repo.add(pos)

        # Log an analysis
        analyses_repo.save(
            position_id=pos.id,
            agent="watchlist_checker",
            skill_name="",
            verdict="sehr_passend",
            summary="Good fit",
        )

        # Log agent run
        agent_runs_repo.log_run(
            agent_name="watchlist_checker",
            agent_deps=["portfolio_data"],
            output_summary="Analyzed AAPL",
        )

        # Verify lineage
        analysis = analyses_repo.get_latest(pos.id, "watchlist_checker")
        assert analysis is not None
        assert analysis.verdict == "sehr_passend"

        run = agent_runs_repo.get_latest_run("watchlist_checker")
        assert run is not None
        assert "portfolio_data" in run["agent_deps"]

    def test_context_hierarchy_tracking(self, agent_runs_repo):
        """Log multi-level agent hierarchy."""
        # Ebene 0: portfolio data
        agent_runs_repo.log_run(
            agent_name="portfolio_data",
            output_summary="5 positions",
        )

        # Ebene 1: analyst verdicts
        for agent in ["storychecker", "fundamental"]:
            agent_runs_repo.log_run(
                agent_name=agent,
                agent_deps=["portfolio_data"],
                output_summary=f"{agent} run",
            )

        # Ebene 2: investment compass (uses Ebene 1)
        agent_runs_repo.log_run(
            agent_name="investment_kompass",
            agent_deps=["portfolio_data", "storychecker", "fundamental"],
            output_summary="Full analysis",
        )

        # Verify hierarchy
        compass_run = agent_runs_repo.get_latest_run("investment_kompass")
        assert len(compass_run["agent_deps"]) == 3
        assert "storychecker" in compass_run["agent_deps"]

        # Get all runs at one level
        level1_runs = agent_runs_repo.get_runs_for_agents(
            ["storychecker", "fundamental"]
        )
        assert len(level1_runs) == 2


class TestWatchlistCheckerIntegration:
    """Integration: WatchlistCheckerAgent with real repositories."""

    @pytest.mark.asyncio
    async def test_watchlist_checker_with_real_analyses_repo(
        self, positions_repo, analyses_repo
    ):
        """Watchlist checker works with real PositionAnalysesRepository."""
        from unittest.mock import AsyncMock
        from agents.watchlist_checker_agent import WatchlistCheckerAgent

        # Create watchlist positions
        positions = []
        for ticker in ["AAPL", "MSFT"]:
            pos = Position(
                asset_class="Aktie",
                investment_type="Stock",
                name=ticker,
                ticker=ticker,
                unit="EUR",
                added_date=date.today(),
                in_portfolio=False,
                in_watchlist=True,
            )
            positions.append(positions_repo.add(pos))

        # Mock LLM
        mock_llm = AsyncMock()
        mock_llm.model = "test-model"

        async def mock_chat(*args, **kwargs):
            return """## Apple (AAPL)
**Fit:** 🟢 Sehr passend
> Good fit

## Microsoft (MSFT)
**Fit:** 🟡 Passend
> Okay fit"""

        mock_llm.chat = mock_chat

        agent = WatchlistCheckerAgent(
            positions_repo=positions_repo,
            analyses_repo=analyses_repo,
            llm=mock_llm,
        )

        # Run check
        result = await agent.check_watchlist(
            portfolio_snapshot="Test portfolio",
            watchlist_positions=positions,
        )

        # Verify results persisted to real repo
        assert len(result.position_fits) == 2
        for fit in result.position_fits:
            saved = analyses_repo.get_latest(fit.position_id, "watchlist_checker")
            assert saved is not None
            assert saved.verdict == fit.verdict


class TestInvestmentCompassIntegration:
    """Integration: InvestmentCompassAgent with real context repositories."""

    @pytest.mark.asyncio
    async def test_compass_builds_context_from_repos(
        self, positions_repo, analyses_repo, agent_runs_repo
    ):
        """Investment Compass builds context from real repositories."""
        from unittest.mock import AsyncMock
        from agents.investment_compass_agent import InvestmentCompassAgent

        # Create position
        pos = Position(
            asset_class="Aktie",
            investment_type="Stock",
            name="Apple",
            ticker="AAPL",
            unit="EUR",
            added_date=date.today(),
            in_portfolio=True,
        )
        pos = positions_repo.add(pos)

        # Add analysis (Ebene 1 context)
        analyses_repo.save(
            position_id=pos.id,
            agent="storychecker",
            skill_name="",
            verdict="intact",
            summary="Thesis still valid",
        )

        # Mock LLM
        mock_llm = AsyncMock()
        mock_llm.model = "test-model"
        mock_llm.chat = AsyncMock(return_value="Investment analysis here")

        agent = InvestmentCompassAgent(
            positions_repo=positions_repo,
            market_repo=None,  # Not needed for context build
            analyses_repo=analyses_repo,
            portfolio_story_repo=None,
            llm=mock_llm,
            skills_repo=None,
        )

        # Run analysis
        result = await agent.analyze(
            user_query="Should I hold AAPL?",
            skill_name="Buffett",
        )

        # Verify context included verdicts from Ebene 1
        assert "storychecker" in result.lineage["agents_used"]
        assert result.response == "Investment analysis here"

        # Verify LLM was called with proper context
        mock_llm.chat.assert_called_once()
        call_args = mock_llm.chat.call_args
        message_content = call_args[0][0][0].content
        assert "Storychecker" in message_content  # Verdict section should appear
