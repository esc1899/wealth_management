"""
End-to-end integration tests.
Uses real SQLite (in-memory) and real repositories — no storage mocking.
LLM and yfinance are mocked to avoid external dependencies.
"""

import os
import sqlite3
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.market_data_agent import MarketDataAgent
from agents.market_data_fetcher import MarketDataFetcher
from agents.portfolio_agent import PortfolioAgent
from core.encryption import EncryptionService
from core.storage.base import init_db
from core.storage.market_data import MarketDataRepository
from core.storage.models import Position, PriceRecord
from core.storage.positions import PositionsRepository


# ------------------------------------------------------------------
# Shared fixtures
# ------------------------------------------------------------------

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    init_db(c)
    return c


@pytest.fixture
def enc():
    key = os.urandom(16).hex()
    salt = os.urandom(16)
    return EncryptionService(key, salt)


@pytest.fixture
def positions_repo(conn, enc):
    return PositionsRepository(conn, enc)


@pytest.fixture
def market_repo(conn):
    return MarketDataRepository(conn)


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.model = "qwen3:8b-test"
    return llm


@pytest.fixture
def portfolio_agent(positions_repo, mock_llm):
    return PortfolioAgent(positions_repo=positions_repo, llm=mock_llm)


@pytest.fixture
def mock_fetcher():
    fetcher = MagicMock(spec=MarketDataFetcher)
    fetcher.fetch_historical.return_value = []
    return fetcher


@pytest.fixture
def market_agent(positions_repo, market_repo, mock_fetcher):
    return MarketDataAgent(
        positions_repo=positions_repo,
        market_repo=market_repo,
        fetcher=mock_fetcher,
        db_path=":memory:",
        encryption_key="test",
    )


def _make_position(ticker="AAPL", name="Apple Inc.", quantity=10, price=150.0) -> Position:
    return Position(
        ticker=ticker, name=name,
        asset_class="Aktie", investment_type="Wertpapiere",
        quantity=quantity, unit="Stück",
        purchase_price=price, purchase_date=date(2024, 1, 15),
        added_date=date(2024, 1, 15), in_portfolio=True,
    )


# ------------------------------------------------------------------
# E2E: Portfolio → Market Data → Dashboard Valuation
# ------------------------------------------------------------------

class TestPortfolioToValuation:
    def test_add_entry_appears_in_valuation(self, positions_repo, market_repo, mock_fetcher):
        positions_repo.add(_make_position("AAPL", quantity=10, price=150.0))

        agent = MarketDataAgent(
            positions_repo=positions_repo, market_repo=market_repo,
            fetcher=mock_fetcher, db_path=":memory:", encryption_key="test",
        )

        valuations = agent.get_portfolio_valuation()
        assert len(valuations) == 1
        assert valuations[0].symbol == "AAPL"
        assert valuations[0].quantity == 10
        assert valuations[0].current_price_eur is None

    def test_fetch_updates_valuation(self, positions_repo, market_repo, mock_fetcher):
        positions_repo.add(_make_position("MSFT", quantity=5, price=300.0))

        price_record = PriceRecord(
            symbol="MSFT", price_eur=350.0, currency_original="USD",
            price_original=380.0, exchange_rate=0.921,
            fetched_at=datetime.now(timezone.utc),
        )
        mock_fetcher.fetch_current_prices.return_value = ([price_record], [])

        agent = MarketDataAgent(
            positions_repo=positions_repo, market_repo=market_repo,
            fetcher=mock_fetcher, db_path=":memory:", encryption_key="test",
        )
        result = agent.fetch_all_now()

        assert result.fetched == 1
        valuations = agent.get_portfolio_valuation()
        assert valuations[0].current_price_eur == 350.0
        assert valuations[0].current_value_eur == 1750.0
        assert valuations[0].pnl_eur == 250.0
        assert abs(valuations[0].pnl_pct - (250 / 1500 * 100)) < 0.01

    def test_multiple_positions_total_value(self, positions_repo, market_repo, mock_fetcher):
        for ticker, qty, price in [("AAPL", 10, 150.0), ("MSFT", 5, 300.0), ("GC=F", 0.5, 1800.0)]:
            positions_repo.add(_make_position(ticker, quantity=qty, price=price))

        prices = [
            PriceRecord(symbol="AAPL", price_eur=200.0, currency_original="USD",
                        price_original=217.0, exchange_rate=0.922,
                        fetched_at=datetime.now(timezone.utc)),
            PriceRecord(symbol="MSFT", price_eur=350.0, currency_original="USD",
                        price_original=380.0, exchange_rate=0.922,
                        fetched_at=datetime.now(timezone.utc)),
            PriceRecord(symbol="GC=F", price_eur=55000.0, currency_original="EUR",
                        price_original=55000.0, exchange_rate=1.0,
                        fetched_at=datetime.now(timezone.utc)),
        ]
        mock_fetcher.fetch_current_prices.return_value = (prices, [])

        agent = MarketDataAgent(
            positions_repo=positions_repo, market_repo=market_repo,
            fetcher=mock_fetcher, db_path=":memory:", encryption_key="test",
        )
        agent.fetch_all_now()

        total = agent.get_total_value_eur()
        expected = 10 * 200 + 5 * 350 + 0.5 * 55000
        assert abs(total - expected) < 0.01


