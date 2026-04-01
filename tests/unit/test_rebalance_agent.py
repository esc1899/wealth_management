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
