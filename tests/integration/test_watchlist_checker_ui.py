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

    # Agent Pages (Cloud & Local) — Multi-turn sessions
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

    def test_structural_scan_page_loads(self):
        """Structural Scan page should load without exceptions."""
        at = AppTest.from_file("pages/structural_scan.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_research_chat_page_loads(self):
        """Research Chat page should load without exceptions."""
        at = AppTest.from_file("pages/research_chat.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_search_chat_page_loads(self):
        """Investment Search page should load without exceptions."""
        at = AppTest.from_file("pages/search_chat.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_portfolio_chat_page_loads(self):
        """Portfolio Chat page should load without exceptions."""
        at = AppTest.from_file("pages/portfolio_chat.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    # Admin & Dashboard Pages
    def test_dashboard_page_loads(self):
        """Dashboard page should load without exceptions."""
        at = AppTest.from_file("pages/dashboard.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_positionen_page_loads(self):
        """Positions page should load without exceptions."""
        at = AppTest.from_file("pages/positionen.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_marktdaten_page_loads(self):
        """Market Data page should load without exceptions."""
        at = AppTest.from_file("pages/marktdaten.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_wealth_history_page_loads(self):
        """Wealth History page should load without exceptions."""
        at = AppTest.from_file("pages/wealth_history.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_wealth_assistant_page_loads(self):
        """Wealth Assistant page should load without exceptions."""
        at = AppTest.from_file("pages/wealth_assistant.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_analyse_page_loads(self):
        """Analysis (Performance) page should load without exceptions."""
        at = AppTest.from_file("pages/analyse.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_news_chat_page_loads(self):
        """News Digest page should load without exceptions."""
        at = AppTest.from_file("pages/news_chat.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    # System Pages
    def test_statistics_page_loads(self):
        """Statistics page should load without exceptions."""
        at = AppTest.from_file("pages/statistics.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_skills_page_loads(self):
        """Skills Management page should load without exceptions."""
        at = AppTest.from_file("pages/skills.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_settings_page_loads(self):
        """Settings page should load without exceptions."""
        at = AppTest.from_file("pages/settings.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"
