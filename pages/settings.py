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
from core.llm.router import available_public_models, current_claude_models
from state import get_app_config_repo, get_skills_repo

st.set_page_config(page_title="Einstellungen", page_icon="⚙️", layout="wide")
st.title(t("settings.title"))

# Drei Bereiche (10.10.2026): Generell (Sprache zuerst, Systemzustand, Backup), Lokale LLM
# (Ollama: das eine lokale Modell) und Cloud LLM (Modelle je Agent, Preise). Jeder
# Bereich speichert nur seine eigenen Einstellungen.
tab_generell, tab_lokal, tab_cloud = st.tabs([
    t("settings.tab_generell"), t("settings.tab_lokal"), t("settings.tab_cloud"),
])

with tab_generell:
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
    # Section: Pruefung je Liste (core/pruefung.py)
    # ------------------------------------------------------------------

    from core.pruefung import MOEGLICH, SKILL_BEREICH, auswahl, auswahl_setzen, skills, skills_setzen

    st.subheader(t("settings.pruefung_header"))
    st.markdown(t("settings.pruefung_satz"))
    _cfg = get_app_config_repo()
    _skills_repo = get_skills_repo()
    with st.form("pruefung_auswahl"):
        _neu, _neue_skills = {}, {}
        for _liste in MOEGLICH:
            _neu[_liste] = st.multiselect(
                t(f"settings.pruefung_{_liste}"), options=list(MOEGLICH[_liste]),
                default=list(auswahl(_cfg, _liste)), format_func=lambda a: t(f"kacheln.agent_{a}"),
                key=f"pruefung_{_liste}",
            )
            # Je Check mit Skill-Bereich der Skill; ohne Skills im Bereich gilt der Standard.
            _gewaehlt = skills(_cfg, _liste)
            _neue_skills[_liste] = {}
            _mit_skill = [(c, _skills_repo.get_by_area(SKILL_BEREICH[c]))
                          for c in MOEGLICH[_liste] if c in SKILL_BEREICH]
            _mit_skill = [(c, sk) for c, sk in _mit_skill if sk]
            if _mit_skill:
                _spalten = st.columns(len(_mit_skill))
                for _sp, (_check, _sk) in zip(_spalten, _mit_skill):
                    _namen = [""] + [x.name for x in _sk]
                    _jetzt = _gewaehlt.get(_check, "")
                    _neue_skills[_liste][_check] = _sp.selectbox(
                        t("settings.pruefung_skill").format(check=t(f"kacheln.agent_{_check}")),
                        options=_namen, index=_namen.index(_jetzt) if _jetzt in _namen else 0,
                        format_func=lambda n: n or t("settings.pruefung_skill_standard"),
                        key=f"pruefung_skill_{_liste}_{_check}",
                    )
        # Ab wann ein Titel als stark bewegt gilt: Kachel und Job kurse lesen dieselbe Schwelle.
        from core import bewegung
        _schwelle = st.number_input(t("settings.bewegung_label"), min_value=0.5, max_value=50.0,
                                    value=float(bewegung.schwelle(_cfg)), step=0.5, format="%.1f",
                                    help=t("settings.bewegung_hilfe").format(deckel=bewegung.DECKEL),
                                    key="pruefung_bewegung")
        if st.form_submit_button(t("settings.pruefung_speichern")):
            for _liste, _checks in _neu.items():
                auswahl_setzen(_cfg, _liste, _checks)
                skills_setzen(_cfg, _liste, _neue_skills[_liste])
            bewegung.schwelle_setzen(_cfg, _schwelle)
            st.success(t("settings.pruefung_gespeichert"))

    st.divider()

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
    # Section: Backup
    # ------------------------------------------------------------------

    import os as _os
    import subprocess as _subprocess

    st.subheader("💾 Backup")

    _BACKUP_SCRIPT = _os.path.expanduser("~/scripts/wm_backup.sh")
    # Was das Terminal-Fenster startet: `ops run wealth_management backup`, damit der
    # Lauf im Run-Log von ops-core steht und die Kachel ihn kennt (seit 2026-09-27).
    _BACKUP_STARTER = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
        "scripts", "backup_im_terminal.command",
    )
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
        # Der Button startet das Skript nicht selbst, sondern in einem Terminal-Fenster
        # (seit 2026-09-26). Als Kind dieses Prozesses rechnet macOS den Plattenzugriff
        # dem Homebrew-Python der App zu, und das hat keinen Festplattenvollzugriff --
        # soll es auch nicht, siehe CLAUDE.md. Ueber `open` startet Launch Services das
        # Terminal, das die Freigabe schon hat; es kommt keine neue dazu.
        st.caption(
            "Die Sicherung läuft in einem eigenen Terminal-Fenster: Nur Terminal darf "
            "auf die Platte, die App nicht. Tippen musst du dort nichts."
        )
        if st.button("▶ Jetzt sichern", type="primary", key="_backup_now_btn"):
            result = _subprocess.run(
                ["/usr/bin/open", "-a", "Terminal", _BACKUP_STARTER],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                st.info(
                    "Sicherung im Terminal-Fenster gestartet. Wenn dort „completed "
                    "successfully“ steht, ist sie fertig – das Log unten zeigt es nach "
                    "dem Neuladen der Seite.",
                    icon=":material/terminal:",
                )
            else:
                st.error(
                    f"Terminal ließ sich nicht öffnen: {result.stderr.strip() or result.returncode}",
                    icon=":material/error:",
                )

    if _os.path.isfile(_BACKUP_LOG):
        with st.expander("📋 Backup-Log (letzte Einträge)"):
            with open(_BACKUP_LOG) as _f:
                _lines = _f.readlines()
            st.code("".join(_lines[-30:]), language=None)

with tab_lokal:
    # ------------------------------------------------------------------
    # Section: Model selection
    # ------------------------------------------------------------------

    app_config = get_app_config_repo()

    st.subheader(t("settings.model_selection_header"))

    # Auswahl: die jeweils aktuellen Claude-Modelle, gefiltert auf das, was der Account laut
    # Models-API wirklich anbietet. Die API-Liste selbst ist als Auswahl untauglich — sie
    # enthält die gesamte Claude-Historie inkl. abgelöster Versionen.
    # Welche "aktuell" sind, sagt seit 2026-09-27 der Modellkatalog des Hauses
    # (~/.ops-core/katalog.toml, auf der Home-Ops-Seite aufgefrischt: je Familie das neueste);
    # ohne Katalog die Liste aus der Konfiguration (constants.py / CLAUDE_MODELS).
    from core import house_models as _house

    @st.cache_resource(ttl=3600)
    def _available_claude_models() -> list[str]:
        """Die Models-API — gecacht, sie ändert sich selten und kostet einen Aufruf."""
        return _fetch_claude_models(config.LLM_API_KEY, config.LLM_BASE_URL)

    # Der Katalog wird bei jedem Laden gelesen (eine kleine Datei): Ein Klick auf
    # "aktualisieren" auf der Home-Ops-Seite ist beim nächsten Neuladen hier.
    _CATALOG_CURRENT = _house.load_catalog(_house.CLAUDE).get("current") or []
    _CONFIGURED_CLAUDE = _CATALOG_CURRENT or config.CLAUDE_MODELS
    _CLAUDE_MODELS = (current_claude_models(_CONFIGURED_CLAUDE, _available_claude_models())
                      if config.LLM_API_KEY else list(_CONFIGURED_CLAUDE))

    # Combined public model list: env-configured models + UI-registered cloud models
    # (registry ∪ env), so a model added in the registry below is immediately selectable
    # without editing .env. DeepSeek first (cheapest), then OpenRouter, then Claude.
    _HAS_ANTHROPIC = bool(config.LLM_API_KEY)
    _HAS_OPENROUTER = bool(config.OPENAI_BASE_URL and config.OPENAI_API_KEY)
    _HAS_DEEPSEEK = bool(config.DEEPSEEK_API_KEY)
    # Only offer models whose provider is actually configured — otherwise DeepSeek's
    # non-empty default leaks into the list and a pick 404s against an Anthropic proxy.
    _ALL_PUBLIC_MODELS = available_public_models(
        claude_models=_CLAUDE_MODELS,
        openrouter_models=config.OPENAI_MODELS,
        deepseek_models=config.DEEPSEEK_MODELS,
        # Claude-Modelle aus der Preisliste nur, wenn der Katalog sie als aktuell führt
        # (2026-09-27): Die Preisliste behält abgelöste Modelle, damit alte Aufrufe ihren
        # Preis haben -- zur Wahl stehen sollen sie nicht. Ein gespeichertes bleibt über
        # `_with_saved` sichtbar, mit Hinweis. Ohne Katalog wie bisher.
        registry={
            mid: e.get("provider")
            for mid, e in app_config.get_model_registry().items()
            if e.get("provider") in app_config.PUBLIC_PROVIDERS
            and not (e.get("provider") == "claude" and _CATALOG_CURRENT
                     and mid not in _CLAUDE_MODELS)
        },
        has_anthropic=_HAS_ANTHROPIC,
        has_openrouter=_HAS_OPENROUTER,
        has_deepseek=_HAS_DEEPSEEK,
    )

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

    # Haus-Standard (2026-09-22): "home" ist keine Modell-ID, sondern ein Verweis
    # auf ~/.ops-core/modelle.toml. Steht ein Agent darauf, ändert Erik ihn auf der
    # Home-Ops-Seite zusammen mit allen anderen, die folgen -- ohne Neustart.
    # Angezeigt wird, worauf er gerade zeigt; gespeichert wird "home".

    _HOUSE = _house.load()
    _HOUSE_LOCAL = (_HOUSE.get(_house.OLLAMA) or {}).get("modell")
    _HOUSE_CLOUD = (_HOUSE.get(_house.CLAUDE) or {}).get("modell") \
        or (_HOUSE.get(_house.OPENROUTER) or {}).get("modell")


    # "Immer das neueste" je Klasse (2026-09-29): gespeichert wird "neuestes:sonnet",
    # aufgelöst beim Aufruf aus dem Katalog (core.llm.router.resolve_house_model).
    # Angeboten nur, was der Katalog als aktuell führt – und nur mit Anthropic-Schlüssel.
    _NEWEST = {f: _house.newest(f) for f in _house.FAMILIES} if _HAS_ANTHROPIC else {}
    _NEWEST_OPTIONS = [_house.newest_setting(f) for f, m in _NEWEST.items() if m]
    _CATALOG_NAMES = _house.load_catalog(_house.CLAUDE).get("names") or {}


    def _model_label(model: str, house: str | None) -> str:
        if _house.is_newest(model):
            family = model[len(_house.NEWEST):]
            return t("settings.newest_of_family").format(
                family=family.capitalize(),
                model=_CATALOG_NAMES.get(_NEWEST.get(family), _NEWEST.get(family)) or "–")
        if model != _house.HOME:
            return _stale_label(model)
        return (t("settings.house_default_is").format(model=house) if house
                else t("settings.house_default_missing"))


    def _stale_label(model: str) -> str:
        """Ein Claude-Modell, das der Katalog nicht mehr als aktuell führt, bleibt wählbar
        (``_with_saved``), sagt aber, dass es ein neueres gibt — sonst fällt ein Altmodell
        erst Wochen später in der Kostenstatistik auf."""
        if _CATALOG_CURRENT and model.startswith("claude-") and model not in _CATALOG_CURRENT:
            return t("settings.model_not_current").format(model=model)
        return model


    def _ollama_sel(agent_key: str, label: str, saved: str = "") -> str:
        saved = saved or app_config.get(f"model_ollama_{agent_key}") or app_config.get("model_ollama") or config.OLLAMA_MODEL
        options = ([_house.HOME] if _HOUSE_LOCAL else []) + _ollama_models
        options = _with_saved(options, saved)
        idx = options.index(saved) if saved in options else 0
        return st.selectbox(label, options=options, index=idx,
                            format_func=lambda m: _model_label(m, _HOUSE_LOCAL),
                            key=f"_model_ollama_{agent_key}")

    def _with_saved(options: list[str], saved: str) -> list[str]:
        """Ein gespeichertes, nicht mehr gelistetes Modell bleibt in der Auswahl sichtbar.

        Sonst zeigt das Dropdown stillschweigend Option 0, während in der DB weiter das alte
        Modell steht — der Agent läuft dann anders, als die Seite behauptet.
        """
        return options if not saved or saved in options else options + [saved]

    def _claude_sel(agent_key: str, label: str) -> str:
        saved = app_config.get(f"model_claude_{agent_key}") or app_config.get("model_claude") or (_CLAUDE_MODELS[0] if _CLAUDE_MODELS else "")
        options = _with_saved(_CLAUDE_MODELS, saved)
        idx = options.index(saved) if saved in options else 0
        return st.selectbox(label, options=options, index=idx, format_func=_stale_label,
                            key=f"_model_claude_{agent_key}")

    def _public_sel(agent_key: str, label: str, saved: str = "") -> str:
        saved = saved or (
            app_config.get(f"model_public_{agent_key}")
            or app_config.get(f"model_openai_{agent_key}")
            or app_config.get(f"model_claude_{agent_key}")
            or app_config.get("model_public")
            or (_ALL_PUBLIC_MODELS[0] if _ALL_PUBLIC_MODELS else "")
        )
        options = ([_house.HOME] if _HOUSE_CLOUD else []) + _NEWEST_OPTIONS + _ALL_PUBLIC_MODELS
        options = _with_saved(options, saved) or ["(keine Modelle konfiguriert)"]
        idx = options.index(saved) if saved in options else 0
        return st.selectbox(label, options=options, index=idx,
                            format_func=lambda m: _model_label(m, _HOUSE_CLOUD),
                            key=f"_model_public_{agent_key}")

    # Ein lokales Modell fuer alle (11.10.2026), wie die Bereiche bei der Cloud.
    from core.pruefung import lokales_modell, lokales_modell_setzen

    st.markdown(f"**{t('settings.ollama_agents_header')}** 🔒")
    st.caption(t("settings.lokal_satz"))
    sel_lokal = _ollama_sel("alle", t("settings.lokal_label"),
                            saved=lokales_modell(app_config, config.OLLAMA_MODEL))

    if st.button(t("settings.save_models_button"), key="_save_models_lokal_btn", width="content"):
        lokales_modell_setzen(app_config, sel_lokal)
        st.cache_resource.clear()
        st.success(t("settings.models_saved"))


with tab_cloud:
    _providers = []
    if _HAS_ANTHROPIC:
        _providers.append("Anthropic")
    if _HAS_DEEPSEEK:
        _providers.append("DeepSeek")
    if _HAS_OPENROUTER:
        _providers.append("OpenRouter")
    _provider_label = "☁️ Cloud (" + " + ".join(_providers) + ")" if _providers else "☁️ Cloud"

    # Ein Modell je Bereich (11.10.2026): Depot, Watchlist, Research -- nach Datengrenze, wie
    # Lotsee es schneiden wuerde (core/pruefung.py::BEREICHE).
    from core.pruefung import BEREICHE, modell as _modell_bereich, modell_setzen

    st.markdown(f"**{_provider_label}**")
    st.caption(t("settings.bereiche_satz"))
    _wahl = {}
    for _spalte, _bereich in zip(st.columns(len(BEREICHE)), BEREICHE):
        with _spalte:
            _wahl[_bereich] = _public_sel(f"bereich_{_bereich}", t(f"settings.bereich_{_bereich}"),
                                          saved=_modell_bereich(app_config, _bereich))
            st.caption(t(f"settings.bereich_{_bereich}_wer"))

    if st.button(t("settings.save_models_button"), key="_save_models_cloud_btn", width="content"):
        for _bereich, _m in _wahl.items():
            modell_setzen(app_config, _bereich, _m)
        st.cache_resource.clear()
        st.success(t("settings.models_saved"))

    st.divider()

    # ------------------------------------------------------------------
    # Section: Model prices
    # ------------------------------------------------------------------

    st.subheader(t("settings.model_prices_header"))
    st.caption(t("settings.model_prices_caption"))

    _PROVIDERS = ["claude", "openrouter", "deepseek", app_config.OLLAMA_PROVIDER]

    # Registry + configured OPENAI_MODELS (placeholder price), honouring the deleted list
    # so a model removed in the UI does not reappear from .env on reload.
    _registry = app_config.get_registry_with_configured(config.OPENAI_MODELS)

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
        if _prov_key == "claude" and _CATALOG_CURRENT:
            st.caption(t("settings.model_prices_from_catalog"))
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

