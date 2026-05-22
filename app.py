"""
Wealth Management — Streamlit entry point.
Navigation is defined explicitly via st.navigation with grouped sections.
"""

import logging
import streamlit as st
import time

st.set_page_config(
    page_title="Wealth Management",
    page_icon="💰",
    layout="wide",
)

from config import config  # noqa: E402

# Configure root logger — all modules inherit this level
_log_level = getattr(logging, config.LOG_LEVEL, logging.INFO)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
from core.health import Severity, is_local_url, run_static_checks  # noqa: E402
from core.i18n import t, set_language, current_language, SUPPORTED_LANGUAGES  # noqa: E402

# Fail fast if required config is missing
_config_errors = config.validate()
if _config_errors:
    for _err in _config_errors:
        st.error(f"⚙️ **Configuration error:** {_err}")
    st.stop()

# Optional: App authentication (login gate) with session timeout (8h)
def _login_form():
    """Full-page login form — renders as main content for password manager autofill."""
    st.markdown("## 🔐 Login")
    with st.form("login_form"):
        st.text_input("Benutzer", value="wealth-management", disabled=True)
        password = st.text_input("Passwort", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Anmelden", use_container_width=True)
    if submitted:
        import hmac
        if hmac.compare_digest(password, config.APP_PASSWORD):
            st.session_state["authenticated"] = True
            st.session_state["auth_time"] = time.time()
            st.rerun()
        else:
            st.error("Falsches Passwort.")

if config.APP_PASSWORD:
    # Check session timeout (8h = 28800 seconds)
    auth_time = st.session_state.get("auth_time")
    if auth_time and time.time() - auth_time > 8 * 3600:
        st.session_state.clear()

    if not st.session_state.get("authenticated"):
        _login_form()
        st.stop()

if config.DEMO_MODE:
    st.warning(t("demo.banner"), icon="🎭")

# Initialise critical shared resources on first load
# Other agents are lazy-loaded when pages access them via @st.cache_resource
from state import (  # noqa: E402
    get_portfolio_agent, get_market_agent, get_agent_scheduler, get_cowork_watcher,
)
get_portfolio_agent()  # Portfolio Chat critical path
get_market_agent()      # Price auto-fetch scheduler
get_agent_scheduler()   # Scheduled cloud jobs runner
get_cowork_watcher()    # Research Ingest file watcher + initial scan

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

_is_local = is_local_url(config.OLLAMA_HOST)
_assistant_group = (
    t("nav.group_assistant") if _is_local
    else t("nav.group_assistant_remote")
)

# Portfolio pages (Watchlist-Analyse local-only)
_portfolio_pages = [
    st.Page("pages/dashboard.py",          title=t("nav.dashboard"),   icon=":material/dashboard:"),
    st.Page("pages/positionen.py",         title=t("nav.positions"),   icon=":material/edit_note:"),
    st.Page("pages/marktdaten.py",         title=t("nav.market_data"), icon=":material/trending_up:"),
    st.Page("pages/analyse.py",            title=t("nav.analysis"),    icon=":material/bar_chart:"),
    st.Page("pages/position_dashboard.py", title="Positionsanalyse",   icon=":material/person_search:"),
]
if _is_local:
    _portfolio_pages.append(
        st.Page("pages/watchlist_analysis.py", title="Watchlist-Analyse", icon=":material/search:"),
    )

# Assistant pages
_assistant_pages = [
    st.Page("pages/portfolio_chat.py",  title=t("nav.portfolio_chat"),  icon=":material/chat:"),
    st.Page("pages/portfolio_story.py",        title="Portfolio Checker",       icon=":material/fact_check:"),
    st.Page("pages/tax_loss_harvesting.py",    title=t("nav.tax_loss_harvesting"), icon=":material/trending_down:"),
]
if _is_local:
    _assistant_pages.append(
        st.Page("pages/watchlist_checker.py", title="Watchlist Checker", icon=":material/check_circle:"),
    )
    _assistant_pages.append(
        st.Page("pages/dividend_calendar.py", title=t("nav.dividend_calendar"), icon=":material/payments:"),
    )
_assistant_pages.append(
    st.Page("pages/wealth_history.py",  title=t("nav.wealth_history"),  icon=":material/show_chart:")
)

pg = st.navigation({
    t("nav.group_portfolio"): _portfolio_pages,
    _assistant_group: _assistant_pages,
    t("nav.group_research"): [
        st.Page("pages/research_chat.py",   title=t("nav.research_chat"),    icon=":material/search:"),
        st.Page("pages/news_chat.py",       title=t("nav.news_chat"),        icon=":material/newspaper:"),
        st.Page("pages/search_chat.py",     title=t("nav.search_chat"),      icon=":material/manage_search:"),
        st.Page("pages/storychecker.py",    title=t("nav.storychecker"),     icon=":material/fact_check:"),
        st.Page("pages/fundamental_analyzer.py", title="Fundamental Analyzer", icon=":material/calculate:"),
        st.Page("pages/cowork_inbox.py",    title="Research Inbox",          icon=":material/inbox:"),
    ],
    t("nav.group_claude_strategy"): [
        st.Page("pages/structural_scan.py",   title=t("nav.structural_scan"),   icon=":material/radar:"),
        st.Page("pages/consensus_gap.py",     title=t("nav.consensus_gap"),     icon=":material/target:"),
        st.Page("pages/sector_rotation.py",   title=t("nav.sector_rotation"),   icon=":material/rotate_right:"),
    ],
    t("nav.group_system"): [
        st.Page("pages/statistics.py",      title=t("nav.statistics"),       icon=":material/bar_chart:"),
        st.Page("pages/skills.py",          title="Skills",                  icon=":material/psychology:"),
        st.Page("pages/scheduler.py",       title="Scheduler",               icon=":material/schedule:"),
        st.Page("pages/settings.py",        title=t("nav.settings"),         icon=":material/settings:"),
        st.Page("pages/cowork_setup.py",    title="Cowork Setup",            icon=":material/settings_suggest:"),
    ],
})

# Sidebar: always-visible system status indicator ("Ampel")
_health_checks = run_static_checks(config)
_has_errors   = any(c.severity == Severity.ERROR   for c in _health_checks)
_has_warnings = any(c.severity == Severity.WARNING for c in _health_checks)

with st.sidebar:
    # Logout button (top right)
    if config.APP_PASSWORD and st.session_state.get("authenticated"):
        if st.button("🔓 Abmelden", use_container_width=False, key="logout_btn"):
            st.session_state.clear()
            st.rerun()
        st.divider()
    if _has_errors:
        st.error(t("health.sidebar_status_error"), icon=":material/error:")
    elif _has_warnings:
        st.warning(t("health.sidebar_status_warning"), icon=":material/warning:")
    else:
        st.success(t("health.sidebar_status_ok"), icon=":material/check_circle:")

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
