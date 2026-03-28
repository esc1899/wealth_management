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

# Initialise shared resources (agents, repos, scheduler) on first load
from state import get_market_agent, get_portfolio_agent, get_research_agent  # noqa: E402
get_portfolio_agent()
get_market_agent()
get_research_agent()

pg = st.navigation({
    "": [
        st.Page("pages/dashboard.py", title="Dashboard", icon=":material/dashboard:"),
    ],
    "Analysen": [
        st.Page("pages/analyse.py", title="Analyse", icon=":material/analytics:"),
    ],
    "Agents": [
        st.Page("pages/portfolio_chat.py", title="Portfolio Chat", icon=":material/chat:"),
        st.Page("pages/research_chat.py",  title="Research Chat",  icon=":material/search:"),
    ],
    "System": [
        st.Page("pages/marktdaten.py",   title="Marktdaten",   icon=":material/show_chart:"),
        st.Page("pages/agentmonitor.py", title="Agentmonitor", icon=":material/monitor:"),
    ],
})

pg.run()
