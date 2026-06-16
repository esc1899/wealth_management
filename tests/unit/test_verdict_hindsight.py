"""Unit tests for Verdict Hindsight — the deterministic price-outcome loop (FEAT-59).

Covers the pure aggregation (core.verdict_hindsight) with a dict-backed price function,
and the two read-only repository feeds against a real SQLite :memory: DB.
"""

import sqlite3
from datetime import date

import pytest

from core.storage.analyses import PositionAnalysesRepository
from core.storage.base import init_db, migrate_db
from core.verdict_hindsight import compute_hindsight


# --- Pure aggregation ------------------------------------------------------------

def _price_fn(prices: dict):
    """Build a (ticker, date) -> price lookup from a {(ticker, 'YYYY-MM-DD'): price} dict."""
    return lambda ticker, date_str: prices.get((ticker, date_str))


def _row(agent, verdict, created_at, ticker):
    return {"agent": agent, "verdict": verdict, "created_at": created_at, "ticker": ticker}


def test_forward_return_and_horizon_maturity():
    rows = [_row("consensus_gap", "wächst", "2026-01-01T09:00:00+00:00", "AAA")]
    prices = {
        ("AAA", "2026-01-01"): 100.0,
        ("AAA", "2026-01-31"): 110.0,  # +30d -> +10%
        ("AAA", "2026-04-01"): 130.0,  # +90d -> would be +30% but not matured yet
    }
    report = compute_hindsight(rows, _price_fn(prices), as_of=date(2026, 3, 1))

    cell_1m = report.by_agent["consensus_gap"][0].horizons["1M"]
    assert cell_1m.n == 1
    assert cell_1m.median_pct == pytest.approx(10.0)
    assert cell_1m.mean_pct == pytest.approx(10.0)
    # 3M target (2026-04-01) lies after as_of -> not matured, ignored.
    assert report.by_agent["consensus_gap"][0].horizons["3M"].n == 0
    assert report.evaluated_verdicts == 1


def test_median_and_mean_across_multiple_verdicts():
    rows = [
        _row("consensus_gap", "wächst", "2026-01-01", "AAA"),
        _row("consensus_gap", "wächst", "2026-01-01", "BBB"),
        _row("consensus_gap", "wächst", "2026-01-01", "CCC"),
    ]
    prices = {
        ("AAA", "2026-01-01"): 100.0, ("AAA", "2026-01-31"): 100.0,  # 0%
        ("BBB", "2026-01-01"): 100.0, ("BBB", "2026-01-31"): 110.0,  # +10%
        ("CCC", "2026-01-01"): 100.0, ("CCC", "2026-01-31"): 140.0,  # +40%
    }
    report = compute_hindsight(rows, _price_fn(prices), as_of=date(2026, 3, 1))
    cell = report.by_agent["consensus_gap"][0].horizons["1M"]
    assert cell.n == 3
    assert cell.median_pct == pytest.approx(10.0)            # robust to the +40% outlier
    assert cell.mean_pct == pytest.approx(50.0 / 3)          # pulled up by the outlier
    assert cell.best_pct == pytest.approx(40.0)
    assert cell.worst_pct == pytest.approx(0.0)


def test_missing_entry_price_is_excluded_not_evaluated():
    rows = [
        _row("consensus_gap", "stabil", "2026-01-01", "AAA"),  # no entry price
        _row("consensus_gap", "stabil", "2026-01-01", "BBB"),  # has price
    ]
    prices = {("BBB", "2026-01-01"): 100.0, ("BBB", "2026-01-31"): 105.0}
    report = compute_hindsight(rows, _price_fn(prices), as_of=date(2026, 3, 1))
    assert report.total_verdicts == 2
    assert report.evaluated_verdicts == 1
    assert report.excluded_no_price == 1
    assert report.by_agent["consensus_gap"][0].horizons["1M"].n == 1


def test_survivorship_gap_surfaced():
    rows = [_row("devils_advocate", "robust", "2026-01-01", "AAA")]
    prices = {("AAA", "2026-01-01"): 100.0, ("AAA", "2026-01-31"): 90.0}
    # 10 verdicts were emitted historically; only 1 position survives.
    report = compute_hindsight(
        rows, _price_fn(prices), as_of=date(2026, 3, 1), total_emitted=10
    )
    assert report.total_verdicts == 1
    assert report.excluded_survivorship == 9


def test_verdicts_are_display_ordered_green_to_red():
    # Supplied out of canonical order; output must follow VERDICT_ORDER.
    rows = [
        _row("consensus_gap", "eingeholt", "2026-01-01", "AAA"),
        _row("consensus_gap", "wächst", "2026-01-01", "BBB"),
        _row("consensus_gap", "stabil", "2026-01-01", "CCC"),
    ]
    prices = {(t, d): 100.0 for t in ("AAA", "BBB", "CCC") for d in ("2026-01-01", "2026-01-31")}
    report = compute_hindsight(rows, _price_fn(prices), as_of=date(2026, 3, 1))
    labels = [r.verdict for r in report.by_agent["consensus_gap"]]
    assert labels == ["wächst", "stabil", "eingeholt"]


