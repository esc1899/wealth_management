"""Unit tests for PortfolioRobustnessAgent."""

from __future__ import annotations

import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.portfolio_robustness_agent import (
    PortfolioRobustnessAgent,
    VALID_VERDICTS,
    _extract_verdict,
    _extract_summary,
)
from core.storage.base import init_db, migrate_db
from core.storage.portfolio_robustness import PortfolioRobustnessRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    init_db(c)
    migrate_db(c)
    return c


@pytest.fixture
def pr_repo(conn):
    return PortfolioRobustnessRepository(conn)


def make_llm(response_text: str):
    llm = MagicMock()
    llm.model = "llama3:latest"
    llm.complete = AsyncMock(return_value=response_text)
    return llm


class TestValidVerdicts:
    def test_valid_verdict_set(self):
        assert VALID_VERDICTS == {"robust", "angreifbar", "fragil", "kritisch"}


class TestExtractVerdict:
    def test_extracts_robust_from_robustheit_line(self):
        text = "## Portfolio-Gegenanalyse\n**Robustheit:** 🟢 Robust\n> Gut diversifiziert."
        assert _extract_verdict(text) == "robust"

    def test_extracts_kritisch_from_symbol(self):
        text = "**Robustheit:** 🔴 Kritisch\n> Massive Konzentration."
        assert _extract_verdict(text) == "kritisch"

    def test_extracts_fragil_from_symbol(self):
        text = "**Robustheit:** 🟠 Fragil\n> Multiple concerns."
        assert _extract_verdict(text) == "fragil"

    def test_extracts_angreifbar_from_symbol(self):
        text = "**Robustheit:** 🟡 Angreifbar\n> Some risks."
        assert _extract_verdict(text) == "angreifbar"

    def test_fallback_to_text_match(self):
        text = "The portfolio is fragil due to concentration."
        assert _extract_verdict(text) == "fragil"

    def test_default_when_no_match(self):
        assert _extract_verdict("No verdict here.") == "angreifbar"


class TestExtractSummary:
    def test_extracts_blockquote_line(self):
        text = "**Robustheit:** 🟢 Robust\n> Das Portfolio ist gut diversifiziert."
        assert _extract_summary(text) == "Das Portfolio ist gut diversifiziert."

    def test_fallback_when_no_blockquote(self):
        result = _extract_summary("No blockquote here.")
        assert isinstance(result, str)
        assert len(result) > 0


class TestPortfolioRobustnessAgent:
    def test_analyze_returns_analysis_object(self):
        llm = make_llm(
            "## Portfolio-Gegenanalyse\n**Robustheit:** 🟡 Angreifbar\n> Tech-Konzentration zu hoch.\n\nDetails here."
        )
        agent = PortfolioRobustnessAgent(llm=llm)

        result = asyncio.run(agent.analyze("- Apple (AAPL)", "- Apple: intact", "de", 5))

        assert result.verdict == "angreifbar"
        assert result.summary == "Tech-Konzentration zu hoch."
        assert len(result.analysis_text) > 0
        assert result.position_count == 5

    def test_all_valid_verdicts_returned(self):
        for v, sym in [("robust", "🟢"), ("angreifbar", "🟡"), ("fragil", "🟠"), ("kritisch", "🔴")]:
            llm = make_llm(f"**Robustheit:** {sym} {v.capitalize()}\n> Test summary.")
            agent = PortfolioRobustnessAgent(llm=llm)
            result = asyncio.run(agent.analyze("snapshot", "verdicts", "de"))
            assert result.verdict == v

    def test_handles_llm_error_gracefully(self):
        llm = MagicMock()
        llm.model = "llama3:latest"
        llm.complete = AsyncMock(side_effect=Exception("Ollama unavailable"))
        agent = PortfolioRobustnessAgent(llm=llm)

        result = asyncio.run(agent.analyze("snapshot", "verdicts", "de"))

        assert result.verdict == "angreifbar"  # default fallback
        assert result.analysis_text == "(Analyse fehlgeschlagen)"

    def test_analysis_text_not_empty_on_success(self):
        llm = make_llm("**Robustheit:** 🟢 Robust\n> All good.\n\nLots of detail about the portfolio.")
        agent = PortfolioRobustnessAgent(llm=llm)

        result = asyncio.run(agent.analyze("portfolio", "verdicts", "de"))

        assert result.analysis_text != ""
        assert len(result.analysis_text) > 10

    def test_empty_portfolio_handled(self):
        llm = make_llm("**Robustheit:** 🟡 Angreifbar\n> Leeres Portfolio.\n")
        agent = PortfolioRobustnessAgent(llm=llm)

        result = asyncio.run(agent.analyze("", "", "de", 0))

        assert result.verdict in VALID_VERDICTS
        assert result.position_count == 0


class TestPortfolioRobustnessRepository:
    def test_save_and_retrieve_latest(self, pr_repo):
        pr_repo.save(
            verdict="fragil",
            summary="High concentration risk.",
            analysis_text="Full analysis text.",
            position_count=10,
        )

        latest = pr_repo.get_latest()
        assert latest is not None
        assert latest.verdict == "fragil"
        assert latest.summary == "High concentration risk."
        assert latest.position_count == 10

    def test_list_recent_returns_multiple(self, pr_repo):
        for v in ["robust", "angreifbar", "fragil"]:
            pr_repo.save(verdict=v, summary=f"Summary {v}", analysis_text="text")

        recent = pr_repo.list_recent(limit=5)
        assert len(recent) == 3

    def test_get_latest_returns_none_when_empty(self, pr_repo):
        assert pr_repo.get_latest() is None
