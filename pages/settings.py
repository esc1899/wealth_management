"""
Settings — manage model selection and system configuration.
"""

import logging

import streamlit as st

logger = logging.getLogger(__name__)

from config import config
from core.health import Severity, check_ollama_connectivity, run_static_checks
from core.i18n import SUPPORTED_LANGUAGES, current_language, set_language, t
from core.llm.claude import fetch_available_models as _fetch_claude_models
from state import get_app_config_repo, get_skills_repo

st.set_page_config(page_title="Einstellungen", page_icon="⚙️", layout="wide")
st.title(t("settings.title"))

# ------------------------------------------------------------------
# Section: System Health
# ------------------------------------------------------------------

st.subheader(t("health.title"))

_static_checks = run_static_checks(config)
_all_checks = list(_static_checks)

if st.button(t("health.check_connectivity"), icon=":material/wifi_find:"):
    with st.spinner("…"):
        st.session_state["_ollama_conn_check"] = check_ollama_connectivity(config.OLLAMA_HOST)

if "_ollama_conn_check" in st.session_state:
    _all_checks.append(st.session_state["_ollama_conn_check"])

if not _all_checks or all(c.severity == Severity.OK for c in _all_checks):
    st.success(t("health.all_ok"), icon=":material/check_circle:")
else:
    for _chk in _all_checks:
        _title = t(f"health.checks.{_chk.key}.title")
        _desc = t(f"health.checks.{_chk.key}.description")
        if _chk.detail:
            _desc = _desc.replace("{detail}", _chk.detail)
        _msg = f"**{_title}** — {_desc}"
        if _chk.severity == Severity.ERROR:
            st.error(_msg, icon=":material/error:")
        elif _chk.severity == Severity.WARNING:
            st.warning(_msg, icon=":material/warning:")
        else:
            st.success(_msg, icon=":material/check_circle:")

st.divider()

# ------------------------------------------------------------------
# Section: Language selection
# ------------------------------------------------------------------

st.subheader(t("settings.language_label"))

lang_options = list(SUPPORTED_LANGUAGES.keys())
lang_labels = list(SUPPORTED_LANGUAGES.values())
current_lang = current_language()
lang_idx = lang_options.index(current_lang) if current_lang in lang_options else 0

chosen_lang = st.radio(
    t("settings.language_label"),
    options=lang_options,
    format_func=lambda k: SUPPORTED_LANGUAGES[k],
    index=lang_idx,
    horizontal=True,
    label_visibility="collapsed",
)
if chosen_lang != current_lang:
    set_language(chosen_lang)
    st.rerun()

st.divider()

# ------------------------------------------------------------------
# Section: Model selection
# ------------------------------------------------------------------

app_config = get_app_config_repo()

st.subheader(t("settings.model_selection_header"))

# Fetch available Claude models from Anthropic API, fallback to config
@st.cache_resource(ttl=3600)
def _get_claude_model_list() -> list[str]:
    if not config.LLM_API_KEY:
        return config.CLAUDE_MODELS
    models = _fetch_claude_models(config.LLM_API_KEY, config.LLM_BASE_URL)
    return models if models else config.CLAUDE_MODELS

_CLAUDE_MODELS = _get_claude_model_list()

# Detect if OpenAI-compatible provider is active
_OPENAI_ACTIVE = bool(config.OPENAI_BASE_URL)
_PUBLIC_MODELS = config.OPENAI_MODELS if _OPENAI_ACTIVE else _CLAUDE_MODELS
_PUBLIC_TYPE = "openai" if _OPENAI_ACTIVE else "claude"

# Fetch available Ollama models
import requests as _requests

