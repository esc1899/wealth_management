"""
Settings — manage and AI-generate skills, model selection, empfehlung labels.
"""

import asyncio
import logging

import streamlit as st

logger = logging.getLogger(__name__)

from config import config
from core.health import Severity, check_ollama_connectivity, run_static_checks
from core.i18n import SUPPORTED_LANGUAGES, current_language, set_language, t
from core.llm.local import OllamaProvider
from core.llm.base import Message, Role
from core.storage.models import Skill, ScheduledJob
from state import get_agent_scheduler, get_app_config_repo, get_scheduled_jobs_repo, get_skills_repo

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

_CLAUDE_MODELS = config.CLAUDE_MODELS

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

st.markdown(f"**{t('settings.ollama_agents_header')}** 🔒")
col_o1, col_o2 = st.columns(2)
with col_o1:
    sel_portfolio = _ollama_sel("portfolio", t("settings.agent_portfolio_chat"))
with col_o2:
    sel_rebalance = _ollama_sel("rebalance", t("settings.agent_rebalance"))

st.markdown(f"**{t('settings.claude_agents_header')}** ☁️")
col_c1, col_c2, col_c3 = st.columns(3)
with col_c1:
    sel_news = _claude_sel("news", t("settings.agent_news"))
with col_c2:
    sel_search = _claude_sel("search", t("settings.agent_search"))
with col_c3:
    sel_storychecker = _claude_sel("storychecker", t("settings.agent_storychecker"))

st.markdown(f"**{t('settings.claude_strategy_header')}** ☁️")
col_s1, col_s2, col_s3 = st.columns(3)
with col_s1:
    sel_structural = _claude_sel("structural_scan", t("settings.agent_structural_scan"))
with col_s2:
    sel_consensus = _claude_sel("consensus_gap", t("settings.agent_consensus_gap"))
with col_s3:
    sel_fundamental = _claude_sel("fundamental", t("settings.agent_fundamental"))

if st.button(t("settings.save_models_button"), key="_save_models_btn", use_container_width=False):
    app_config.set("model_ollama_portfolio", sel_portfolio)
    app_config.set("model_ollama_rebalance", sel_rebalance)
    app_config.set("model_claude_news", sel_news)
    app_config.set("model_claude_search", sel_search)
    app_config.set("model_claude_storychecker", sel_storychecker)
    app_config.set("model_claude_structural_scan", sel_structural)
    app_config.set("model_claude_consensus_gap", sel_consensus)
    app_config.set("model_claude_fundamental", sel_fundamental)
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
# Section: Cost alerts
# ------------------------------------------------------------------

st.subheader(t("settings.cost_alert_header"))
st.caption(t("settings.cost_alert_caption"))

_current_alert = app_config.get_cost_alert()
_cal1, _cal2 = st.columns(2)
_alert_daily = _cal1.number_input(
    t("settings.cost_alert_daily_label"),
    value=float(_current_alert.get("daily", 0.0)),
    min_value=0.0,
    step=0.5,
    format="%.2f",
    help=t("settings.cost_alert_disabled"),
    key="_alert_daily",
)
_alert_monthly = _cal2.number_input(
    t("settings.cost_alert_monthly_label"),
    value=float(_current_alert.get("monthly", 0.0)),
    min_value=0.0,
    step=1.0,
    format="%.2f",
    help=t("settings.cost_alert_disabled"),
    key="_alert_monthly",
)

if st.button(t("settings.cost_alert_save"), key="_save_alert_btn"):
    app_config.set_cost_alert(_alert_daily, _alert_monthly)
    st.success(t("settings.cost_alert_saved"))

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
# Section: Scheduled agent jobs
# ------------------------------------------------------------------

_sched_repo = get_scheduled_jobs_repo()
_all_skills_repo = get_skills_repo()
_SCHEDULABLE_AGENTS = {
    "news": t("settings.agent_news"),
    "structural_scan": t("nav.structural_scan"),
    "consensus_gap": t("nav.consensus_gap"),
    "storychecker": t("settings.agent_storychecker"),
    "fundamental": t("settings.agent_fundamental"),
}

st.subheader(t("settings.scheduling_header"))
st.caption(t("settings.scheduling_caption"))

_all_jobs = _sched_repo.get_all()

if not _all_jobs:
    st.info(t("settings.no_scheduled_jobs"))
