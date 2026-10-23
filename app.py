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
# Die Lotsee-Optik (seit 12.10.2026): Grundfarben im Theme (.streamlit/config.toml), Zeichen,
# Menü-Cursor und Lichtschein aus core/ui/optik.py.
from core.ui import optik  # noqa: E402

optik.einbinden()

from config import config  # noqa: E402

# Configure root logger — all modules inherit this level
_log_level = getattr(logging, config.LOG_LEVEL, logging.INFO)
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
from core.i18n import t  # noqa: E402

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
        submitted = st.form_submit_button("Anmelden", width="stretch")
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
    get_market_agent,
    get_scheduled_job_runs_repo,
)
get_market_agent()      # Market data (scheduled fetch runs in the planner service)

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

# Legal modal on first visit per session (disable per installation: SHOW_LEGAL_NOTICE=false)
if config.SHOW_LEGAL_NOTICE and not st.session_state.get("legal_accepted"):
    _legal_dialog()
    st.stop()

# Oben die Kacheln, Depot ist die Startseite.
_neu_pages = [
    st.Page("pages/kacheln_depot.py",      title=t("kacheln.nav_depot"),     icon=":material/grid_view:", default=True),
    st.Page("pages/kacheln_watchlist.py",  title=t("kacheln.nav_watchlist"), icon=":material/visibility:"),
]

_AUS = "hidden"

# Pflege und Performance: die Basis ohne Sprachmodell (mit Kacheln oben). Ein KI-Knopf darin
# ist ein Extra und ohne erreichbares Ollama ausgegraut (core/ui/lokales_modell.py).
_pflege_pages = [
    st.Page("pages/positionen.py",         title=t("nav.positions"),          icon=":material/edit_note:"),
    st.Page("pages/portfolio_narrativ.py", title=t("nav.portfolio_narrativ"), icon=":material/menu_book:"),
]
_performance_pages = [
    st.Page("pages/analyse.py",           title=t("nav.analysis"),          icon=":material/bar_chart:"),
    st.Page("pages/dividend_calendar.py", title=t("nav.dividend_calendar"), icon=":material/payments:"),
    st.Page("pages/wealth_history.py",    title=t("nav.wealth_history"),    icon=":material/show_chart:"),
    st.Page("pages/tax_loss_harvesting.py", title=t("nav.tax_loss_harvesting"), icon=":material/trending_down:"),
    # Bewertet die Sektoren des eigenen Depots, sucht keine neuen Titel (11.10.2026).
    st.Page("pages/sector_rotation.py",   title=t("nav.sector_rotation"),   icon=":material/rotate_right:"),
    # Wie gut die Urteile der Checks gealtert sind; rechnet nur, ruft kein Modell (11.10.2026).
    st.Page("pages/verdict_hindsight.py", title=t("nav.verdict_hindsight"), icon=":material/history_toggle_off:"),
]
# Suche: eine Seite, oben die Strategie (freie Suche, Einzeltitel, Strukturwandel); die
# frueheren Seiten sind ihre Teile (core/ui/suche/); darunter die Kandidaten, deren Titelseite
# (pages/kandidat.py) nur ueber ihre Kachel erreichbar ist.
_suche_pages = [
    st.Page("pages/suche.py", title=t("nav.suche"), icon=":material/manage_search:"),
]

# Ohne Menuepunkt: Positions- und Watchlist-Analyse erreicht man ueber Titel und Kaestchen der
# Kacheln, den Kandidaten ueber seine Kachel. Sie haengen an der ersten Gruppe, damit keine
# Gruppe ohne sichtbare Seite eine leere Ueberschrift zeigt.
_ausgeblendet = [
    st.Page("pages/position_dashboard.py", title="Positionsanalyse",   icon=":material/person_search:", visibility=_AUS),
    st.Page("pages/watchlist_analysis.py", title="Watchlist-Analyse",  icon=":material/search:", visibility=_AUS),
    st.Page("pages/kandidat.py",           title="Kandidat",           icon=":material/travel_explore:", visibility=_AUS),
]

pg = st.navigation({
    t("kacheln.nav_gruppe"): _neu_pages + _ausgeblendet,
    t("nav.group_pflege"): _pflege_pages,
    t("nav.group_performance"): _performance_pages,
    t("nav.group_suche"): _suche_pages,
    # Einstellungen zuletzt: was den Betrieb einstellt, nichts zum Lesen. Die Gruppe System ist
    # darin aufgegangen (11.10.2026).
    t("nav.settings"): [
        st.Page("pages/settings.py",         title=t("nav.settings"),   icon=":material/settings:"),
        st.Page("pages/skills.py",           title="Skills",            icon=":material/psychology:"),
        st.Page("pages/scheduler.py",        title="Scheduler",         icon=":material/schedule:"),
        st.Page("pages/usage_statistics.py", title=t("nav.statistics"), icon=":material/bar_chart:"),
        # Das Schema als Bild (22.10.2026): nur fuer Erik, nichts zum Bedienen.
        st.Page("pages/ontologie.py",        title=t("nav.ontologie"),  icon=":material/hub:"),
    ],
})

# Seitenleiste: keine Ampel mehr (12.10.2026) -- sie pruefte nur die Konfiguration und meldete
# trotzdem "alles ok"; der Zustand steht in den Einstellungen. Die Sprache waehlt man dort.
with st.sidebar:
    # Logout button (top right)
    if config.APP_PASSWORD and st.session_state.get("authenticated"):
        if st.button("🔓 Abmelden", width="content", key="logout_btn"):
            st.session_state.clear()
            st.rerun()
        st.divider()
    # Scheduler runtime status: only visible when the latest run of an enabled
    # job failed — recovered jobs (green after red) clear the warning immediately.
    try:
        _failed_jobs = get_scheduled_job_runs_repo().count_jobs_with_failed_latest_run()
    except Exception:
        _failed_jobs = 0  # never block the app over a status query
    if _failed_jobs:
        st.warning(
            t("health.sidebar_scheduler_failed").format(n=_failed_jobs),
            icon=":material/schedule:",
        )
        st.page_link("pages/scheduler.py", label=t("health.sidebar_scheduler_link"))

pg.run()

if config.SHOW_LEGAL_NOTICE:
    st.markdown("---")
    col1, col2 = st.columns([10, 1])
    with col2:
        if st.button(t("legal.legal_footer"), key="legal_reopen"):
            st.session_state["legal_accepted"] = False
            st.rerun()
