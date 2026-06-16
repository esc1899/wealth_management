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

# Combined public model list: env-configured models + UI-registered cloud models
# (registry ∪ env), so a model added in the registry below is immediately selectable
# without editing .env. DeepSeek first (cheapest), then OpenRouter, then Claude.
_HAS_ANTHROPIC = bool(config.LLM_API_KEY)
_HAS_OPENROUTER = bool(config.OPENAI_BASE_URL and config.OPENAI_API_KEY)
_HAS_DEEPSEEK = bool(config.DEEPSEEK_API_KEY)
_registry_public = [
    mid for mid, e in app_config.get_model_registry().items()
    if e.get("provider") in app_config.PUBLIC_PROVIDERS
]
_ALL_PUBLIC_MODELS = list(dict.fromkeys(
    config.DEEPSEEK_MODELS + config.OPENAI_MODELS + _CLAUDE_MODELS + _registry_public
))

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
        app_config.get(f"model_public_{agent_key}")
        or app_config.get(f"model_openai_{agent_key}")
        or app_config.get(f"model_claude_{agent_key}")
        or app_config.get("model_public")
        or (_ALL_PUBLIC_MODELS[0] if _ALL_PUBLIC_MODELS else "")
    )
    options = _ALL_PUBLIC_MODELS or ["(keine Modelle konfiguriert)"]
    idx = options.index(saved) if saved in options else 0
    return st.selectbox(label, options=options, index=idx, key=f"_model_public_{agent_key}")

st.markdown(f"**{t('settings.ollama_agents_header')}** 🔒")
col_o1, col_o2, col_o3 = st.columns(3)
with col_o1:
    sel_portfolio = _ollama_sel("portfolio", t("settings.agent_portfolio_chat"))
with col_o2:
    sel_portfolio_story = _ollama_sel("portfolio_story", "Portfolio Story")
with col_o3:
    sel_watchlist_checker = _ollama_sel("watchlist_checker", "Watchlist Checker")

col_o4, col_o5, col_o6 = st.columns([1, 1, 1])
with col_o4:
    sel_portfolio_comment = _ollama_sel("portfolio_comment", "💬 KI-Kommentare")
with col_o5:
    sel_portfolio_robustness = _ollama_sel("portfolio_robustness", "🐻 Portfolio Robustness")
with col_o6:
    sel_rebalance = _ollama_sel("rebalance", f"⚖️ {t('nav.rebalance_chat')}")

_providers = []
if _HAS_ANTHROPIC:
    _providers.append("Anthropic")
if _HAS_DEEPSEEK:
    _providers.append("DeepSeek")
if _HAS_OPENROUTER:
    _providers.append("OpenRouter")
_provider_label = "☁️ Cloud (" + " + ".join(_providers) + ")" if _providers else "☁️ Cloud"

st.markdown(f"**{_provider_label}**")
col_c1, col_c2, col_c3 = st.columns(3)
with col_c1:
    sel_news = _public_sel("news", t("settings.agent_news"))
with col_c2:
    sel_search = _public_sel("search", t("settings.agent_search"))
with col_c3:
    sel_storychecker = _public_sel("storychecker", t("settings.agent_storychecker"))

st.markdown(f"**{_provider_label} Strategy**")
col_s1, col_s2, col_s3 = st.columns(3)
with col_s1:
    sel_structural = _public_sel("structural_scan", t("settings.agent_structural_scan"))
with col_s2:
    sel_consensus = _public_sel("consensus_gap", t("settings.agent_consensus_gap"))
with col_s3:
    sel_fundamental = _public_sel("fundamental_analyzer", t("settings.agent_fundamental"))

col_s4, col_s5, col_s6 = st.columns([1, 1, 1])
with col_s4:
    sel_capital_allocator = _public_sel("capital_allocator", "Capital Allocator")
with col_s5:
    sel_sector_rotation = _public_sel("sector_rotation", t("settings.agent_sector_rotation"))
with col_s6:
    sel_devils_advocate = _public_sel("devils_advocate", "🐻 Devil's Advocate")

