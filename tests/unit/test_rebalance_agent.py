"""
Unit tests for RebalanceAgent.
LLM and repositories are mocked — no external calls.
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.rebalance_agent import RebalanceAgent
from core.storage.models import Position, PriceRecord


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def make_position(ticker: str, quantity: float, purchase_price: float) -> Position:
    return Position(
        id=1,
        ticker=ticker,
        name=f"{ticker} Corp",
        asset_class="Aktie",
        investment_type="Wertpapiere",
        quantity=quantity,
        unit="Stück",
        purchase_price=purchase_price,
        purchase_date=date(2022, 1, 1),
        added_date=date.today(),
        in_portfolio=True,
    )


def make_price(symbol: str, price: float) -> PriceRecord:
    return PriceRecord(
        symbol=symbol,
        price_eur=price,
        currency_original="EUR",
        price_original=price,
        exchange_rate=1.0,
        fetched_at=datetime.now(timezone.utc),
    )


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def mock_positions_repo():
    repo = MagicMock()
    repo.get_portfolio.return_value = [
        make_position("AAPL", 10.0, 150.0),
        make_position("MSFT", 5.0, 300.0),
    ]
    repo.get_watchlist.return_value = []
    return repo


@pytest.fixture
def mock_market_repo():
    repo = MagicMock()
    repo.get_price.side_effect = lambda ticker: {
        "AAPL": make_price("AAPL", 175.0),
        "MSFT": make_price("MSFT", 380.0),
    }.get(ticker)
    return repo


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.chat = AsyncMock(return_value="🌾 AAPL has grown above target weight. Consider harvesting.")
    return llm


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    session = MagicMock()
    session.id = 1
    session.skill_name = "Farmer Strategy"
    session.skill_prompt = "Sow, harvest, prune."
    session.portfolio_snapshot = ""
    repo.create_session.return_value = session
    repo.get_session.return_value = session
    repo.get_messages.return_value = []
    return repo


@pytest.fixture
def agent(mock_positions_repo, mock_market_repo, mock_llm):
    mock_analyses_repo = MagicMock()
    mock_analyses_repo.get_latest_bulk.return_value = {}
    return RebalanceAgent(
        positions_repo=mock_positions_repo,
        market_repo=mock_market_repo,
        analyses_repo=mock_analyses_repo,
        llm=mock_llm,
    )


# ------------------------------------------------------------------
# start_session
# ------------------------------------------------------------------

class TestAnalyze:
    @pytest.mark.asyncio
    async def test_returns_llm_response(self, agent, mock_llm, mock_repo):
        _, result = await agent.start_session("Farmer Strategy", "Sow, harvest, prune.", user_context="", repo=mock_repo)
        assert "AAPL" in result or "harvest" in result

    @pytest.mark.asyncio
    async def test_empty_portfolio_returns_message(self, agent, mock_positions_repo, mock_llm, mock_repo):
        mock_positions_repo.get_portfolio.return_value = []
        _, result = await agent.start_session("Farmer Strategy", "Analyze.", user_context="", repo=mock_repo)
        # LLM still gets called; portfolio_snapshot says "Portfolio is empty."
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        system_msg = next((m for m in messages if m.role.value == "system"), None)
        assert "empty" in system_msg.content.lower()

    @pytest.mark.asyncio
    async def test_calls_llm_with_portfolio_context(self, agent, mock_llm, mock_repo):
        await agent.start_session("Farmer Strategy", "Sow, harvest, prune.", user_context="", repo=mock_repo)
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        all_content = " ".join(m.content for m in messages)
        assert "AAPL" in all_content
        assert "MSFT" in all_content

    @pytest.mark.asyncio
    async def test_system_contains_skill_name(self, agent, mock_llm, mock_repo):
        await agent.start_session("Farmer Strategy", "Sow, harvest, prune.", user_context="", repo=mock_repo)
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        system_msg = next((m for m in messages if m.role.value == "system"), None)
        assert system_msg is not None
        assert "Farmer Strategy" in system_msg.content

    @pytest.mark.asyncio
    async def test_portfolio_context_includes_values(self, agent, mock_llm, mock_repo):
        await agent.start_session("Farmer Strategy", "Analyze.", user_context="", repo=mock_repo)
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        # Portfolio snapshot is in the system message
        system_msg = next((m for m in messages if m.role.value == "system"), None)
        # 10 AAPL × €175 = €1,750
        assert "1,750" in system_msg.content or "175" in system_msg.content

    @pytest.mark.asyncio
    async def test_portfolio_context_includes_weights(self, agent, mock_llm, mock_repo):
        """Total = 10*175 + 5*380 = 1750 + 1900 = 3650. AAPL = 47.9%, MSFT = 52.1%"""
        await agent.start_session("Farmer Strategy", "Analyze.", user_context="", repo=mock_repo)
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        system_msg = next((m for m in messages if m.role.value == "system"), None)
        assert "%" in system_msg.content

    @pytest.mark.asyncio
    async def test_positions_without_price_handled_gracefully(self, agent, mock_market_repo, mock_llm, mock_repo):
        mock_market_repo.get_price.return_value = None
        _, result = await agent.start_session("Farmer Strategy", "Analyze.", user_context="", repo=mock_repo)
        assert result  # should not raise

    @pytest.mark.asyncio
    async def test_excluded_position_marked_in_snapshot(self, mock_positions_repo, mock_market_repo, mock_llm, mock_repo):
        excluded = make_position("EXCL", 10.0, 100.0)
        excluded = excluded.model_copy(update={"rebalance_excluded": True})
        mock_positions_repo.get_portfolio.return_value = [excluded]
        mock_analyses_repo = MagicMock()
        mock_analyses_repo.get_latest_bulk.return_value = {}
        agent = RebalanceAgent(
            positions_repo=mock_positions_repo,
            market_repo=mock_market_repo,
            analyses_repo=mock_analyses_repo,
            llm=mock_llm,
        )
        await agent.start_session("Farmer Strategy", "Analyze.", user_context="", repo=mock_repo)
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        system_msg = next((m for m in messages if m.role.value == "system"), None)
        assert "AUSGESCHLOSSEN" in system_msg.content

    @pytest.mark.asyncio
    async def test_snapshot_contains_josef_regel_section(self, agent, mock_llm, mock_repo):
        await agent.start_session("Farmer Strategy", "Analyze.", user_context="", repo=mock_repo)
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        system_msg = next((m for m in messages if m.role.value == "system"), None)
        assert "Josef" in system_msg.content

    @pytest.mark.asyncio
    async def test_watchlist_candidates_shown_in_snapshot(
        self, mock_positions_repo, mock_market_repo, mock_llm, mock_repo
    ):
        from datetime import date as dt
        watchlist_pos = Position(
            id=99,
            ticker="CAND",
            name="Buy Candidate",
            asset_class="Aktie",
            investment_type="Wertpapiere",
            unit="Stück",
            added_date=dt.today(),
            in_portfolio=False,
            in_watchlist=True,
            story="Strong growth potential in AI sector.",
        )
        mock_positions_repo.get_watchlist.return_value = [watchlist_pos]
        mock_analyses_repo = MagicMock()
        mock_analyses_repo.get_latest_bulk.return_value = {}
        agent = RebalanceAgent(
            positions_repo=mock_positions_repo,
            market_repo=mock_market_repo,
            analyses_repo=mock_analyses_repo,
            llm=mock_llm,
        )
        await agent.start_session("Farmer Strategy", "Analyze.", user_context="", repo=mock_repo)
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        system_msg = next((m for m in messages if m.role.value == "system"), None)
        assert "CAND" in system_msg.content or "Buy Candidate" in system_msg.content


# ------------------------------------------------------------------
# _get_position_value
# ------------------------------------------------------------------

class TestPositionValue:
    """
    Tests for _get_position_value — the calculation that fixed precious metals.
    Bug: 100g gold at €2800/troy oz returned €280,000 instead of €9,002.
    """

    def _make_agent(self, market_repo):
        return RebalanceAgent(
            positions_repo=MagicMock(),
            market_repo=market_repo,
            analyses_repo=MagicMock(),
            llm=MagicMock(),
        )

    def test_standard_stock_quantity_times_price(self):
        """Stock value = quantity × current price (in EUR)."""
        price = make_price("AAPL", 175.0)
        market_repo = MagicMock()
        market_repo.get_price.side_effect = lambda t: price if t == "AAPL" else None

        pos = make_position("AAPL", 10.0, 150.0)
        agent = self._make_agent(market_repo)
        assert agent._get_position_value(pos) == 1750.0

    def test_precious_metal_gram_uses_troy_oz_conversion(self):
        """
        Precious metals stored in grams with price in €/troy oz.
        100g at €2800/troy oz = 100 × (2800 / 31.1035) ≈ €9,002 — NOT 100 × 2800 = €280,000.
        """
        price = make_price("GC=F", 2800.0)
        market_repo = MagicMock()
        market_repo.get_price.side_effect = lambda t: price if t == "GC=F" else None

        pos = make_position("GC=F", 100.0, 80.0)
        pos = pos.model_copy(update={"unit": "g"})
        agent = self._make_agent(market_repo)

        value = agent._get_position_value(pos)
        expected = 100.0 * (2800.0 / 31.1035)
        assert value is not None
        assert abs(value - expected) < 1.0
        assert value < 15_000  # Sanity: not the 100x-inflated €280,000

    def test_missing_market_price_returns_none(self):
        """No price in market data → None (data not yet fetched or invalid ticker)."""
        market_repo = MagicMock()
        market_repo.get_price.return_value = None

        pos = make_position("AAPL", 10.0, 150.0)
        agent = self._make_agent(market_repo)
        assert agent._get_position_value(pos) is None


# ------------------------------------------------------------------
# Josef's Regel & Portfolio Totals
# ------------------------------------------------------------------

class TestJosefRule:
    """
    Test that portfolio totals are calculated correctly.
    Bug: Positions with both in_portfolio=1 and in_watchlist=1 were double-counted,
    causing allocation percentages to sum to 200% instead of 100%.
    """

    @pytest.mark.asyncio
    async def test_watchlist_positions_excluded_from_portfolio_totals(self, mock_llm, mock_repo):
        """
        REGRESSION TEST for bug: Positions with both in_portfolio=1 and in_watchlist=1
        were double-counted in portfolio totals, causing allocation % to sum to 200% instead of 100%.

        Setup:
        - Portfolio: AAPL (€1000) + MSFT (€2000) = €3000 total
        - MSFT is ALSO in watchlist (both flags = 1)
        - Pure watchlist: GOOG (not in portfolio)

        Expected: AAPL 33.3%, MSFT 66.7% in Josef's Regel (sum = 100%)
        The bug was: MSFT got counted twice, making sum = 200%
        """
        # Pure portfolio position
        pos_a = make_position("AAPL", 10.0, 100.0)
        pos_a = pos_a.model_copy(update={"id": 1, "ticker": "AAPL", "in_watchlist": False})

        # Position that is BOTH in portfolio AND watchlist (the problematic case)
        pos_b = make_position("MSFT", 5.0, 400.0)
        pos_b = pos_b.model_copy(update={"id": 2, "ticker": "MSFT", "in_watchlist": True})

        # Pure watchlist (NOT in portfolio)
        pos_goog = make_position("GOOG", 20.0, 150.0)
        pos_goog = pos_goog.model_copy(update={
            "id": 3, "ticker": "GOOG", "in_portfolio": False, "in_watchlist": True
        })

        # Setup mocks
        positions_repo = MagicMock()
        positions_repo.get_portfolio.return_value = [pos_a, pos_b]  # Only portfolio positions
        positions_repo.get_watchlist.return_value = [pos_b, pos_goog]  # Both hybrid and pure watchlist

        market_repo = MagicMock()
        market_repo.get_price.side_effect = lambda ticker: {
            "AAPL": make_price("AAPL", 100.0),  # 10 × 100 = €1000
            "MSFT": make_price("MSFT", 400.0),  # 5 × 400 = €2000
            "GOOG": make_price("GOOG", 150.0),  # 20 × 150 = €3000 (watchlist only)
        }.get(ticker)

        analyses_repo = MagicMock()
        analyses_repo.get_latest_bulk.return_value = {}

        agent = RebalanceAgent(
            positions_repo=positions_repo,
            market_repo=market_repo,
            analyses_repo=analyses_repo,
            llm=mock_llm,
        )

        # Generate snapshot
        await agent.start_session("Test", "Test strategy", user_context="", repo=mock_repo)

        # Extract the snapshot from LLM call
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        system_msg = next((m for m in messages if m.role.value == "system"), None)
        snapshot = system_msg.content

        # Assertions
        assert "Josef" in snapshot, "Josef's Regel section should be present"
        assert "Aktien" in snapshot, "Aktien category should be present (both stocks are Wertpapiere)"

        # GOOG should NOT appear in the portfolio section (it's watchlist-only)
        tradeable_section = snapshot.split("### Nicht-handelbares Vermögen")[0]  # Get portfolio section only
        assert "GOOG" not in tradeable_section, "Watchlist-only position GOOG should not be in portfolio section"

        # MSFT and AAPL should be in handelbares portfolio
        assert "MSFT" in snapshot
        assert "AAPL" in snapshot

        # Critical: Check that percentages don't sum to 200%
        # The bug manifested as "Ist" percentages summing to 200%
        assert "200%" not in snapshot, "Bug: allocation percentages summed to 200% instead of 100%"

        # Positive check: sum of "Ist" column should be ~100% (not 200%)
        # The table format is: | Kategorie | Wert | Ist | Ziel | Abweichung |
        # We need to extract only the "Ist" column values
        lines = snapshot.split("\n")
        josef_section = False
        ist_percentages = []
        header_found = False

        for line in lines:
            if "Josef" in line:
                josef_section = True
                continue
            if not josef_section:
                continue
            if not header_found and "Ist" in line and "Ziel" in line:
                header_found = True
                continue
            if header_found and "%" in line and "|" in line:
                # Parse table row: | Kategorie | €value | 33.3% | 33.3% | +0.0% |
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 5:
                    # Index 3 should be the "Ist" column (0-indexed: 0=empty, 1=category, 2=value, 3=Ist, 4=Ziel, 5=Abweichung)
                    ist_col = parts[3]  # The "Ist" percentage
                    if ist_col and "%" in ist_col:
                        try:
                            pct = float(ist_col.rstrip("%").strip())
                            ist_percentages.append(pct)
                        except:
                            pass

        if ist_percentages:
            total = sum(ist_percentages)
            assert total < 110, f"Ist allocation sum should be ~100%, got {total}% (suggests double-counting bug)"
            # Positive: should be close to 100%
            assert total > 90, f"Ist allocation sum should be ~100%, got {total}%"
