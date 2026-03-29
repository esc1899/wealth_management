"""
Wealth Management — Streamlit entry point.
Navigation is defined explicitly via st.navigation with grouped sections.
"""

import streamlit as st

st.set_page_config(
    page_title="Wealth Management",
    page_icon="💰",
    layout="wide",
)

from config import config  # noqa: E402

if config.DEMO_MODE:
    st.warning("⚠️ Demo-Modus aktiv — keine echten Daten", icon="🎭")

# Initialise shared resources (agents, repos, scheduler) on first load
from state import get_market_agent, get_portfolio_agent, get_research_agent  # noqa: E402
get_portfolio_agent()
get_market_agent()
get_research_agent()

pg = st.navigation({
    "Portfolio": [
        st.Page("pages/dashboard.py",      title="Dashboard",       icon=":material/dashboard:"),
        st.Page("pages/marktdaten.py",     title="Marktdaten",      icon=":material/trending_up:"),
        st.Page("pages/analyse.py",        title="Analyse",         icon=":material/bar_chart:"),
    ],
    "Assistent 🔒": [
        st.Page("pages/portfolio_chat.py", title="Portfolio Chat",  icon=":material/chat:"),
    ],
    "Research ☁️": [
        st.Page("pages/research_chat.py",  title="Research Chat",   icon=":material/search:"),
        st.Page("pages/settings.py",       title="Einstellungen",   icon=":material/settings:"),
    ],
})

pg.run()
