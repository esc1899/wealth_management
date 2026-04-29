"""
E2E Workflow Tests — real SQLite in-memory, mocked LLM/network.

Tests complete user journeys organised by feature domain:
- Asset class workflows (Aktie, Edelmetall, Fonds)
- Watchlist lifecycle (add → delete → clear)
- Watchlist → Portfolio promotion
- Strategy workflows (YAML, custom)
- Research session lifecycle
- Market data with portfolio + watchlist positions

No mocking of storage. LLM and yfinance are mocked.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.market_data_agent import MarketDataAgent
from agents.portfolio_agent import PortfolioAgent
from agents.research_agent import ResearchAgent
from core.encryption import EncryptionService
from core.llm.local import OllamaResponse, ToolCall
from core.storage.base import init_db
from core.storage.market_data import MarketDataRepository
from core.storage.models import Position, PriceRecord
from core.storage.positions import PositionsRepository
from core.storage.research import ResearchRepository
from core.strategy_config import CUSTOM_STRATEGY_NAME, StrategyConfig, StrategyRegistry


# ------------------------------------------------------------------
# Shared fixtures
# ------------------------------------------------------------------

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    init_db(c)
    return c


@pytest.fixture
def enc():
    return EncryptionService("test_password_32bytes_long!!!!!", b"0123456789abcdef")


@pytest.fixture
def positions(conn, enc):
    return PositionsRepository(conn, enc)


@pytest.fixture
def research(conn):
    return ResearchRepository(conn)


@pytest.fixture
def market(conn):
    return MarketDataRepository(conn)


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.model = "test-model"
    return llm


@pytest.fixture
def mock_fetcher():
    f = MagicMock()
    f.fetch_historical.return_value = []
    return f


@pytest.fixture
def portfolio_agent(positions, mock_llm):
    return PortfolioAgent(positions_repo=positions, llm=mock_llm)


@pytest.fixture
def market_agent(positions, market, mock_fetcher):
    return MarketDataAgent(
        positions_repo=positions, market_repo=market, fetcher=mock_fetcher,
        db_path=":memory:", encryption_key="test",
    )


@pytest.fixture
def strategy_registry():
    return StrategyRegistry({
        "Value Investing": StrategyConfig(
            name="Value Investing",
            description="Graham-style value analysis",
            system_prompt="Analysiere nach Value-Investing-Prinzipien: KGV, KBV, Burggraben.",
        ),
        "Dividendenstrategie": StrategyConfig(
            name="Dividendenstrategie",
            description="High dividend yield focus",
            system_prompt="Analysiere Dividendenrendite, Ausschüttungsquote und Stabilität.",
        ),
    })


@pytest.fixture
def research_agent(positions, research, mock_llm, strategy_registry):
    from unittest.mock import AsyncMock
    from core.llm.claude import ClaudeResponse
    mock_llm.chat_with_tools = AsyncMock(return_value=ClaudeResponse(
        content="Analyse abgeschlossen.",
        tool_calls=[],
        stop_reason="end_turn",
    ))
    return ResearchAgent(
        positions_repo=positions,
        research_repo=research,
        llm=mock_llm,
        strategy_registry=strategy_registry,
    )


# ------------------------------------------------------------------
# Asset class workflows
# ------------------------------------------------------------------

class TestAssetClassWorkflows:
    """Verify that different asset classes are stored and retrieved correctly."""

    def test_stock_added_with_correct_fields(self, positions):
        pos = Position(
            ticker="SAP.DE", name="SAP SE",
            asset_class="Aktie", investment_type="Wertpapiere",
            quantity=5, unit="Stück",
            purchase_price=185.0, purchase_date=date(2024, 3, 1),
            added_date=date(2024, 3, 1), in_portfolio=True,
        )
        saved = positions.add(pos)
        fetched = positions.get(saved.id)

        assert fetched.asset_class == "Aktie"
        assert fetched.investment_type == "Wertpapiere"
        assert fetched.ticker == "SAP.DE"
        assert fetched.unit == "Stück"
        assert fetched.quantity == 5
        assert fetched.in_portfolio is True

    def test_gold_coin_stored_as_edelmetall(self, positions):
        pos = Position(
            ticker="GC=F", name="Krügerrand",
            asset_class="Edelmetall", investment_type="Edelmetalle",
            quantity=2, unit="Troy Oz",
            purchase_price=1850.0, purchase_date=date(2024, 1, 10),
            added_date=date(2024, 1, 10), in_portfolio=True,
        )
        saved = positions.add(pos)
        fetched = positions.get(saved.id)

        assert fetched.asset_class == "Edelmetall"
        assert fetched.unit == "Troy Oz"
        assert fetched.ticker == "GC=F"
        assert fetched.quantity == 2

    def test_fonds_without_ticker(self, positions):
        pos = Position(
            ticker=None, name="Deka-ImmobilienEuropa",
            asset_class="Immobilienfonds", investment_type="Immobilien",
            quantity=10, unit="Stück",
            purchase_price=50.0, purchase_date=date(2024, 2, 1),
            added_date=date(2024, 2, 1), in_portfolio=True,
        )
        saved = positions.add(pos)
        tickers = positions.get_tickers_for_price_fetch()

        assert saved.ticker is None
        assert "None" not in tickers
        # other tickers present but not this one
        assert all(t is not None for t in tickers)

    def test_mixed_asset_classes_separated(self, positions):
        positions.add(Position(
            ticker="AAPL", name="Apple", asset_class="Aktie",
            investment_type="Wertpapiere", quantity=10, unit="Stück",
            added_date=date.today(), in_portfolio=True,
            purchase_date=date.today(),
        ))
        positions.add(Position(
            ticker="GC=F", name="Gold", asset_class="Edelmetall",
            investment_type="Edelmetalle", quantity=1, unit="Troy Oz",
            added_date=date.today(), in_portfolio=True,
            purchase_date=date.today(),
        ))
        portfolio = positions.get_portfolio()
        classes = {p.asset_class for p in portfolio}
        assert "Aktie" in classes
        assert "Edelmetall" in classes

    def test_strategy_stored_on_position(self, positions):
        pos = Position(
            ticker="BMW.DE", name="BMW AG",
            asset_class="Aktie", investment_type="Wertpapiere",
            unit="Stück", added_date=date.today(), in_portfolio=False,
            recommendation_source="research_agent",
            strategy="Value Investing",
        )
        saved = positions.add(pos)
        fetched = positions.get(saved.id)

        assert fetched.strategy == "Value Investing"
        assert fetched.recommendation_source == "research_agent"


# ------------------------------------------------------------------
# Watchlist lifecycle
# ------------------------------------------------------------------

class TestWatchlistLifecycle:
    """Complete add → verify → delete → verify workflows."""

    def test_add_to_watchlist_not_in_portfolio(self, positions):
        pos = Position(
            ticker="TSLA", name="Tesla", asset_class="Aktie",
            investment_type="Wertpapiere", unit="Stück",
            added_date=date.today(), in_portfolio=False, in_watchlist=True,
        )
        saved = positions.add(pos)

        assert saved.in_portfolio is False
        assert len(positions.get_watchlist()) == 1
        assert len(positions.get_portfolio()) == 0

    def test_delete_removes_from_watchlist(self, positions):
        pos = Position(
            ticker="TSLA", name="Tesla", asset_class="Aktie",
            investment_type="Wertpapiere", unit="Stück",
            added_date=date.today(), in_portfolio=False, in_watchlist=True,
        )
        saved = positions.add(pos)
        positions.delete(saved.id)

        assert positions.get_watchlist() == []

    def test_clear_watchlist_removes_all(self, portfolio_agent, positions):
        for ticker in ["AAPL", "MSFT", "SAP.DE"]:
            positions.add(Position(
                ticker=ticker, name=ticker, asset_class="Aktie",
                investment_type="Wertpapiere", unit="Stück",
                added_date=date.today(), in_portfolio=False, in_watchlist=True,
            ))
        assert len(positions.get_watchlist()) == 3

        result = portfolio_agent._tool_clear_watchlist()

        assert result["deleted"] == 3
        assert positions.get_watchlist() == []

    def test_clear_watchlist_leaves_portfolio_intact(self, portfolio_agent, positions):
        positions.add(Position(
            ticker="AAPL", name="Apple", asset_class="Aktie",
            investment_type="Wertpapiere", quantity=10, unit="Stück",
            purchase_date=date.today(), added_date=date.today(), in_portfolio=True,
        ))
        positions.add(Position(
            ticker="MSFT", name="Microsoft", asset_class="Aktie",
            investment_type="Wertpapiere", unit="Stück",
            added_date=date.today(), in_portfolio=False, in_watchlist=True,
        ))

        portfolio_agent._tool_clear_watchlist()

        assert len(positions.get_portfolio()) == 1
        assert positions.get_portfolio()[0].ticker == "AAPL"
        assert positions.get_watchlist() == []

    def test_watchlist_to_portfolio_promotion(self, positions):
        wl = positions.add(Position(
            ticker="NVDA", name="Nvidia", asset_class="Aktie",
            investment_type="Wertpapiere", unit="Stück",
            added_date=date.today(), in_portfolio=False, in_watchlist=True,
        ))
        assert len(positions.get_portfolio()) == 0

        promoted = positions.promote_to_portfolio(
            wl.id, quantity=3, purchase_price=800.0, purchase_date=date.today()
        )

        assert promoted.in_portfolio is True
        assert promoted.in_watchlist is True   # stays on watchlist after promotion (can be in both)
        assert promoted.quantity == 3
        assert promoted.purchase_price == 800.0
        assert len(positions.get_portfolio()) == 1
        assert len(positions.get_watchlist()) == 1  # still on watchlist


# ------------------------------------------------------------------
# Strategy workflows
# ------------------------------------------------------------------

class TestStrategyWorkflows:
    """YAML strategies and custom strategies used in research sessions."""

    def test_named_strategy_prompt_stored_in_session(self, research_agent, research):
        session = research_agent.start_session("SAP.DE", "Value Investing")
        fetched = research.get_session(session.id)

        assert fetched.strategy_name == "Value Investing"
        assert "KGV" in fetched.strategy_prompt
        assert "Burggraben" in fetched.strategy_prompt

    def test_custom_strategy_prompt_stored_verbatim(self, research_agent, research):
        custom = "Fokus auf ESG-Kennzahlen und Nachhaltigkeitsbewertung."
        session = research_agent.start_session(
            "AAPL", CUSTOM_STRATEGY_NAME, custom_prompt=custom
        )
        fetched = research.get_session(session.id)

        assert fetched.strategy_name == CUSTOM_STRATEGY_NAME
        assert fetched.strategy_prompt == custom

    def test_strategy_prompt_survives_reload(self, research_agent, research):
        """Session restored from DB has the original strategy prompt intact."""
        session = research_agent.start_session("MSFT", "Dividendenstrategie")
        original_prompt = session.strategy_prompt

        reloaded = research.get_session(session.id)
        assert reloaded.strategy_prompt == original_prompt

    def test_different_strategies_stored_independently(self, research_agent, research):
        s1 = research_agent.start_session("AAPL", "Value Investing")
        s2 = research_agent.start_session("BMW.DE", "Dividendenstrategie")

        assert research.get_session(s1.id).strategy_name == "Value Investing"
        assert research.get_session(s2.id).strategy_name == "Dividendenstrategie"
        assert research.get_session(s1.id).strategy_prompt != research.get_session(s2.id).strategy_prompt

    def test_unknown_strategy_raises(self, research_agent):
        with pytest.raises(ValueError, match="Unknown strategy"):
            research_agent.start_session("AAPL", "Nonexistent Strategy")

    def test_research_agent_adds_to_watchlist_with_strategy(self, research_agent, positions):
        session = research_agent.start_session("AAPL", "Value Investing")
        proposal = {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "asset_class": "Aktie",
            "notes": "Attraktiv",
            "story": "",
        }
        research_agent.add_from_proposal(session.id, proposal)

        wl = positions.get_watchlist()
        assert len(wl) == 1
        assert wl[0].strategy == "Value Investing"
        assert wl[0].recommendation_source == "research_agent"
        assert wl[0].in_portfolio is False


# ------------------------------------------------------------------
# Research session lifecycle
# ------------------------------------------------------------------

class TestResearchSessionLifecycle:
    """Full create → messages → list → delete cascade."""

    def test_session_creation_stores_all_fields(self, research):
        s = research.create_session(
            ticker="bmw.de", strategy_name="Value Investing",
            strategy_prompt="KGV < 15", company_name="BMW AG",
        )
        fetched = research.get_session(s.id)

        assert fetched.ticker == "BMW.DE"          # uppercased
        assert fetched.company_name == "BMW AG"
        assert fetched.strategy_prompt == "KGV < 15"
        assert fetched.summary is None

    def test_messages_stored_in_order(self, research):
        s = research.create_session("AAPL", "Value Investing", "prompt")
        research.add_message(s.id, "user", "Analysiere Apple.")
        research.add_message(s.id, "assistant", "Apple ist unterbewertet.")
        research.add_message(s.id, "user", "Kaufen?")

        msgs = research.get_messages(s.id)
        assert len(msgs) == 3
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"
        assert msgs[2].content == "Kaufen?"

    def test_messages_isolated_between_sessions(self, research):
        s1 = research.create_session("AAPL", "Value Investing", "p1")
        s2 = research.create_session("MSFT", "Dividendenstrategie", "p2")
        research.add_message(s1.id, "user", "AAPL Frage")
        research.add_message(s2.id, "user", "MSFT Frage")

        assert len(research.get_messages(s1.id)) == 1
        assert research.get_messages(s1.id)[0].content == "AAPL Frage"

    def test_delete_cascades_to_messages(self, research):
        s = research.create_session("AAPL", "Value Investing", "prompt")
        research.add_message(s.id, "user", "Frage")
        research.add_message(s.id, "assistant", "Antwort")

        research.delete_session(s.id)

        assert research.get_session(s.id) is None
        assert research.get_messages(s.id) == []

    def test_list_sessions_newest_first(self, research):
        s1 = research.create_session("AAPL", "Value Investing", "p1")
        s2 = research.create_session("MSFT", "Dividendenstrategie", "p2")
        s3 = research.create_session("SAP.DE", "Value Investing", "p3")

        sessions = research.list_sessions()
        assert sessions[0].id == s3.id
        assert sessions[-1].id == s1.id

    def test_summary_updated(self, research):
        s = research.create_session("AAPL", "Value Investing", "prompt")
        research.update_summary(s.id, "Strong buy — 30% unterbewertet.")

        fetched = research.get_session(s.id)
        assert fetched.summary == "Strong buy — 30% unterbewertet."


# ------------------------------------------------------------------
# Market data: portfolio + watchlist
# ------------------------------------------------------------------

class TestMarketDataAllPositions:
    """Prices shown for both portfolio and watchlist positions."""

    def _add_portfolio(self, positions: PositionsRepository, ticker: str) -> Position:
        return positions.add(Position(
            ticker=ticker, name=ticker, asset_class="Aktie",
            investment_type="Wertpapiere", quantity=10, unit="Stück",
            purchase_price=100.0, purchase_date=date.today(),
            added_date=date.today(), in_portfolio=True,
        ))

    def _add_watchlist(self, positions: PositionsRepository, ticker: str) -> Position:
        return positions.add(Position(
            ticker=ticker, name=ticker, asset_class="Aktie",
            investment_type="Wertpapiere", unit="Stück",
            added_date=date.today(), in_portfolio=False, in_watchlist=True,
        ))

    def _price(self, symbol: str, eur: float) -> PriceRecord:
        return PriceRecord(
            symbol=symbol, price_eur=eur, currency_original="EUR",
            price_original=eur, exchange_rate=1.0,
            fetched_at=datetime.now(timezone.utc),
        )

    def test_default_excludes_watchlist(self, positions, market_agent, market):
        self._add_portfolio(positions, "AAPL")
        self._add_watchlist(positions, "MSFT")
        market.upsert_price(self._price("AAPL", 200.0))
        market.upsert_price(self._price("MSFT", 350.0))

        vals = market_agent.get_portfolio_valuation()
        assert len(vals) == 1
        assert vals[0].symbol == "AAPL"

    def test_include_watchlist_shows_both(self, positions, market_agent, market):
        self._add_portfolio(positions, "AAPL")
        self._add_watchlist(positions, "MSFT")
        market.upsert_price(self._price("AAPL", 200.0))
        market.upsert_price(self._price("MSFT", 350.0))

        vals = market_agent.get_portfolio_valuation(include_watchlist=True)
        assert len(vals) == 2
        symbols = {v.symbol for v in vals}
        assert symbols == {"AAPL", "MSFT"}

    def test_in_portfolio_flag_correct(self, positions, market_agent, market):
        self._add_portfolio(positions, "AAPL")
        self._add_watchlist(positions, "MSFT")
        market.upsert_price(self._price("AAPL", 200.0))
        market.upsert_price(self._price("MSFT", 350.0))

        vals = market_agent.get_portfolio_valuation(include_watchlist=True)
        by_symbol = {v.symbol: v for v in vals}
        assert by_symbol["AAPL"].in_portfolio is True
        assert by_symbol["MSFT"].in_portfolio is False

    def test_watchlist_position_without_price_still_included(self, positions, market_agent):
        self._add_watchlist(positions, "NVDA")

        vals = market_agent.get_portfolio_valuation(include_watchlist=True)
        assert len(vals) == 1
        assert vals[0].current_price_eur is None

    def test_edelmetall_in_portfolio_valued_correctly(self, positions, market_agent, market):
        positions.add(Position(
            ticker="GC=F", name="Krügerrand",
            asset_class="Edelmetall", investment_type="Edelmetalle",
            quantity=2, unit="Troy Oz",
            purchase_price=1800.0, purchase_date=date.today(),
            added_date=date.today(), in_portfolio=True,
        ))
        market.upsert_price(self._price("GC=F", 2000.0))

        vals = market_agent.get_portfolio_valuation()
        assert len(vals) == 1
        assert vals[0].current_value_eur == 4000.0
        assert vals[0].pnl_eur == 400.0


# ------------------------------------------------------------------
# Portfolio agent tool execution with real DB
# ------------------------------------------------------------------

class TestPortfolioAgentWithRealDB:
    """Tool execution tests — mock LLM returns tool call, real DB stores it."""

    @pytest.mark.asyncio
    async def test_add_stock_via_chat(self, portfolio_agent, positions, mock_llm):
        mock_llm.chat_with_tools = AsyncMock(side_effect=[
            OllamaResponse(content="", tool_calls=[ToolCall(
                name="add_portfolio_entry",
                arguments={
                    "ticker": "SAP.DE", "name": "SAP SE", "asset_class": "Aktie",
                    "quantity": 5, "unit": "Stück",
                    "purchase_price": 185.0, "purchase_date": "2024-06-01",
                },
            )]),
            OllamaResponse(content="5 SAP-Aktien hinzugefügt.", tool_calls=[]),
        ])

        await portfolio_agent.chat("Ich habe 5 SAP-Aktien für 185€ gekauft.")

        portfolio = positions.get_portfolio()
        assert len(portfolio) == 1
        assert portfolio[0].ticker == "SAP.DE"
        assert portfolio[0].quantity == 5
        assert portfolio[0].asset_class == "Aktie"

    @pytest.mark.asyncio
    async def test_add_gold_coin_via_chat(self, portfolio_agent, positions, mock_llm):
        mock_llm.chat_with_tools = AsyncMock(side_effect=[
            OllamaResponse(content="", tool_calls=[ToolCall(
                name="add_portfolio_entry",
                arguments={
                    "ticker": "GC=F", "name": "Krügerrand",
                    "asset_class": "Edelmetall", "quantity": 1,
                    "unit": "Troy Oz", "purchase_date": "2024-01-10",
                    "purchase_price": 1850.0,
                },
            )]),
            OllamaResponse(content="1 Krügerrand hinzugefügt.", tool_calls=[]),
        ])

        await portfolio_agent.chat("Ich habe einen Krügerrand für 1850€ gekauft.")

        portfolio = positions.get_portfolio()
        assert portfolio[0].asset_class == "Edelmetall"
        assert portfolio[0].unit == "Troy Oz"
        assert portfolio[0].ticker == "GC=F"

    @pytest.mark.asyncio
    async def test_clear_watchlist_via_chat(self, portfolio_agent, positions, mock_llm):
        for ticker in ["AAPL", "MSFT"]:
            positions.add(Position(
                ticker=ticker, name=ticker, asset_class="Aktie",
                investment_type="Wertpapiere", unit="Stück",
                added_date=date.today(), in_portfolio=False, in_watchlist=True,
            ))
        mock_llm.chat_with_tools = AsyncMock(side_effect=[
            OllamaResponse(content="", tool_calls=[ToolCall(
                name="clear_watchlist", arguments={},
            )]),
            OllamaResponse(content="Watchlist geleert.", tool_calls=[]),
        ])

        await portfolio_agent.chat("Lösche alles aus der Watchlist.")

        assert positions.get_watchlist() == []

    @pytest.mark.asyncio
    async def test_delete_single_watchlist_entry_via_chat(self, portfolio_agent, positions, mock_llm):
        saved = positions.add(Position(
            ticker="TSLA", name="Tesla", asset_class="Aktie",
            investment_type="Wertpapiere", unit="Stück",
            added_date=date.today(), in_portfolio=False, in_watchlist=True,
        ))
        mock_llm.chat_with_tools = AsyncMock(side_effect=[
            OllamaResponse(content="", tool_calls=[ToolCall(
                name="remove_from_watchlist", arguments={"entry_id": saved.id},
            )]),
            OllamaResponse(content="Tesla entfernt.", tool_calls=[]),
        ])

        await portfolio_agent.chat(f"Lösche Tesla (ID {saved.id}) aus der Watchlist.")

        assert positions.get_watchlist() == []
