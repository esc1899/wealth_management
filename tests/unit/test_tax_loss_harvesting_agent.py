"""Tests for TaxLossHarvestingAgent — result structure, metrics, and LLM interaction."""

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

from agents.market_data_agent import PortfolioValuation
from agents.tax_loss_harvesting_agent import (
    TaxLossHarvestingAgent,
    TaxLossHarvestingResult,
    _ABGELTUNGSTEUER,
    _build_context,
)
from core.storage.models import Position


def make_valuation(**kwargs) -> PortfolioValuation:
    defaults = dict(
        symbol="TST",
        name="Test AG",
        asset_class="Aktie",
        investment_type="Wertpapiere",
        quantity=10.0,
        unit="shares",
        purchase_price_eur=100.0,
        current_price_eur=80.0,
        current_value_eur=800.0,
        cost_basis_eur=1000.0,
        pnl_eur=-200.0,
        pnl_pct=-20.0,
        fetched_at=datetime.now(),
        in_portfolio=True,
        analysis_excluded=False,
    )
    defaults.update(kwargs)
    return PortfolioValuation(**defaults)


def make_position(**kwargs) -> Position:
    defaults = dict(
        id=99,
        asset_class="Aktie",
        investment_type="Wertpapiere",
        name="Watchlist Corp",
        ticker="WLC",
        unit="shares",
        added_date=date.today(),
        in_portfolio=False,
        in_watchlist=True,
    )
    defaults.update(kwargs)
    return Position(**defaults)


def make_agent(response: str = "## Analyse\nTest Report") -> TaxLossHarvestingAgent:
    mock_llm = AsyncMock()
    mock_llm.model = "test-model"
    mock_llm.chat = AsyncMock(return_value=response)
    return TaxLossHarvestingAgent(llm=mock_llm)


class TestTaxLossHarvestingAgent:

    @pytest.mark.asyncio
    async def test_analyze_returns_result(self):
        """analyze() returns a TaxLossHarvestingResult with correct shape."""
        agent = make_agent("## Report\nDetails here")
        loss = [make_valuation(pnl_eur=-1500.0)]
        result = await agent.analyze(
            loss_positions=loss,
            watchlist_positions=[],
            verdicts={},
            wash_sale_tickers=[],
            language="de",
        )

        assert isinstance(result, TaxLossHarvestingResult)
        assert result.candidate_count == 1
        assert result.total_loss_eur == pytest.approx(1500.0)
        assert "Report" in result.report_markdown

    @pytest.mark.asyncio
    async def test_tax_benefit_calculation(self):
        """total_tax_benefit_eur = total_loss × 0.26375."""
        agent = make_agent()
        total_loss = 2000.0
        loss = [make_valuation(pnl_eur=-total_loss)]
        result = await agent.analyze(
            loss_positions=loss,
            watchlist_positions=[],
            verdicts={},
            wash_sale_tickers=[],
        )

        expected = total_loss * _ABGELTUNGSTEUER
        assert result.total_tax_benefit_eur == pytest.approx(expected, rel=1e-6)

    @pytest.mark.asyncio
    async def test_wash_sale_tickers_passed_through(self):
        """wash_sale_tickers are included verbatim in the result."""
        agent = make_agent()
        wash = ["AAPL", "MSFT"]
        result = await agent.analyze(
            loss_positions=[make_valuation(pnl_eur=-1200.0)],
            watchlist_positions=[],
            verdicts={},
            wash_sale_tickers=wash,
        )

        assert result.wash_sale_tickers == wash

    @pytest.mark.asyncio
    async def test_empty_loss_positions_returns_early(self):
        """Empty loss list returns zero-result without calling the LLM."""
        mock_llm = AsyncMock()
        mock_llm.model = "test-model"
        mock_llm.chat = AsyncMock()
        agent = TaxLossHarvestingAgent(llm=mock_llm)

        result = await agent.analyze(
            loss_positions=[],
            watchlist_positions=[],
            verdicts={},
            wash_sale_tickers=[],
        )

        assert result.candidate_count == 0
        assert result.total_loss_eur == 0.0
        assert result.total_tax_benefit_eur == 0.0
        mock_llm.chat.assert_not_called()


class TestBuildContext:

    def test_context_contains_loss_position(self):
        v = make_valuation(symbol="TST", name="Test AG", pnl_eur=-1500.0)
        ctx = _build_context([v], [], {}, [])

        assert "Test AG" in ctx
        assert "TST" in ctx
        assert "1,500" in ctx or "1500" in ctx

    def test_context_flags_wash_sale(self):
        v = make_valuation(symbol="TST", pnl_eur=-1500.0)
        ctx = _build_context([v], [], {}, wash_sale_tickers=["TST"])

        assert "WASH-SALE" in ctx

    def test_context_includes_watchlist_verdicts(self):
        p = make_position(id=5, ticker="WLC", name="Watchlist Corp")

        mock_verdict = MagicMock()
        mock_verdict.verdict = "intact"
        verdicts = {"storychecker": {5: mock_verdict}}

        ctx = _build_context(
            [make_valuation(pnl_eur=-1200.0)],
            [p],
            verdicts,
            [],
        )
        assert "WLC" in ctx
        assert "intact" in ctx