def test_fundamental_analyzer_graded_and_unknown_excluded():
    rows = [
        _row("fundamental_analyzer", "unterbewertet", "2026-01-01", "AAA"),
        _row("fundamental_analyzer", "unbekannt", "2026-01-01", "BBB"),  # not gradeable
    ]
    prices = {
        ("AAA", "2026-01-01"): 100.0, ("AAA", "2026-01-31"): 112.0,
        ("BBB", "2026-01-01"): 100.0, ("BBB", "2026-01-31"): 100.0,
    }
    report = compute_hindsight(rows, _price_fn(prices), as_of=date(2026, 3, 1))
    fa = report.by_agent["fundamental_analyzer"]
    labels = [r.verdict for r in fa]
    assert labels == ["unterbewertet"]           # "unbekannt" not shown
    assert report.excluded_unknown == 1
    assert fa[0].horizons["1M"].median_pct == pytest.approx(12.0)
    # Disjoint counting identity holds.
    assert (
        report.evaluated_verdicts
        + report.excluded_no_price
        + report.excluded_unknown
        == report.total_verdicts
    )


def test_distinct_positions_reflects_concentration():
    # 4 verdicts of the same label, but only 2 distinct tickers.
    rows = [
        _row("consensus_gap", "wächst", "2026-01-01", "AAA"),
        _row("consensus_gap", "wächst", "2026-01-15", "AAA"),  # same position, re-run
        _row("consensus_gap", "wächst", "2026-01-01", "BBB"),
        _row("consensus_gap", "wächst", "2026-01-15", "BBB"),
    ]
    prices = {
        (tk, d): 100.0
        for tk in ("AAA", "BBB")
        for d in ("2026-01-01", "2026-01-15", "2026-01-31", "2026-02-14")
    }
    report = compute_hindsight(rows, _price_fn(prices), as_of=date(2026, 3, 1))
    row = report.by_agent["consensus_gap"][0]
    assert row.total_verdicts == 4
    assert row.distinct_positions == 2


def test_empty_report():
    report = compute_hindsight([], _price_fn({}), as_of=date(2026, 3, 1))
    assert report.is_empty
    assert report.by_agent == {}
    assert report.total_emitted == 0


# --- Repository feeds ------------------------------------------------------------

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    migrate_db(c)
    return c


def _add_position(conn, pos_id, ticker):
    conn.execute(
        """INSERT INTO positions (id, asset_class, investment_type, name, ticker, unit,
                                   added_date, in_portfolio)
           VALUES (?, 'Aktien', 'Aktie', ?, ?, 'Stück', '2026-01-01', 1)""",
        (pos_id, f"Name {pos_id}", ticker),
    )
    conn.commit()


def test_repo_feeds_skip_deleted_positions_and_null_verdicts(conn):
    repo = PositionAnalysesRepository(conn)
    _add_position(conn, 1, "AAA")
    _add_position(conn, 2, "BBB")

    repo.save(1, "consensus_gap", "Standard", "wächst", "s1")
    repo.save(2, "devils_advocate", "Standard", "robust", "s2")
    repo.save(1, "consensus_gap", "Standard", None, "no verdict")   # null verdict -> skip
    # Verdict for a position that no longer exists (survivorship).
    repo.save(999, "consensus_gap", "Standard", "eingeholt", "deleted pos")

    joined = repo.get_verdicts_with_ticker(["consensus_gap", "devils_advocate"])
    tickers = sorted(r["ticker"] for r in joined)
    assert tickers == ["AAA", "BBB"]  # null-verdict and deleted-position rows dropped
    assert all(r["scope"] == "portfolio" for r in joined)  # both positions in_portfolio=1

    # The total counts every emitted (non-null) verdict, incl. the deleted position.
    assert repo.count_directional_verdicts(["consensus_gap", "devils_advocate"]) == 3


def test_repo_feeds_empty_agents(conn):
    repo = PositionAnalysesRepository(conn)
    assert repo.get_verdicts_with_ticker([]) == []
    assert repo.count_directional_verdicts([]) == 0


def test_migration_relabels_legacy_fundamental_agent(conn):
    from core.storage.base import migrate_db

    repo = PositionAnalysesRepository(conn)
    _add_position(conn, 1, "AAA")
    # Simulate a pre-consolidation row written under the old agent name.
    conn.execute(
        "INSERT INTO position_analyses (position_id, agent, skill_name, verdict, created_at) "
        "VALUES (1, 'fundamental', 'Standard', 'unterbewertet', '2026-04-02T00:00:00+00:00')"
    )
    conn.commit()

    migrate_db(conn)  # idempotent re-run applies the FEAT-59 relabel

    assert repo.count_directional_verdicts(["fundamental"]) == 0
    assert repo.count_directional_verdicts(["fundamental_analyzer"]) == 1
