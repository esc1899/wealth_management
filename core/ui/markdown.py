"""Markdown rendering helpers for LLM output."""

import re
import streamlit as st


def llm_markdown(text: str, **kwargs) -> None:
    """Render LLM-generated markdown, escaping $ to prevent LaTeX math rendering."""
    if not text:
        return
    # Escape dollar signs that aren't already escaped
    safe = re.sub(r'(?<!\\)\$', r'\\$', text)
    st.markdown(safe, **kwargs)
