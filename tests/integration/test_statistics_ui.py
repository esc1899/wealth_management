"""
UI smoke tests for the Statistics page: months and agents, provider split, models without price named.

Verifies the page renders without exception and that estimated costs are split
by provider (core/preise.py). Seeds a couple of usage rows via the shared
state singletons and removes them in teardown.
"""

from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

from state import get_usage_repo

PAGES = Path(__file__).resolve().parents[2] / "pages"


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
        at = AppTest.from_file(PAGES / "usage_statistics.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_provider_breakdown_metrics_present(self, seeded_usage):
        at = AppTest.from_file(PAGES / "usage_statistics.py")
        at.run()
        labels = [m.label for m in at.metric]
        # Provider breakdown renders Anthropic + OpenRouter metrics for the seeded rows
        assert "Anthropic" in labels, labels
        assert "OpenRouter" in labels, labels

    def test_models_without_price_are_named_not_hidden(self, seeded_usage, tmp_path, monkeypatch):
        """Blindzeit ist eine Aussage: Was keinen Preis hat, zaehlt 0 -- und die Seite sagt es."""
        monkeypatch.setenv("OPS_CORE_KATALOG", str(tmp_path / "fehlt.toml"))
        at = AppTest.from_file(PAGES / "usage_statistics.py")
        at.run()
        captions = " ".join(c.value for c in at.caption)
        assert "claude-sonnet-4-6" in captions and "mistralai/mistral-large-2512" in captions

    def test_points_to_the_maschinenraum_and_has_no_buttons(self, seeded_usage):
        at = AppTest.from_file(PAGES / "usage_statistics.py")
        at.run()
        assert "/maschinenraum/" in at.markdown[0].value
        assert not at.button
