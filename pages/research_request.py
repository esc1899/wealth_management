"""
Research anfordern — globale Research-Anfrage ohne Positions-Bezug (FEAT-55).

Erstellt offene Research-Requests (z.B. "SpaceX zeichnen?"), die Claude
über den UserPromptSubmit-Hook bzw. get_research_queue() abholt.
"""

import streamlit as st

from core.ui.research_request_form import render_research_request_form
from state import get_research_queue_repo

st.set_page_config(
    page_title="Research anfordern",
    page_icon=":material/add_circle:",
    layout="wide",
)

render_research_request_form(get_research_queue_repo(), show_ticker_field=True)
