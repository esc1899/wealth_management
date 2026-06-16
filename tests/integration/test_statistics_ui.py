"""
UI smoke tests for the Statistics page — FEAT-58 provider × method framing.

Verifies the page renders without exception and that estimated costs are split
by provider (registry-driven). Seeds a couple of usage rows via the shared
state singletons and removes them in teardown.
"""

import pytest
from streamlit.testing.v1 import AppTest

from state import get_usage_repo


@pytest.fixture
def seeded_usage(request):
    repo = get_usage_repo()
    conn = repo._conn
    _before = conn.execute("SELECT COALESCE(MAX(id), 0) FROM llm_usage").fetchone()[0]
    # One Claude call + one OpenRouter call this month
    repo.record("news", "claude-sonnet-4-6", 1000, 500, skill="Standard")
    repo.record("search", "mistralai/mistral-large-2512", 2000, 800, skill="Standard")

    def cleanup():
        # Remove exactly the rows we inserted, leaving other tests' data intact.
        conn.execute("DELETE FROM llm_usage WHERE id > ?", (_before,))
        conn.commit()

    request.addfinalizer(cleanup)


class TestStatisticsPage:
    def test_page_loads(self, seeded_usage):
        at = AppTest.from_file("pages/statistics.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_provider_breakdown_metrics_present(self, seeded_usage):
        at = AppTest.from_file("pages/statistics.py")
        at.run()
        labels = [m.label for m in at.metric]
        # Provider breakdown renders Anthropic + OpenRouter metrics for the seeded rows
        assert "Anthropic" in labels, labels
        assert "OpenRouter" in labels, labels

    def test_costs_and_tokens_sections_present(self, seeded_usage):
        at = AppTest.from_file("pages/statistics.py")
        at.run()
        headers = " ".join(sh.value for sh in at.subheader)
        assert "Kosten" in headers, headers
        assert "Tokens" in headers, headers
        # The old "Geschätzt"/"Abgefragt" wording is gone from the headers
        assert "Geschätzt" not in headers, headers
        assert "Abgefragt" not in headers, headers
