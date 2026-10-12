"""
Streamlit UI smoke tests for pages.
Uses Streamlit's experimental testing API to verify pages load without exceptions.

Note: These are smoke tests focusing on import errors and runtime crashes,
not full integration tests. Full UI testing would require Playwright/Selenium.
"""

from pathlib import Path
from streamlit.testing.v1 import AppTest

PAGES = Path(__file__).resolve().parents[2] / "pages"


class TestPageLoadability:
    """Smoke tests: verify pages load without exceptions.

    This catches import errors, syntax errors, and immediate runtime crashes
    that would occur during page initialization.
    """

    # Agent Pages (Cloud & Local) — Multi-turn sessions
    def test_scheduler_page_loads(self):
        """Scheduler page — since 2026-10-02 without reload_jobs(); the jobs run as
        the ops-core job `agenten`."""
        at = AppTest.from_file(PAGES / "scheduler.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_watchlist_checker_page_loads(self):
        """Watchlist Checker page should load without exceptions."""
        at = AppTest.from_file(PAGES / "watchlist_checker.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_portfolio_story_page_loads(self):
        """Portfolio Story page should load without exceptions."""
        at = AppTest.from_file(PAGES / "portfolio_story.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_rebalance_chat_page_loads(self):
        """Invest / Rebalance page should load without exceptions."""
        at = AppTest.from_file(PAGES / "rebalance_chat.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_tax_loss_harvesting_page_loads(self):
        """Tax Loss Harvesting page should load without exceptions."""
        at = AppTest.from_file(PAGES / "tax_loss_harvesting.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_fundamental_analyzer_page_loads(self):
        """Fundamental Analyzer page should load without exceptions."""
        at = AppTest.from_file(PAGES / "fundamental_analyzer.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_consensus_gap_page_loads(self):
        """Consensus Gap page should load without exceptions."""
        at = AppTest.from_file(PAGES / "consensus_gap.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_storychecker_page_loads(self):
        """Story Checker page should load without exceptions."""
        at = AppTest.from_file(PAGES / "storychecker.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_sector_rotation_page_loads(self):
        """Sektorrotation: wieder eine eigene Seite unter Performance (11.10.2026)."""
        at = AppTest.from_file(PAGES / "sector_rotation.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_suche_zeigt_jede_strategie(self):
        """Suche (11.10.2026): eine Seite, oben die Strategie -- jeder Teil laedt."""
        at = AppTest.from_file(PAGES / "suche.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"
        for art in ("einzeltitel", "strukturwandel", "frei"):
            at.button_group(key="suche_art").set_value(art).run()
            assert not at.exception, f"{art}: {at.exception}"

    def test_research_chat_page_loads(self):
        """Research Chat page should load without exceptions."""
        at = AppTest.from_file(PAGES / "research_chat.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_portfolio_chat_page_loads(self):
        """Portfolio Chat page should load without exceptions."""
        at = AppTest.from_file(PAGES / "portfolio_chat.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    # Admin & Dashboard Pages
    def test_dashboard_page_loads(self):
        """Dashboard page should load without exceptions."""
        at = AppTest.from_file(PAGES / "dashboard.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_positionen_page_loads(self):
        """Positions page should load without exceptions."""
        at = AppTest.from_file(PAGES / "positionen.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_marktdaten_page_loads(self):
        """Market Data page should load without exceptions."""
        at = AppTest.from_file(PAGES / "marktdaten.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_wealth_history_page_loads(self):
        """Wealth History page should load without exceptions."""
        at = AppTest.from_file(PAGES / "wealth_history.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_analyse_page_loads(self):
        """Analysis (Performance) page should load without exceptions."""
        at = AppTest.from_file(PAGES / "analyse.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_position_dashboard_page_loads(self):
        """Position Dashboard page should load without exceptions."""
        at = AppTest.from_file(PAGES / "position_dashboard.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_news_chat_page_loads(self):
        """News Digest page should load without exceptions."""
        at = AppTest.from_file(PAGES / "news_chat.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_research_answers_page_loads(self):
        """Research Answers page (incl. new-request tab) should load without exceptions."""
        at = AppTest.from_file(PAGES / "research_answers.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    # System Pages
    def test_statistics_page_loads(self):
        """Statistics page should load without exceptions."""
        at = AppTest.from_file(PAGES / "usage_statistics.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_skills_page_loads(self):
        """Skills Management page should load without exceptions."""
        at = AppTest.from_file(PAGES / "skills.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_settings_page_loads(self):
        """Settings page should load without exceptions."""
        at = AppTest.from_file(PAGES / "settings.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_cowork_inbox_loads(self):
        """Cowork Research Inbox page should load without exceptions."""
        at = AppTest.from_file(PAGES / "cowork_inbox.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_cowork_setup_loads(self):
        """Cowork Setup page should load without exceptions."""
        at = AppTest.from_file(PAGES / "cowork_setup.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_watchlist_analysis_page_loads(self):
        """Watchlist-Analyse page should load without exceptions."""
        at = AppTest.from_file(PAGES / "watchlist_analysis.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"

    def test_scheduler_page_loads(self):
        """Scheduler page should load without exceptions."""
        at = AppTest.from_file(PAGES / "scheduler.py")
        at.run()
        assert not at.exception, f"Page threw exception: {at.exception}"