if st.button(t("settings.save_models_button"), key="_save_models_btn", use_container_width=False):
    app_config.set("model_ollama_portfolio", sel_portfolio)
    app_config.set("model_ollama_portfolio_story", sel_portfolio_story)
    app_config.set("model_ollama_watchlist_checker", sel_watchlist_checker)
    app_config.set("model_ollama_portfolio_comment", sel_portfolio_comment)
    app_config.set("model_public_news", sel_news)
    app_config.set("model_public_search", sel_search)
    app_config.set("model_public_storychecker", sel_storychecker)
    app_config.set("model_public_structural_scan", sel_structural)
    app_config.set("model_public_consensus_gap", sel_consensus)
    app_config.set("model_public_fundamental_analyzer", sel_fundamental)
    app_config.set("model_public_capital_allocator", sel_capital_allocator)
    app_config.set("model_public_sector_rotation", sel_sector_rotation)
    app_config.set("model_public_devils_advocate", sel_devils_advocate)
    app_config.set("model_ollama_portfolio_robustness", sel_portfolio_robustness)
    app_config.set("model_ollama_rebalance", sel_rebalance)
    st.cache_resource.clear()
    st.success(t("settings.models_saved"))

st.divider()

# ------------------------------------------------------------------
# Section: Model prices
# ------------------------------------------------------------------

st.subheader(t("settings.model_prices_header"))
st.caption(t("settings.model_prices_caption"))

_PROVIDERS = ["claude", "openrouter", "deepseek", app_config.OLLAMA_PROVIDER]

_registry = app_config.get_model_registry()
# Auto-add any configured OPENAI_MODELS not yet in the registry (placeholder price)
for _m in config.OPENAI_MODELS:
    if _m not in _registry:
        _registry[_m] = {"input": 0.0, "output": 0.0, "provider": "openrouter"}

st.caption(t("settings.model_prices_provider_note"))
st.caption(t("settings.model_prices_columns_legend"))

_PROVIDER_GROUP_LABELS = {
    "claude": "☁️ Claude (Anthropic)",
    "openrouter": "☁️ OpenRouter",
    "deepseek": "☁️ DeepSeek",
    app_config.OLLAMA_PROVIDER: f"🔒 {t('settings.model_prices_ollama_label')}",
}

# Group models by their current provider (provider can still be changed per row;
# the model regroups after save).
_grouped: dict[str, list] = {_p: [] for _p in _PROVIDERS}
for _model_id, _entry in _registry.items():
    _p = _entry.get("provider")
    _grouped[_p if _p in _grouped else "openrouter"].append((_model_id, _entry))

_registry_edits: dict = {}
_delete_ids: set = set()


def _render_registry_row(_model_id: str, _entry: dict, *, ollama: bool) -> None:
    if ollama:
        _rc1, _rc2, _rc3, _rc4, _rc5, _rc6 = st.columns([2.0, 0.9, 0.9, 1.2, 1.7, 0.6])
    else:
        _rc1, _rc2, _rc3, _rc4, _rc6 = st.columns([2.0, 0.9, 0.9, 1.2, 0.6])
        _rc5 = None
    _rc1.markdown(f"`{_model_id}`")
    _in = _rc2.number_input(
        t("settings.model_prices_input_label"), value=float(_entry.get("input", 0.0)),
        min_value=0.0, step=0.01, format="%.4f", key=f"_price_in_{_model_id}", label_visibility="collapsed",
    )
    _out = _rc3.number_input(
        t("settings.model_prices_output_label"), value=float(_entry.get("output", 0.0)),
        min_value=0.0, step=0.01, format="%.4f", key=f"_price_out_{_model_id}", label_visibility="collapsed",
    )
    _prov = _rc4.selectbox(
        t("settings.model_prices_provider_label"), options=_PROVIDERS,
        index=_PROVIDERS.index(_entry.get("provider") if _entry.get("provider") in _PROVIDERS else "openrouter"),
        key=f"_price_prov_{_model_id}", label_visibility="collapsed",
    )
    _new = {"input": _in, "output": _out, "provider": _prov}
    if _prov == app_config.OLLAMA_PROVIDER and _rc5 is not None:
        _think = _rc5.checkbox(
            t("settings.model_prices_think_label"), value=bool(_entry.get("think", False)),
            key=f"_price_think_{_model_id}",
        )
        _ctx = _rc5.number_input(
            t("settings.model_prices_numctx_label"), value=int(_entry.get("num_ctx") or 0),
            min_value=0, step=1024, key=f"_price_ctx_{_model_id}",
            help=t("settings.model_prices_numctx_help"),
        )
        _new["think"] = _think
        if _ctx:
            _new["num_ctx"] = int(_ctx)
    if _rc6.checkbox(t("settings.model_prices_delete"), key=f"_price_del_{_model_id}", label_visibility="collapsed"):
        _delete_ids.add(_model_id)
    _registry_edits[_model_id] = _new


