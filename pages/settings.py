"""
Settings — manage and AI-generate skills, model selection, empfehlung labels.
"""

import asyncio

import streamlit as st

from config import config
from core.health import Severity, check_ollama_connectivity, run_static_checks
from core.i18n import SUPPORTED_LANGUAGES, current_language, set_language, t
from core.llm.local import OllamaProvider
from core.llm.base import Message, Role
from core.storage.models import Skill
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

skills_repo = get_skills_repo()

# ------------------------------------------------------------------
# Section: Skills list
# ------------------------------------------------------------------

st.subheader(t("settings.skills_header"))

all_skills = skills_repo.get_all()

if not all_skills:
    st.info(t("settings.no_skills"))
else:
    # Group by area
    areas: dict[str, list] = {}
    for skill in all_skills:
        areas.setdefault(skill.area, []).append(skill)

    for area, area_skills in areas.items():
        st.markdown(f"**{t('settings.area_label')}: {area}**")
        for skill in area_skills:
            with st.expander(f"{skill.name}" + (f" — {skill.description}" if skill.description else "")):
                if st.session_state.get("editing_skill_id") == skill.id:
                    # --- Edit form ---
                    with st.form(key=f"edit_form_{skill.id}"):
                        edit_name = st.text_input(t("settings.name_label"), value=skill.name)
                        edit_area = st.text_input(t("settings.area_label_required"), value=skill.area)
                        edit_desc = st.text_input(t("settings.description_label"), value=skill.description or "")
                        edit_prompt = st.text_area(t("settings.prompt_label"), value=skill.prompt, height=180)
                        col_save, col_cancel = st.columns(2)
                        with col_save:
                            submitted = st.form_submit_button(t("settings.save_button"), use_container_width=True)
                        with col_cancel:
                            cancelled = st.form_submit_button(t("settings.cancel_button"), use_container_width=True)
                    if submitted:
                        if not edit_name.strip() or not edit_prompt.strip():
                            st.error(t("settings.name_required_error"))
                        else:
                            updated = skill.model_copy(update={
                                "name": edit_name.strip(),
                                "area": edit_area.strip() or skill.area,
                                "description": edit_desc.strip() or None,
                                "prompt": edit_prompt.strip(),
                            })
                            skills_repo.update(updated)
                            del st.session_state["editing_skill_id"]
                            st.rerun()
                    if cancelled:
                        del st.session_state["editing_skill_id"]
                        st.rerun()
                else:
                    st.markdown(f"**{t('settings.description_prefix')}:** {skill.description or '–'}")
                    st.markdown(f"**{t('settings.prompt_prefix')}:**")
                    st.code(skill.prompt, language=None)
                    col_edit, col_del = st.columns(2)
                    with col_edit:
                        if st.button(t("settings.edit_button"), key=f"edit_{skill.id}", use_container_width=True):
                            st.session_state["editing_skill_id"] = skill.id
                            st.rerun()
                    with col_del:
                        if st.button(t("settings.delete_button"), key=f"del_{skill.id}", type="secondary", use_container_width=True):
                            skills_repo.delete(skill.id)
                            st.success(f"{t('settings.skill_deleted')} '{skill.name}'")
                            st.rerun()

st.divider()

# ------------------------------------------------------------------
# Section: Add skill manually
# ------------------------------------------------------------------

st.subheader(t("settings.add_skill"))

AREA_OPTIONS = ["research", "stock_search", "rebalancing", "portfolio_analysis", t("settings.other_area")]

with st.form("add_skill_form"):
    new_name = st.text_input(t("settings.name_label"), placeholder=t("settings.name_placeholder"))
    area_choice = st.selectbox(t("settings.area_label_required"), AREA_OPTIONS)
    custom_area = ""
    if area_choice == t("settings.other_area"):
        custom_area = st.text_input(t("settings.custom_area_label"), placeholder=t("settings.custom_area_placeholder"))
    new_description = st.text_input(t("settings.description_label"), placeholder=t("settings.description_placeholder"))
    new_prompt = st.text_area(t("settings.prompt_label"), placeholder=t("settings.prompt_placeholder"), height=180)
    save_btn = st.form_submit_button(t("settings.save_button"), use_container_width=True)

if save_btn:
    resolved_area = custom_area.strip() if area_choice == t("settings.other_area") else area_choice
    if not new_name.strip():
        st.error(t("settings.name_required_error"))
    elif area_choice == t("settings.other_area") and not resolved_area:
        st.error(t("settings.area_required_error"))
    elif not new_prompt.strip():
        st.error(t("settings.prompt_required_error"))
    else:
        try:
            skill = Skill(
                name=new_name.strip(),
                area=resolved_area,
                description=new_description.strip() or None,
                prompt=new_prompt.strip(),
            )
            skills_repo.add(skill)
            st.success(f"'{skill.name}' {t('settings.skill_saved')}")
            st.rerun()
        except Exception as exc:
            st.error(f"{t('settings.save_error')}: {exc}")

st.divider()

