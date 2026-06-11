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
