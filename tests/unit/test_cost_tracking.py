"""
Unit tests for cost tracking:
- UsageRepository: record(skill), reset(), avg_cost_per_call(), monthly_estimate()
- AppConfigRepository: get_model_prices / set_model_prices
- LLMProvider: skill_context attribute, 3-arg on_usage callback
- compute_cost helper
"""

from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.storage.app_config import AppConfigRepository
from core.storage.base import init_db, migrate_db
from core.storage.usage import UsageRepository, compute_cost


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    init_db(c)
    migrate_db(c)
    return c


@pytest.fixture
def usage_repo(conn):
    return UsageRepository(conn)


@pytest.fixture
def config_repo(conn):
    return AppConfigRepository(conn)


_PRICES = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-6":         {"input": 3.00, "output": 15.00},
}


# ---------------------------------------------------------------------------
# compute_cost
# ---------------------------------------------------------------------------

def test_compute_cost_haiku():
    cost = compute_cost(1_000_000, 0, "claude-haiku-4-5-20251001", _PRICES)
    assert cost == pytest.approx(0.80)


def test_compute_cost_sonnet_output():
    cost = compute_cost(0, 1_000_000, "claude-sonnet-4-6", _PRICES)
    assert cost == pytest.approx(15.00)


def test_compute_cost_unknown_model():
    cost = compute_cost(1_000_000, 1_000_000, "unknown-model", _PRICES)
    assert cost == 0.0


def test_compute_cost_combined():
    # 500k input + 500k output for haiku
    cost = compute_cost(500_000, 500_000, "claude-haiku-4-5-20251001", _PRICES)
    assert cost == pytest.approx(0.80 * 0.5 + 4.00 * 0.5)


# ---------------------------------------------------------------------------
# UsageRepository.record with skill
# ---------------------------------------------------------------------------

def test_record_with_skill(usage_repo):
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 100, 200, skill="Standard News")
    rows = usage_repo.total_all_time()
    assert len(rows) == 1
    assert rows[0]["skill"] == "Standard News"
    assert rows[0]["input_tokens"] == 100
    assert rows[0]["output_tokens"] == 200


def test_record_without_skill(usage_repo):
    usage_repo.record("portfolio_chat", "qwen3:8b", 50, 80)
    rows = usage_repo.total_all_time()
    assert len(rows) == 1
    assert rows[0]["skill"] is None


def test_record_multiple_skills(usage_repo):
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 100, 200, skill="Skill A")
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 150, 250, skill="Skill B")
    rows = usage_repo.total_all_time()
    assert len(rows) == 2
    skills = {r["skill"] for r in rows}
    assert skills == {"Skill A", "Skill B"}


# ---------------------------------------------------------------------------
# UsageRepository.reset
# ---------------------------------------------------------------------------

def test_reset_all(usage_repo):
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 100, 200, skill="S1")
    usage_repo.record("structural_scan", "claude-sonnet-4-6", 300, 400, skill="S2")
    assert len(usage_repo.total_all_time()) == 2
    usage_repo.reset()  # global reset
    assert usage_repo.total_all_time() == []


def test_reset_specific_agent(usage_repo):
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 100, 200, skill="S1")
    usage_repo.record("structural_scan", "claude-sonnet-4-6", 300, 400, skill="S2")
    usage_repo.reset(agent="news_digest", model="claude-haiku-4-5-20251001")
    rows = usage_repo.total_all_time()
    assert len(rows) == 1
    assert rows[0]["agent"] == "structural_scan"


def test_reset_specific_skill(usage_repo):
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 100, 200, skill="Skill A")
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 150, 250, skill="Skill B")
    usage_repo.reset(agent="news_digest", model="claude-haiku-4-5-20251001", skill="Skill A")
    rows = usage_repo.total_all_time()
    assert len(rows) == 1
    assert rows[0]["skill"] == "Skill B"


