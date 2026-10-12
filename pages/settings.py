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
from state import get_app_config_repo, get_skills_repo, get_usage_repo

st.set_page_config(page_title="Einstellungen", page_icon="⚙️", layout="wide")
st.title(t("settings.title"))

# Drei Bereiche nach Bedeutung, nicht nach Technik (12.10.2026): Pruefung (was geprueft wird und
# mit welchem Modell), System (Sprache, Zustand, Sicherung) und Preise (nur zum Nachlesen, aus
# core/preise.py). Jeder Bereich speichert nur seine eigenen Einstellungen.
tab_pruefung, tab_system, tab_preise = st.tabs([
    t("settings.tab_pruefung"), t("settings.tab_system"), t("settings.tab_preise"),
])

with tab_pruefung:
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

    # Zur Wahl: OpenRouter-Modelle aus der Konfiguration (OPENAI_MODELS), dann die aktuellen
    # Claude-Modelle -- nur von Anbietern mit Schluessel, sonst laeuft eine Wahl ins Leere.
    # Seit 12.10.2026 gibt es keine Registry mehr, die weitere Modelle wählbar machte.
    _HAS_ANTHROPIC = bool(config.LLM_API_KEY)
    _HAS_OPENROUTER = bool(config.OPENAI_BASE_URL and config.OPENAI_API_KEY)
    _ALL_PUBLIC_MODELS = available_public_models(
        claude_models=_CLAUDE_MODELS,
        openrouter_models=config.OPENAI_MODELS,
        has_anthropic=_HAS_ANTHROPIC,
        has_openrouter=_HAS_OPENROUTER,
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

    _providers = []
    if _HAS_ANTHROPIC:
        _providers.append("Anthropic")
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

    # Ein Knopf fuer beide: lokal und Cloud stehen auf einer Seite und werden zusammen gewaehlt.
    if st.button(t("settings.save_models_button"), key="_save_models_btn", width="content"):
        lokales_modell_setzen(app_config, sel_lokal)
        for _bereich, _m in _wahl.items():
            modell_setzen(app_config, _bereich, _m)
        st.cache_resource.clear()
        st.success(t("settings.models_saved"))

with tab_system:
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

with tab_preise:
    # ------------------------------------------------------------------
    # Section: Preise -- nur zum Nachlesen (core/preise.py, seit 12.10.2026)
    # ------------------------------------------------------------------

    from core import preise as _preise

    st.subheader(t("settings.preise_header"))
    st.markdown(t("settings.preise_satz"))

    _katalog = _house.load_catalog(_house.CLAUDE)
    _liste = _preise.preisliste(app_config, katalog=_katalog)
    # Gezeigt wird, was zur Wahl steht oder je gerufen wurde -- nicht der ganze Katalog.
    try:
        _benutzt = get_usage_repo().models()
    except Exception:
        _benutzt = []
    _modelle = list(dict.fromkeys([*_ALL_PUBLIC_MODELS, *_benutzt]))
    _zeilen = []
    for _m in _modelle:
        _p = _preise.preis(_m, _liste)
        _anb = _preise.anbieter(_m)
        _zeilen.append({
            t("settings.preise_modell"): _m,
            t("settings.preise_anbieter"): {"claude": "Anthropic", "openrouter": "OpenRouter", "ollama": "Ollama 🔒",
                                            "deepseek": "DeepSeek (direkt, alt)"}[_anb],
            t("settings.preise_eingabe"): None if _p is None else _p["input"],
            t("settings.preise_ausgabe"): None if _p is None else _p["output"],
            t("settings.preise_quelle"): (t("settings.preise_offen") if _p is None
                                          else t(f"settings.preise_quelle_{_p.get('quelle', 'lokal')}")),
        })
    if _zeilen:
        st.dataframe(_zeilen, hide_index=True, width="stretch",
                     column_config={
                         t("settings.preise_eingabe"): st.column_config.NumberColumn(format="$%.2f"),
                         t("settings.preise_ausgabe"): st.column_config.NumberColumn(format="$%.2f"),
                     })
    _stand_or = app_config.get(_preise.OPENROUTER_STAND)
    st.caption(t("settings.preise_stand").format(
        katalog=_katalog.get("stand") or "–", openrouter=_stand_or or "–"))