def _get_ollama_model_list() -> list[str]:
    try:
        url = f"{config.OLLAMA_HOST.rstrip('/')}/api/tags"
        resp = _requests.get(url, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        logger.debug("Ollama model discovery failed: %s", e)
    return []

_ollama_models = _get_ollama_model_list()
if not _ollama_models:
    st.caption(t("settings.ollama_unavailable"))
    _ollama_models = [config.OLLAMA_MODEL]

def _ollama_sel(agent_key: str, label: str) -> str:
    saved = app_config.get(f"model_ollama_{agent_key}") or app_config.get("model_ollama") or config.OLLAMA_MODEL
    idx = _ollama_models.index(saved) if saved in _ollama_models else 0
    return st.selectbox(label, options=_ollama_models, index=idx, key=f"_model_ollama_{agent_key}")

def _claude_sel(agent_key: str, label: str) -> str:
    saved = app_config.get(f"model_claude_{agent_key}") or app_config.get("model_claude") or (_CLAUDE_MODELS[0] if _CLAUDE_MODELS else "")
    idx = _CLAUDE_MODELS.index(saved) if saved in _CLAUDE_MODELS else 0
    return st.selectbox(label, options=_CLAUDE_MODELS, index=idx, key=f"_model_claude_{agent_key}")

def _public_sel(agent_key: str, label: str) -> str:
    saved = (
        app_config.get(f"model_{_PUBLIC_TYPE}_{agent_key}")
        or app_config.get(f"model_{_PUBLIC_TYPE}")
        or (_PUBLIC_MODELS[0] if _PUBLIC_MODELS else "")
    )
    idx = _PUBLIC_MODELS.index(saved) if saved in _PUBLIC_MODELS else 0
    return st.selectbox(
        label,
        options=_PUBLIC_MODELS or ["(configure OPENAI_MODELS)" if _OPENAI_ACTIVE else "(no models)"],
        index=idx,
        key=f"_model_{_PUBLIC_TYPE}_{agent_key}"
    )

st.markdown(f"**{t('settings.ollama_agents_header')}** 🔒")
col_o1, col_o2, col_o3 = st.columns(3)
with col_o1:
    sel_portfolio = _ollama_sel("portfolio", t("settings.agent_portfolio_chat"))
with col_o2:
    sel_portfolio_story = _ollama_sel("portfolio_story", "Portfolio Story")
with col_o3:
    sel_watchlist_checker = _ollama_sel("watchlist_checker", "Watchlist Checker")

col_o4, _ = st.columns([1, 2])
with col_o4:
    sel_portfolio_comment = _ollama_sel("portfolio_comment", "💬 KI-Kommentare")

_provider_icon = "🌐" if _OPENAI_ACTIVE else "☁️"
_provider_label = t('settings.claude_agents_header') if not _OPENAI_ACTIVE else "OpenAI-compatible"

st.markdown(f"**{_provider_label}** {_provider_icon}")
col_c1, col_c2, col_c3 = st.columns(3)
with col_c1:
    sel_news = _public_sel("news", t("settings.agent_news"))
with col_c2:
    sel_search = _public_sel("search", t("settings.agent_search"))
with col_c3:
    sel_storychecker = _public_sel("storychecker", t("settings.agent_storychecker"))

st.markdown(f"**{_provider_label} Strategy** {_provider_icon}")
col_s1, col_s2, col_s3 = st.columns(3)
with col_s1:
    sel_structural = _public_sel("structural_scan", t("settings.agent_structural_scan"))
with col_s2:
    sel_consensus = _public_sel("consensus_gap", t("settings.agent_consensus_gap"))
with col_s3:
    sel_fundamental = _public_sel("fundamental_analyzer", t("settings.agent_fundamental"))

col_s4, _ = st.columns([1, 2])
with col_s4:
    sel_capital_allocator = _public_sel("capital_allocator", "Capital Allocator")

if st.button(t("settings.save_models_button"), key="_save_models_btn", use_container_width=False):
    app_config.set("model_ollama_portfolio", sel_portfolio)
    app_config.set("model_ollama_portfolio_story", sel_portfolio_story)
    app_config.set("model_ollama_watchlist_checker", sel_watchlist_checker)
    app_config.set("model_ollama_portfolio_comment", sel_portfolio_comment)
    app_config.set(f"model_{_PUBLIC_TYPE}_news", sel_news)
    app_config.set(f"model_{_PUBLIC_TYPE}_search", sel_search)
    app_config.set(f"model_{_PUBLIC_TYPE}_storychecker", sel_storychecker)
    app_config.set(f"model_{_PUBLIC_TYPE}_structural_scan", sel_structural)
    app_config.set(f"model_{_PUBLIC_TYPE}_consensus_gap", sel_consensus)
    app_config.set(f"model_{_PUBLIC_TYPE}_fundamental_analyzer", sel_fundamental)
    app_config.set(f"model_{_PUBLIC_TYPE}_capital_allocator", sel_capital_allocator)
    st.cache_resource.clear()
    st.success(t("settings.models_saved"))

st.divider()

# ------------------------------------------------------------------
# Section: Model prices
# ------------------------------------------------------------------

st.subheader(t("settings.model_prices_header"))
st.caption(t("settings.model_prices_caption"))

_current_prices = app_config.get_model_prices()

# Header row
_ph1, _ph2, _ph3 = st.columns([3, 1, 1])
_ph1.caption("Modell")
_ph2.caption(t("settings.model_prices_input_label") + " ($/Mio)")
_ph3.caption(t("settings.model_prices_output_label") + " ($/Mio)")

# Render one row per model
_price_edits: dict = {}
for _model_id, _price in _current_prices.items():
    _pc1, _pc2, _pc3 = st.columns([3, 1, 1])
    _pc1.markdown(f"`{_model_id}`")
    _price_edits[_model_id] = {
        "input": _pc2.number_input(
            t("settings.model_prices_input_label"),
            value=float(_price.get("input", 0.0)),
            min_value=0.0,
            step=0.01,
            format="%.4f",
            key=f"_price_in_{_model_id}",
            label_visibility="collapsed",
        ),
        "output": _pc3.number_input(
            t("settings.model_prices_output_label"),
            value=float(_price.get("output", 0.0)),
            min_value=0.0,
            step=0.01,
            format="%.4f",
            key=f"_price_out_{_model_id}",
            label_visibility="collapsed",
        ),
    }

# Add a new model row
with st.expander(t("settings.model_prices_add_model")):
    _new_model_id = st.text_input(t("settings.model_prices_model_id"), key="_new_price_model_id")
    _nc1, _nc2 = st.columns(2)
    _new_price_in = _nc1.number_input(
        t("settings.model_prices_input_label"), min_value=0.0, step=0.01, format="%.4f", key="_new_price_in"
    )
    _new_price_out = _nc2.number_input(
        t("settings.model_prices_output_label"), min_value=0.0, step=0.01, format="%.4f", key="_new_price_out"
    )

if st.button(t("settings.model_prices_save"), key="_save_prices_btn"):
    _saved_prices = dict(_price_edits)
    if _new_model_id.strip():
        _saved_prices[_new_model_id.strip()] = {"input": _new_price_in, "output": _new_price_out}
    app_config.set_model_prices(_saved_prices)
    st.success(t("settings.model_prices_saved"))

st.divider()

# ------------------------------------------------------------------
# Section: KI-Kommentarstil
# ------------------------------------------------------------------

st.subheader("💬 KI-Kommentarstil")
st.caption("Wird für KI-Kommentare verwendet (Portfolio Story, erweiterbar auf weitere Seiten)")

from core.services.portfolio_comment_service import get_style_options

_styles = get_style_options()
_style_ids = [s["id"] for s in _styles]
_style_labels = [f"{s['emoji']} {s['name']}" for s in _styles]
_saved_style = app_config.get("comment_style") or _style_ids[0]
_style_idx = _style_ids.index(_saved_style) if _saved_style in _style_ids else 0
_sel_label = st.selectbox(
    "Kommentarstil",
    _style_labels,
    index=_style_idx,
    key="_settings_comment_style",
)
_sel_id = _style_ids[_style_labels.index(_sel_label)]
_sel_style = _styles[_style_ids.index(_sel_id)]
st.caption(f"_{_sel_style['instruction']}_")

if st.button("💾 Stil speichern", key="_save_comment_style_btn"):
    app_config.set("comment_style", _sel_id)
    st.success("Kommentarstil gespeichert!")

st.divider()

# ------------------------------------------------------------------
# Section: Backup
# ------------------------------------------------------------------

import os as _os
import subprocess as _subprocess

st.subheader("💾 Backup")

_BACKUP_SCRIPT = _os.path.expanduser("~/scripts/wm_backup.sh")
_BACKUP_REPO = config.BACKUP_REPO_PATH
_BACKUP_LOG = _os.path.expanduser("~/Library/Logs/wm_backup.log")

_drive_mounted = bool(_BACKUP_REPO) and _os.path.isdir(_BACKUP_REPO)
_script_exists = _os.path.isfile(_BACKUP_SCRIPT)

if not _script_exists:
    st.warning(f"Backup-Script nicht gefunden: `{_BACKUP_SCRIPT}`")
elif not _BACKUP_REPO:
    st.warning("BACKUP_REPO_PATH ist nicht in `.env` gesetzt.")
elif _drive_mounted:
    st.success(f"WD Passport verbunden — bereit für Backup", icon=":material/check_circle:")
else:
    st.info("WD Passport nicht verbunden. Laufwerk anschließen, dann Backup starten.", icon=":material/usb:")

if _script_exists and _drive_mounted:
    if st.button("▶ Jetzt sichern", type="primary", key="_backup_now_btn"):
        with st.spinner("Backup läuft…"):
            result = _subprocess.run(
                ["/bin/bash", _BACKUP_SCRIPT],
                capture_output=True,
                text=True,
                timeout=300,
            )
        if result.returncode == 0:
            st.success("Backup erfolgreich abgeschlossen!", icon=":material/check_circle:")
        else:
            st.error("Backup fehlgeschlagen — siehe Log unten.", icon=":material/error:")

if _os.path.isfile(_BACKUP_LOG):
    with st.expander("📋 Backup-Log (letzte Einträge)"):
        with open(_BACKUP_LOG) as _f:
            _lines = _f.readlines()
        st.code("".join(_lines[-30:]), language=None)