def test_reset_does_not_affect_future_records(usage_repo):
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 100, 200)
    usage_repo.reset()
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 50, 60)
    rows = usage_repo.total_all_time()
    assert len(rows) == 1
    assert rows[0]["input_tokens"] == 50


# ---------------------------------------------------------------------------
# UsageRepository.avg_cost_per_call
# ---------------------------------------------------------------------------

def test_avg_cost_per_call_no_data(usage_repo):
    result = usage_repo.avg_cost_per_call("news_digest", "claude-haiku-4-5-20251001", None, _PRICES)
    assert result == 0.0


def test_avg_cost_per_call_single(usage_repo):
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 1_000_000, 0, skill=None)
    avg = usage_repo.avg_cost_per_call("news_digest", "claude-haiku-4-5-20251001", None, _PRICES)
    assert avg == pytest.approx(0.80)


def test_avg_cost_per_call_multiple(usage_repo):
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 1_000_000, 0, skill=None)
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 0, 1_000_000, skill=None)
    avg = usage_repo.avg_cost_per_call("news_digest", "claude-haiku-4-5-20251001", None, _PRICES)
    # avg input = 500k, avg output = 500k → cost = 0.4 + 2.0 = 2.4
    assert avg == pytest.approx(2.40)


def test_avg_cost_per_call_skill_filter(usage_repo):
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 1_000_000, 0, skill="Skill A")
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 2_000_000, 0, skill="Skill B")
    avg_a = usage_repo.avg_cost_per_call("news_digest", "claude-haiku-4-5-20251001", "Skill A", _PRICES)
    avg_b = usage_repo.avg_cost_per_call("news_digest", "claude-haiku-4-5-20251001", "Skill B", _PRICES)
    assert avg_a == pytest.approx(0.80)
    assert avg_b == pytest.approx(1.60)


def test_avg_cost_after_reset(usage_repo):
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 1_000_000, 0, skill=None)
    usage_repo.reset()
    avg = usage_repo.avg_cost_per_call("news_digest", "claude-haiku-4-5-20251001", None, _PRICES)
    assert avg == 0.0


# ---------------------------------------------------------------------------
# UsageRepository.monthly_estimate
# ---------------------------------------------------------------------------

def test_monthly_estimate_empty(usage_repo):
    result = usage_repo.monthly_estimate([], _PRICES)
    assert result == []


def test_monthly_estimate_no_usage_data(usage_repo):
    job = MagicMock()
    job.enabled = True
    job.agent_name = "news_digest"
    job.skill_name = "Standard"
    job.model = "claude-haiku-4-5-20251001"
    job.frequency = "daily"
    result = usage_repo.monthly_estimate([job], _PRICES)
    assert len(result) == 1
    assert result[0]["monthly_cost_eur"] == 0.0


def test_monthly_estimate_with_data(usage_repo):
    usage_repo.record("news_digest", "claude-haiku-4-5-20251001", 1_000_000, 0, skill="Standard")
    job = MagicMock()
    job.enabled = True
    job.agent_name = "news_digest"
    job.skill_name = "Standard"
    job.model = "claude-haiku-4-5-20251001"
    job.frequency = "daily"

    # Mock positions_repo with 20 positions (news-eligible)
    positions_repo = MagicMock()
    pos = MagicMock()
    pos.ticker = "TEST"
    pos.asset_class = "Aktie"
    positions_repo.get_portfolio.return_value = [pos] * 20

    result = usage_repo.monthly_estimate([job], _PRICES, positions_repo)
    assert len(result) == 1
    # Cost per position = $0.80 / 20 = $0.04
    # Monthly = 30 calls × 20 positions × $0.04 = $24.00
    assert result[0]["monthly_cost_eur"] == pytest.approx(24.00)


def test_monthly_estimate_disabled_job_skipped(usage_repo):
    job = MagicMock()
    job.enabled = False
    job.agent_name = "news_digest"
    job.skill_name = "Standard"
    job.model = "claude-haiku-4-5-20251001"
    job.frequency = "daily"
    result = usage_repo.monthly_estimate([job], _PRICES)
    assert result == []


