"""
UI smoke tests for FEAT-56 — bilingual Cowork Setup page.

The page has no data dependencies (config only). These tests verify it renders
without exception in both languages and that the system prompt / example file
follow current_language().
"""

import pytest
from streamlit.testing.v1 import AppTest

from pages.cowork_setup import (
    _EXAMPLE_FILE_DE,
    _EXAMPLE_FILE_EN,
    _SYSTEM_PROMPT_DE,
    _SYSTEM_PROMPT_EN,
)


@pytest.mark.parametrize("lang", ["de", "en"])
def test_page_renders(lang):
    at = AppTest.from_file("pages/cowork_setup.py", default_timeout=30)
    at.session_state["lang"] = lang
    at.run()
    assert not at.exception, f"{lang}: {at.exception}"
    assert at.subheader  # at least the section headers rendered


def test_system_prompt_follows_language():
    """Both prompts share the format but differ in prose language."""
    # English-specific phrasing only in the EN variant
    assert "investment profile" in _SYSTEM_PROMPT_EN.lower()
    assert "investmentprofil" in _SYSTEM_PROMPT_DE.lower()
    # Field names / enums stay identical (DB identifiers) in both
    for token in ("watchlist_candidates", "ready_for_import", "request_id"):
        assert token in _SYSTEM_PROMPT_DE
        assert token in _SYSTEM_PROMPT_EN


def test_example_file_follows_language():
    assert "AI-generated research" in _EXAMPLE_FILE_EN
    assert "KI-generiertes Research" in _EXAMPLE_FILE_DE
    # The frontmatter (identifiers) is identical in both
    for token in ("research_id:", "status: ready_for_import", "ticker: ASML"):
        assert token in _EXAMPLE_FILE_DE
        assert token in _EXAMPLE_FILE_EN
