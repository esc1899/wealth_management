"""
UI integration tests for FEAT-55 — Research-Ergebnis-Integration.

Seeds data through the shared state singletons (cached :memory: connection,
DB_PATH=":memory:" from conftest) and runs the pages via AppTest. Seeded rows
are removed in teardown so other page smoke tests stay unaffected.
"""

from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from core.storage.models import Position
from state import get_positions_repo, get_research_queue_repo


@pytest.fixture
def seeded(request):
    """Portfolio position MSFT + open request + done request with answers."""
    pos_repo = get_positions_repo()
    rq_repo = get_research_queue_repo()

    pos = pos_repo.add(
        Position(
            asset_class="Aktie",
            investment_type="stock",
            name="Microsoft",
            ticker="MSFT",
            unit="Stück",
            quantity=10.0,
            in_portfolio=True,
            added_date=date.today(),
        )
    )
    open_req = rq_repo.create_request("Wettbewerbsposition prüfen", ticker="MSFT")
    open_ans = rq_repo.submit_answer(
        "## Zwischenstand\nErste Funde.", request_id=open_req.id, ticker="MSFT"
    )
    done_req = rq_repo.create_request("Q3-Zahlen einordnen", ticker="MSFT")
    done_ans = rq_repo.submit_answer(
        "## Ergebnis\nSolide Zahlen.", request_id=done_req.id, ticker="MSFT"
    )
    rq_repo.complete_request(done_req.id)

    def cleanup():
        rq_repo.delete_answer(open_ans.id)
        rq_repo.delete_answer(done_ans.id)
        rq_repo.delete_request(open_req.id)
        rq_repo.delete_request(done_req.id)
        pos_repo.delete(pos.id)

    request.addfinalizer(cleanup)
    return pos, open_req, done_req


class TestResearchAnswersPage:
    def test_page_loads_with_seeded_data(self, seeded):
        at = AppTest.from_file("pages/research_answers.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_to_position_button_for_portfolio_ticker(self, seeded):
        at = AppTest.from_file("pages/research_answers.py")
        at.run()
        keys = [b.key for b in at.button]
        assert any(k and k.startswith("to_pos_") for k in keys), keys

    def test_done_request_shows_answer_toggle(self, seeded):
        _, _, done_req = seeded
        at = AppTest.from_file("pages/research_answers.py")
        at.run()
        toggle_keys = [tg.key for tg in at.toggle]
        assert f"show_answer_{done_req.id}" in toggle_keys, toggle_keys


class TestPositionDashboardAnswersSection:
    def test_dashboard_shows_answers_for_ticker(self, seeded):
        at = AppTest.from_file("pages/position_dashboard.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"
        # Answers section header rendered (2 answers for MSFT)
        headers = [s.value for s in at.subheader]
        assert any("Research-Antworten (2)" in h or "Research answers (2)" in h for h in headers), headers


@pytest.fixture
def seeded_watchlist(request):
    """Watchlist position LIN + answer + Cowork-Research-Entry mit Suggestion."""
    from state import get_cowork_repo

    pos_repo = get_positions_repo()
    rq_repo = get_research_queue_repo()
    cowork_repo = get_cowork_repo()

    pos = pos_repo.add(
        Position(
            asset_class="Aktie",
            investment_type="stock",
            name="Linde",
            ticker="LIN",
            unit="Stück",
            quantity=1.0,
            in_portfolio=False,
            in_watchlist=True,
            added_date=date.today(),
        )
    )
    req = rq_repo.create_request("Burggraben prüfen", ticker="LIN")
    ans = rq_repo.submit_answer("## Ergebnis\nOligopol hält.", request_id=req.id, ticker="LIN")
    entry = cowork_repo.create_entry(
        research_id="wla-test-lin-001",
        type="watchlist_scan",
        date=date.today(),
        model="test-model",
        status="ready_for_import",
        body_markdown="# Deep Dive\nIndustriegase seit 1902.",
        sources=[],
        disclaimer="Test.",
        request_id=req.id,
    )
    suggestion = cowork_repo.create_suggestion(
        research_id="wla-test-lin-001",
        ticker="LIN",
        exchange="XETRA",
        name="Linde plc",
        rationale="Oligopol.",
        conviction="high",
        suggested_action="watch",
    )

    def cleanup():
        conn = cowork_repo._conn
        conn.execute("DELETE FROM cowork_watchlist_suggestions WHERE id = ?", (suggestion.id,))
        conn.execute("DELETE FROM cowork_research_entries WHERE id = ?", (entry.id,))
        conn.commit()
        rq_repo.delete_answer(ans.id)
        rq_repo.delete_request(req.id)
        pos_repo.delete(pos.id)

    request.addfinalizer(cleanup)
    return pos


class TestWatchlistAnalysisResearchSection:
    def test_page_loads_with_seeded_watchlist(self, seeded_watchlist):
        at = AppTest.from_file("pages/watchlist_analysis.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_shows_answers_and_cowork_research(self, seeded_watchlist):
        at = AppTest.from_file("pages/watchlist_analysis.py")
        at.run()
        headers = [s.value for s in at.subheader]
        assert any("Research-Antworten (1)" in h or "Research answers (1)" in h for h in headers), headers
        assert any("Cowork" in h for h in headers), headers