# ------------------------------------------------------------------
# E2E: Portfolio Agent Chat → Storage
# ------------------------------------------------------------------

class TestPortfolioChatToStorage:
    @pytest.mark.asyncio
    async def test_chat_add_entry_stored_in_db(self, positions_repo, mock_llm):
        from core.llm.local import OllamaResponse, ToolCall
        mock_llm.chat_with_tools = AsyncMock(side_effect=[
            OllamaResponse(
                content="",
                tool_calls=[ToolCall(
                    name="add_portfolio_entry",
                    arguments={
                        "ticker": "AAPL",
                        "name": "Apple Inc.",
                        "quantity": 10,
                        "unit": "Stück",
                        "purchase_price": 185.0,
                        "purchase_date": "2024-06-01",
                        "asset_class": "Aktie",
                    },
                )],
            ),
            OllamaResponse(content="10 Apple-Aktien wurden hinzugefügt.", tool_calls=[]),
        ])

        agent = PortfolioAgent(positions_repo=positions_repo, llm=mock_llm)
        response = await agent.chat("Ich habe 10 Apple-Aktien für 185€ gekauft")

        assert "Apple" in response or "hinzugefügt" in response
        entries = positions_repo.get_portfolio()
        assert len(entries) == 1
        assert entries[0].ticker == "AAPL"
        assert entries[0].quantity == 10
        assert entries[0].purchase_price == 185.0

    @pytest.mark.asyncio
    async def test_agent_add_to_watchlist_direct_api(self, positions_repo, mock_llm):
        agent = PortfolioAgent(positions_repo=positions_repo, llm=mock_llm)
        entry = agent.add_to_watchlist(
            ticker="TSLA",
            name="Tesla",
            asset_class="Aktie",
            notes="Beobachten",
        )

        assert entry.id is not None
        stored = positions_repo.get_by_ticker("TSLA")
        assert len(stored) == 1
        assert stored[0].recommendation_source == "agent"
        assert stored[0].in_portfolio is False


# ------------------------------------------------------------------
# E2E: Market Data price persistence
# ------------------------------------------------------------------

class TestMarketDataPersistence:
    def test_fetched_prices_persist_across_repo_instances(self, conn, enc, mock_fetcher):
        repo1 = MarketDataRepository(conn)
        repo2 = MarketDataRepository(conn)

        price = PriceRecord(
            symbol="GOLD", price_eur=1800.0, currency_original="USD",
            price_original=1952.0, exchange_rate=0.922,
            fetched_at=datetime.now(timezone.utc),
        )
        repo1.upsert_price(price)

        result = repo2.get_price("GOLD")
        assert result is not None
        assert result.price_eur == 1800.0

    def test_failed_symbols_not_stored(self, positions_repo, market_repo):
        positions_repo.add(_make_position("INVALID", quantity=1, price=100.0))

        fetcher = MagicMock(spec=MarketDataFetcher)
        fetcher.fetch_current_prices.return_value = ([], ["INVALID"])
        fetcher.fetch_historical.return_value = []

        agent = MarketDataAgent(
            positions_repo=positions_repo, market_repo=market_repo,
            fetcher=fetcher, db_path=":memory:", encryption_key="test",
        )
        result = agent.fetch_all_now()

        assert result.fetched == 0
        assert "INVALID" in result.failed
        assert market_repo.get_price("INVALID") is None