# ------------------------------------------------------------------
# Section: LLM-generated skill
# ------------------------------------------------------------------

st.subheader(t("settings.generate_header"))

gen_description = st.text_input(
    t("settings.generate_description"),
    placeholder=t("settings.generate_description_placeholder"),
    key="gen_desc",
)
gen_area = st.selectbox(t("settings.generate_area"), AREA_OPTIONS[:-1], key="gen_area")

if st.button(t("settings.generate_button"), key="gen_btn"):
    if not gen_description.strip():
        st.error(t("settings.description_required"))
    else:
        with st.spinner(t("settings.generating")):
            try:
                llm = OllamaProvider(host=config.OLLAMA_HOST, model=config.OLLAMA_MODEL)
                user_msg = (
                    f"Erstelle einen Investment-Analyse-Prompt für folgenden Anwendungsfall: "
                    f"{gen_description.strip()}. Bereich: {gen_area}. "
                    f"Antworte NUR mit dem Prompt-Text selbst, ohne Einleitung oder Erklärung."
                )
                generated = asyncio.run(llm.chat([Message(role=Role.USER, content=user_msg)]))
                st.session_state["gen_result"] = generated
            except Exception as exc:
                st.error(f"{t('settings.ai_error')}: {exc}")

if "gen_result" in st.session_state and st.session_state["gen_result"]:
    st.markdown(f"**{t('settings.generated_label')}:**")
    edited_prompt = st.text_area(
        t("settings.generated_edit_label"),
        value=st.session_state["gen_result"],
        height=200,
        key="gen_edit",
    )
    gen_save_name = st.text_input(t("settings.generated_name_label"), key="gen_save_name")
    gen_save_desc = st.text_input(t("settings.generated_desc_label"), key="gen_save_desc")

    if st.button(t("settings.save_generated"), key="gen_save_btn"):
        if not gen_save_name.strip():
            st.error(t("settings.name_required_gen"))
        elif not edited_prompt.strip():
            st.error(t("settings.prompt_empty_error"))
        else:
            try:
                skill = Skill(
                    name=gen_save_name.strip(),
                    area=gen_area,
                    description=gen_save_desc.strip() or None,
                    prompt=edited_prompt.strip(),
                )
                skills_repo.add(skill)
                st.success(f"'{skill.name}' {t('settings.generated_saved')}")
                del st.session_state["gen_result"]
                st.rerun()
            except Exception as exc:
                st.error(f"{t('settings.save_error')}: {exc}")

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

_CLAUDE_MODELS = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
]

# Fetch available Ollama models
import requests as _requests

def _get_ollama_model_list() -> list[str]:
    try:
        url = f"{config.OLLAMA_HOST.rstrip('/')}/api/tags"
        resp = _requests.get(url, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []

_ollama_models = _get_ollama_model_list()
_saved_ollama = app_config.get("model_ollama") or config.OLLAMA_MODEL
_saved_claude = app_config.get("model_claude") or "claude-haiku-4-5-20251001"

if not _ollama_models:
    st.caption(t("settings.ollama_unavailable"))
    _ollama_models = [_saved_ollama] if _saved_ollama else [config.OLLAMA_MODEL]

_ollama_idx = _ollama_models.index(_saved_ollama) if _saved_ollama in _ollama_models else 0
_claude_idx = _CLAUDE_MODELS.index(_saved_claude) if _saved_claude in _CLAUDE_MODELS else 0

col_m1, col_m2 = st.columns(2)
with col_m1:
    sel_ollama = st.selectbox(
        t("settings.ollama_model_label"),
        options=_ollama_models,
        index=_ollama_idx,
        key="_settings_ollama_model",
    )
with col_m2:
    sel_claude = st.selectbox(
        t("settings.claude_model_label"),
        options=_CLAUDE_MODELS,
        index=_claude_idx,
        key="_settings_claude_model",
    )

if st.button(t("settings.save_models_button"), key="_save_models_btn"):
    app_config.set("model_ollama", sel_ollama)
    app_config.set("model_claude", sel_claude)
    st.success(t("settings.models_saved"))

st.divider()

# ------------------------------------------------------------------
# Section: Empfehlung labels
# ------------------------------------------------------------------

st.subheader(t("settings.empfehlung_labels_header"))

_DEFAULT_EMPFEHLUNG = ["Kaufen", "Halten", "Verkaufen", "Beobachten"]
_current_labels: list[str] = app_config.get_json("empfehlung_labels", _DEFAULT_EMPFEHLUNG)

labels_text = st.text_area(
    t("settings.empfehlung_labels_label"),
    value="\n".join(_current_labels),
    height=130,
    help=t("settings.empfehlung_labels_help"),
    key="_settings_empf_labels",
)

if st.button(t("settings.save_labels_button"), key="_save_labels_btn"):
    parsed = [l.strip() for l in labels_text.splitlines() if l.strip()]
    if not parsed:
        st.error(t("settings.labels_empty_error"))
    else:
        app_config.set_json("empfehlung_labels", parsed)
        st.success(t("settings.labels_saved"))
