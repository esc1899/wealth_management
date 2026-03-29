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
from core.i18n import t, set_language, current_language, SUPPORTED_LANGUAGES  # noqa: E402

if config.DEMO_MODE:
    st.warning(t("demo.banner"), icon="🎭")

# Initialise shared resources (agents, repos, scheduler) on first load
from state import get_market_agent, get_portfolio_agent, get_research_agent  # noqa: E402
get_portfolio_agent()
get_market_agent()
get_research_agent()

@st.dialog("Disclaimer & Privacy Notice", width="large")
def _legal_dialog():
    tab1, tab2 = st.tabs([t("legal.tab_disclaimer"), t("legal.tab_privacy")])
    with tab1:
        st.write(t("legal.disclaimer_text"))
    with tab2:
        st.write(t("legal.privacy_text"))
    accepted = st.checkbox(t("legal.accept_checkbox"))
    if st.button(t("legal.continue_button"), disabled=not accepted):
        st.session_state["legal_accepted"] = True
        st.rerun()

# Legal modal on first visit per session
if not st.session_state.get("legal_accepted"):
    _legal_dialog()
    st.stop()

pg = st.navigation({
    t("nav.group_portfolio"): [
        st.Page("pages/dashboard.py",      title=t("nav.dashboard"),       icon=":material/dashboard:"),
        st.Page("pages/marktdaten.py",     title=t("nav.market_data"),     icon=":material/trending_up:"),
        st.Page("pages/analyse.py",        title=t("nav.analysis"),        icon=":material/bar_chart:"),
    ],
    t("nav.group_assistant"): [
        st.Page("pages/portfolio_chat.py", title=t("nav.portfolio_chat"),  icon=":material/chat:"),
    ],
    t("nav.group_research"): [
        st.Page("pages/research_chat.py",  title=t("nav.research_chat"),   icon=":material/search:"),
        st.Page("pages/settings.py",       title=t("nav.settings"),        icon=":material/settings:"),
    ],
})

# Language switcher in sidebar
with st.sidebar:
    lang_options = list(SUPPORTED_LANGUAGES.keys())
    current = current_language()
    selected_idx = lang_options.index(current) if current in lang_options else 0
    selected = st.selectbox(
        "🌐",
        options=lang_options,
        format_func=lambda x: SUPPORTED_LANGUAGES[x],
        index=selected_idx,
        key="lang_selector",
        label_visibility="collapsed",
    )
    if selected != current:
        set_language(selected)
        st.rerun()

pg.run()

st.markdown("---")
col1, col2 = st.columns([10, 1])
with col2:
    if st.button(t("legal.legal_footer"), key="legal_reopen"):
        st.session_state["legal_accepted"] = False
        st.rerun()