for _prov_key in _PROVIDERS:
    _items = _grouped.get(_prov_key) or []
    if not _items:
        continue
    st.markdown(f"**{_PROVIDER_GROUP_LABELS[_prov_key]}**")
    for _model_id, _entry in _items:
        _render_registry_row(_model_id, _entry, ollama=(_prov_key == app_config.OLLAMA_PROVIDER))

# ── Add a new model — dropdown for discoverable models (Ollama + Claude), free text otherwise
_MANUAL = "✏️ " + t("settings.model_prices_manual_entry")
_discoverable: dict[str, str] = {}  # model_id -> provider
for _m in _ollama_models:
    if _m not in _registry:
        _discoverable[_m] = app_config.OLLAMA_PROVIDER
for _m in _CLAUDE_MODELS:
    if _m not in _registry:
        _discoverable.setdefault(_m, "claude")

with st.expander(t("settings.model_prices_add_model")):
    _pick = st.selectbox(
        t("settings.model_prices_pick_model"),
        options=[_MANUAL] + list(_discoverable.keys()),
        key="_new_price_pick",
    )
    _is_manual = _pick == _MANUAL
    if _is_manual:
        _new_model_id = st.text_input(t("settings.model_prices_model_id"), key="_new_price_model_id")
        _default_prov_idx = 1  # openrouter
    else:
        _new_model_id = _pick
        st.caption(f"`{_pick}`")
        _default_prov_idx = _PROVIDERS.index(_discoverable[_pick])
    _nc1, _nc2, _nc3 = st.columns([1, 1, 1])
    _new_price_in = _nc1.number_input(
        t("settings.model_prices_input_label"), min_value=0.0, step=0.01, format="%.4f", key="_new_price_in"
    )
    _new_price_out = _nc2.number_input(
        t("settings.model_prices_output_label"), min_value=0.0, step=0.01, format="%.4f", key="_new_price_out"
    )
    _new_provider = _nc3.selectbox(
        t("settings.model_prices_provider_label"), options=_PROVIDERS, index=_default_prov_idx, key="_new_price_provider"
    )

st.caption(t("settings.model_prices_delete_hint"))
if _delete_ids:
    st.warning(
        t("settings.model_prices_delete_preview").format(models=", ".join(sorted(_delete_ids))),
        icon=":material/delete:",
    )

if st.button(t("settings.model_prices_save"), key="_save_prices_btn"):
    _saved = {mid: e for mid, e in _registry_edits.items() if mid not in _delete_ids}
    if _new_model_id.strip():
        _saved[_new_model_id.strip()] = {
            "input": _new_price_in, "output": _new_price_out, "provider": _new_provider,
        }
    # Persist deletions so seeded defaults stay gone; re-added ids drop off the list.
    _deleted = (set(app_config.get_deleted_models()) | _delete_ids) - set(_saved.keys())
    app_config.set_deleted_models(list(_deleted))
    app_config.set_model_prices(_saved)
    st.cache_resource.clear()
    st.toast(t("settings.model_prices_saved"), icon="✅")
    st.rerun()

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
