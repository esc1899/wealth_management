"""UI smoke test for the Verdict Hindsight page (FEAT-59).

Runs the page against the shared state singletons and asserts it renders without
exception and shows the framing/metrics scaffold.
"""

from pathlib import Path
from streamlit.testing.v1 import AppTest

PAGES = Path(__file__).resolve().parents[2] / "pages"


class TestVerdictHindsightPage:
    def test_page_loads(self):
        at = AppTest.from_file(PAGES / "verdict_hindsight.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_framing_and_metrics_present(self):
        at = AppTest.from_file(PAGES / "verdict_hindsight.py")
        at.run()
        # The journal framing (info box) and the four headline metrics always render.
        assert at.info, "framing info box missing"
        assert len(at.metric) >= 4, [m.label for m in at.metric]
