"""
Streamlit UI smoke tests for pages.
Uses Streamlit's experimental testing API to verify pages load without exceptions.

Note: These are smoke tests focusing on import errors and runtime crashes,
not full integration tests. Full UI testing would require Playwright/Selenium.
"""

from streamlit.testing.v1 import AppTest


class TestPageLoadability:
    """Smoke tests: verify pages load without exceptions.

    This catches import errors, syntax errors, and immediate runtime crashes
    that would occur during page initialization.
    """

    def test_watchlist_checker_page_loads(self):
        """Watchlist Checker page should load without exceptions."""
        at = AppTest.from_file("pages/watchlist_checker.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_portfolio_story_page_loads(self):
        """Portfolio Story page should load without exceptions."""
        at = AppTest.from_file("pages/portfolio_story.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_fundamental_analyzer_page_loads(self):
        """Fundamental Analyzer page should load without exceptions."""
        at = AppTest.from_file("pages/fundamental_analyzer.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_consensus_gap_page_loads(self):
        """Consensus Gap page should load without exceptions."""
        at = AppTest.from_file("pages/consensus_gap.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_storychecker_page_loads(self):
        """Story Checker page should load without exceptions."""
        at = AppTest.from_file("pages/storychecker.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"