# ---------------------------------------------------------------------------
# UsageRepository.benchmark_runs
# ---------------------------------------------------------------------------

def test_record_benchmark(usage_repo):
    usage_repo.record_benchmark(
        scenario_name="structural_scan/Standard",
        agent="structural_scan",
        model="claude-sonnet-4-6",
        skill_name="Standard",
        input_tokens=100,
        output_tokens=200,
        cost_eur=0.003,
        label="baseline",
    )
    runs = usage_repo.get_benchmark_runs()
    assert len(runs) == 1
    assert runs[0]["scenario_name"] == "structural_scan/Standard"
    assert runs[0]["label"] == "baseline"


def test_get_benchmark_scenarios(usage_repo):
    usage_repo.record_benchmark("sc1/A", "sc1", "model", "A", 10, 20, 0.001)
    usage_repo.record_benchmark("sc1/A", "sc1", "model", "A", 10, 20, 0.001)
    usage_repo.record_benchmark("sc2/B", "sc2", "model", "B", 10, 20, 0.001)
    scenarios = usage_repo.get_benchmark_scenarios()
    assert set(scenarios) == {"sc1/A", "sc2/B"}


# ---------------------------------------------------------------------------
# AppConfigRepository: model prices
# ---------------------------------------------------------------------------

def test_get_model_prices_seeds_defaults(config_repo):
    prices = config_repo.get_model_prices()
    assert "claude-haiku-4-5-20251001" in prices
    assert prices["claude-haiku-4-5-20251001"]["input"] == pytest.approx(0.80)
    assert prices["claude-haiku-4-5-20251001"]["output"] == pytest.approx(4.00)


def test_set_model_prices(config_repo):
    config_repo.set_model_prices({"my-model": {"input": 1.0, "output": 5.0}})
    prices = config_repo.get_model_prices()
    # Defaults are merged back in
    assert "claude-haiku-4-5-20251001" in prices
    assert "my-model" in prices
    assert prices["my-model"]["input"] == 1.0


def test_model_prices_override(config_repo):
    config_repo.set_model_prices({"claude-haiku-4-5-20251001": {"input": 9.99, "output": 9.99}})
    prices = config_repo.get_model_prices()
    # Stored value overrides default
    assert prices["claude-haiku-4-5-20251001"]["input"] == pytest.approx(9.99)


# ---------------------------------------------------------------------------
# LLMProvider: skill_context + 3-arg on_usage
# ---------------------------------------------------------------------------

def test_llm_provider_has_skill_context():
    from core.llm.claude import ClaudeProvider
    provider = ClaudeProvider(api_key="test", model="claude-haiku-4-5-20251001")
    assert provider.skill_context is None
    provider.skill_context = "My Skill"
    assert provider.skill_context == "My Skill"


def test_llm_provider_on_usage_receives_skill():
    from core.llm.claude import ClaudeProvider
    received = []
    provider = ClaudeProvider(api_key="test", model="claude-haiku-4-5-20251001")
    provider.on_usage = lambda i, o, skill=None: received.append((i, o, skill))
    provider.skill_context = "Test Skill"

    # Simulate on_usage being fired
    provider.on_usage(100, 200, provider.skill_context)
    assert received == [(100, 200, "Test Skill")]


def test_usage_repo_records_skill_from_callback(usage_repo):
    """Integration: on_usage lambda (as set up in state.py) passes skill to record()."""
    agent_name = "news_digest"
    model = "claude-haiku-4-5-20251001"

    on_usage = lambda i, o, skill=None: usage_repo.record(agent_name, model, i, o, skill=skill)
    on_usage(100, 200, "Standard News")

    rows = usage_repo.total_all_time()
    assert len(rows) == 1
    assert rows[0]["skill"] == "Standard News"