else:
    _WEEKDAY_NAMES = [
        t("settings.weekday_mon"), t("settings.weekday_tue"), t("settings.weekday_wed"),
        t("settings.weekday_thu"), t("settings.weekday_fri"), t("settings.weekday_sat"),
        t("settings.weekday_sun"),
    ]
    for _job in _all_jobs:
        with st.container(border=True):
            _jc1, _jc2, _jc3, _jc4 = st.columns([4, 1, 1, 1])
            with _jc1:
                _freq_label = t(f"settings.freq_{_job.frequency}")
                if _job.frequency == "weekly" and _job.run_weekday is not None:
                    _freq_label += f" ({_WEEKDAY_NAMES[_job.run_weekday]})"
                elif _job.frequency == "monthly" and _job.run_day:
                    _freq_label += f" ({t('settings.day_of_month')} {_job.run_day})"
                _freq_label += f" {_job.run_hour:02d}:{_job.run_minute:02d}"
                _job_title = _job.agent_name.capitalize()
                if _job.skill_name:
                    _job_title += f" — {_job.skill_name}"
                st.markdown(f"**{_job_title}**")
                st.caption(f"{_freq_label}" + (f" · {t('settings.last_run')}: {_job.last_run.strftime('%d.%m.%Y %H:%M') if _job.last_run else '—'}"))
            with _jc2:
                _new_enabled = st.toggle(
                    t("settings.job_enabled"),
                    value=_job.enabled,
                    key=f"_job_enabled_{_job.id}",
                )
                if _new_enabled != _job.enabled:
                    _sched_repo.set_enabled(_job.id, _new_enabled)
                    get_agent_scheduler().reload_jobs()
                    st.rerun()
            with _jc3:
                if st.button(t("settings.run_now_button"), key=f"_job_run_{_job.id}", type="primary"):
                    get_agent_scheduler().run_job_now(_job.id)
                    st.toast(t("settings.job_started"), icon="▶️")
            with _jc4:
                if st.button(t("settings.delete_button"), key=f"_job_del_{_job.id}", type="secondary"):
                    _sched_repo.delete(_job.id)
                    get_agent_scheduler().reload_jobs()
                    st.rerun()

st.markdown(f"**{t('settings.add_scheduled_job')}**")

_FREQ_OPTIONS = ["daily", "weekly", "monthly"]
_FREQ_LABELS = [t(f"settings.freq_{f}") for f in _FREQ_OPTIONS]
_WEEKDAY_OPTIONS = list(range(7))

# Agent selector outside the form so changing it triggers a rerun and updates skills
_jf_agent_label = st.selectbox(
    t("settings.job_agent_label"),
    options=list(_SCHEDULABLE_AGENTS.keys()),
    format_func=lambda k: _SCHEDULABLE_AGENTS[k],
    key="_jf_agent",
)
_jf_agent_skills = _all_skills_repo.get_by_area(_jf_agent_label)
_jf_needs_skill = _jf_agent_label != "storychecker"

with st.form("add_job_form"):
    if _jf_needs_skill:
        _jf_skill = st.selectbox(
            t("settings.job_skill_label"),
            options=_jf_agent_skills,
            format_func=lambda s: s.name,
            key="_jf_skill",
        )
    else:
        _jf_skill = None
        st.caption(t("settings.storychecker_skill_note"))
    _jf_freq_label = st.selectbox(
        t("settings.job_frequency_label"),
        options=_FREQ_LABELS,
        key="_jf_freq",
    )
    _jf_freq = _FREQ_OPTIONS[_FREQ_LABELS.index(_jf_freq_label)]

    _jf_col1, _jf_col2 = st.columns(2)
    with _jf_col1:
        _jf_hour = st.number_input(t("settings.job_hour_label"), min_value=0, max_value=23, value=8, key="_jf_hour")
    with _jf_col2:
        _jf_minute = st.number_input(t("settings.job_minute_label"), min_value=0, max_value=59, value=0, step=5, key="_jf_minute")

    _jf_weekday = None
    _jf_day = None
    if _jf_freq == "weekly":
        _WEEKDAY_NAMES_FORM = [
            t("settings.weekday_mon"), t("settings.weekday_tue"), t("settings.weekday_wed"),
            t("settings.weekday_thu"), t("settings.weekday_fri"), t("settings.weekday_sat"),
            t("settings.weekday_sun"),
        ]
        _jf_weekday_label = st.selectbox(t("settings.job_weekday_label"), options=_WEEKDAY_NAMES_FORM, key="_jf_weekday")
        _jf_weekday = _WEEKDAY_NAMES_FORM.index(_jf_weekday_label)
    elif _jf_freq == "monthly":
        _jf_day = st.number_input(t("settings.job_day_label"), min_value=1, max_value=28, value=1, key="_jf_day")

    _jf_model_opts = [""] + _CLAUDE_MODELS
    _jf_model = st.selectbox(
        t("settings.job_model_label"),
        options=_jf_model_opts,
        format_func=lambda x: x if x else t("settings.job_model_default"),
        key="_jf_model",
    )

    _jf_submitted = st.form_submit_button(t("settings.save_button"), use_container_width=True)

if _jf_submitted:
    if _jf_needs_skill and not _jf_agent_skills:
        st.error(t("settings.no_agent_skills"))
    else:
        _new_job = ScheduledJob(
            agent_name=_jf_agent_label,
            skill_name=_jf_skill.name if _jf_skill else "",
            skill_prompt=_jf_skill.prompt if _jf_skill else "",
            frequency=_jf_freq,
            run_hour=int(_jf_hour),
            run_minute=int(_jf_minute),
            run_weekday=int(_jf_weekday) if _jf_weekday is not None else None,
            run_day=int(_jf_day) if _jf_day is not None else None,
            model=_jf_model or None,
        )
        _sched_repo.add(_new_job)
        get_agent_scheduler().reload_jobs()
        st.success(t("settings.job_saved"))
        st.rerun()
