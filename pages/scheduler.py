"""
Scheduler — manage recurring agent jobs and view run history.
"""

import streamlit as st

from config import config
from core.constants import CLAUDE_MODELS_DEFAULT_LIST
from core.i18n import t
from core.llm.claude import fetch_available_models as _fetch_claude_models
from core.storage.models import ScheduledJob
from state import (
    get_agent_scheduler,
    get_scheduled_jobs_repo,
    get_scheduled_job_runs_repo,
    get_skills_repo,
    get_monthly_digest_repo,
    get_yearly_digest_repo,
)

st.set_page_config(page_title="Scheduler", page_icon="⏱️", layout="wide")
st.title("⏱️ Scheduler")
st.caption(t("settings.scheduling_caption"))

# ------------------------------------------------------------------
# Model list (same pattern as settings.py)
# ------------------------------------------------------------------

@st.cache_resource(ttl=3600)
def _get_claude_model_list() -> list[str]:
    if not config.LLM_API_KEY:
        return config.CLAUDE_MODELS
    models = _fetch_claude_models(config.LLM_API_KEY, config.LLM_BASE_URL)
    return models if models else config.CLAUDE_MODELS


_CLAUDE_MODELS = _get_claude_model_list()

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

_sched_repo = get_scheduled_jobs_repo()
_runs_repo = get_scheduled_job_runs_repo()

# Auto-seed system jobs on first page load if they don't exist yet.
_all_jobs_for_seed = _sched_repo.get_all()
if not any(j.agent_name == "monthly_digest" for j in _all_jobs_for_seed):
    _seed_job = ScheduledJob(
        agent_name="monthly_digest",
        skill_name="Monatsdigest",
        skill_prompt="",
        frequency="monthly",
        run_hour=6,
        run_minute=0,
        run_day=1,  # 1st of month → generates previous month's digest
        enabled=True,
    )
    _sched_repo.add(_seed_job)
    get_agent_scheduler().reload_jobs()

if not any(j.agent_name == "yearly_digest" for j in _all_jobs_for_seed):
    _seed_yearly = ScheduledJob(
        agent_name="yearly_digest",
        skill_name="Jahresdigest",
        skill_prompt="",
        frequency="yearly",
        run_hour=6,
        run_minute=0,
        run_month=1,  # January
        run_day=1,    # 1st → generates previous year's digest
        enabled=True,
    )
    _sched_repo.add(_seed_yearly)
    get_agent_scheduler().reload_jobs()

if not any(j.agent_name == "wealth_snapshot" for j in _all_jobs_for_seed):
    _seed_snapshot = ScheduledJob(
        agent_name="wealth_snapshot",
        skill_name="Vermögens-Snapshot",
        skill_prompt="",
        frequency="daily",
        run_hour=20,
        run_minute=0,
        enabled=True,
    )
    _sched_repo.add(_seed_snapshot)
    get_agent_scheduler().reload_jobs()

_SCHEDULABLE_AGENTS = {
    "news": t("settings.agent_news"),
    "structural_scan": t("nav.structural_scan"),
    "consensus_gap": t("nav.consensus_gap"),
    "storychecker": t("settings.agent_storychecker"),
    "fundamental": t("settings.agent_fundamental"),
}

# System jobs are auto-seeded and shown as read-only (no delete).
_SYSTEM_AGENT_NAMES = {"monthly_digest", "yearly_digest", "wealth_snapshot"}

_SKILL_CAPABLE_AGENTS = {
    "news": "news",
    "structural_scan": "structural_scan",
    "consensus_gap": "consensus_gap",
    "fundamental": "fundamental",
}

_WEEKDAY_NAMES = [
    t("settings.weekday_mon"), t("settings.weekday_tue"), t("settings.weekday_wed"),
    t("settings.weekday_thu"), t("settings.weekday_fri"), t("settings.weekday_sat"),
    t("settings.weekday_sun"),
]

_STATUS_ICONS = {"success": "✅", "failed": "❌", "running": "⏳"}
_SOURCE_LABELS = {"scheduled": "Geplant", "manual": "Manuell", "catchup": "Nachgeholt"}

# ------------------------------------------------------------------
# Existing jobs
# ------------------------------------------------------------------

_all_jobs = _sched_repo.get_all()

if not _all_jobs:
    st.info(t("settings.no_scheduled_jobs"))
else:
    for _job in _all_jobs:
        _is_system = _job.agent_name in _SYSTEM_AGENT_NAMES
        with st.container(border=True):
            _jc1, _jc2, _jc3, _jc4 = st.columns([4, 1, 1, 1])
            with _jc1:
                _freq_label = t(f"settings.freq_{_job.frequency}")
                if _job.frequency == "weekly" and _job.run_weekday is not None:
                    _freq_label += f" ({_WEEKDAY_NAMES[_job.run_weekday]})"
                elif _job.frequency == "monthly" and _job.run_day:
                    _freq_label += f" ({t('settings.day_of_month')} {_job.run_day})"
                elif _job.frequency == "yearly":
                    _m = _job.run_month or 1
                    _d = _job.run_day or 1
                    _freq_label += f" ({_d:02d}.{_m:02d}.)"
                _freq_label += f" {_job.run_hour:02d}:{_job.run_minute:02d}"
                _agent_label = _SCHEDULABLE_AGENTS.get(_job.agent_name, "")
                if _agent_label and _job.skill_name and _job.skill_name != _agent_label:
                    _job_title = f"{_agent_label} · {_job.skill_name}"
                else:
                    _job_title = _job.skill_name or _agent_label or _job.agent_name.capitalize()
                if _is_system:
                    _job_title += " ⚙️"
                st.markdown(f"**{_job_title}**")
                st.caption(
                    f"{_freq_label}"
                    + (f" · {t('settings.last_run')}: {_job.last_run.strftime('%d.%m.%Y %H:%M') if _job.last_run else '—'}")
                    + (" · System-Job" if _is_system else "")
                )
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
                if _is_system:
                    st.write("")  # no delete for system jobs
                elif st.button(t("settings.delete_button"), key=f"_job_del_{_job.id}", type="secondary"):
                    _sched_repo.delete(_job.id)
                    get_agent_scheduler().reload_jobs()
                    st.rerun()

            # Run history
            _runs = _runs_repo.get_for_job(_job.id, limit=10)
            if _runs:
                with st.expander(f"▼ Ausführungshistorie ({len(_runs)} Einträge)", expanded=False):
                    for _run in _runs:
                        _icon = _STATUS_ICONS.get(_run.status, "⚪")
                        _src = _SOURCE_LABELS.get(_run.source, _run.source)
                        _start_str = _run.started_at.strftime("%d.%m.%Y %H:%M")
                        if _run.completed_at and _run.started_at:
                            _dur = int((_run.completed_at - _run.started_at).total_seconds())
                            _dur_str = f"{_dur}s"
                        else:
                            _dur_str = "—"
                        _line = f"{_icon} **{_start_str}** · {_src} · {_dur_str}"
                        if _run.error_msg:
                            st.markdown(_line)
                            st.caption(f"Fehler: {_run.error_msg}")
                        else:
                            st.markdown(_line)

st.divider()

# ------------------------------------------------------------------
# Add new job
# ------------------------------------------------------------------

st.subheader(t("settings.add_scheduled_job"))

_FREQ_OPTIONS = ["daily", "weekly", "monthly", "yearly"]
_FREQ_LABELS = [t(f"settings.freq_{f}") for f in _FREQ_OPTIONS]

if "_sched_new_agent" not in st.session_state:
    st.session_state["_sched_new_agent"] = list(_SCHEDULABLE_AGENTS.keys())[0]

_jf_agent_label = st.selectbox(
    t("settings.job_agent_label"),
    options=list(_SCHEDULABLE_AGENTS.keys()),
    format_func=lambda k: _SCHEDULABLE_AGENTS[k],
    key="_sched_new_agent",
)

if _jf_agent_label in _SKILL_CAPABLE_AGENTS:
    _skills_repo = get_skills_repo()
    _skill_area = _SKILL_CAPABLE_AGENTS[_jf_agent_label]
    _available_skills = _skills_repo.get_by_area(_skill_area)

    if _available_skills:
        _skill_options = [None] + _available_skills
        _sel_skill = st.selectbox(
            "Skill",
            options=_skill_options,
            format_func=lambda s: "— kein Skill —" if s is None else f"{s.name} — {s.description or ''}",
            key="_sched_new_skill",
        )
        st.session_state["_sched_new_skill_id"] = _sel_skill.id if _sel_skill else None
    else:
        st.info(f"Keine Skills für {_SCHEDULABLE_AGENTS[_jf_agent_label]} konfiguriert")
        st.session_state["_sched_new_skill_id"] = None
else:
    st.session_state["_sched_new_skill_id"] = None

with st.form("add_job_form"):
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
    _jf_month = None
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
    elif _jf_freq == "yearly":
        _jf_ycol1, _jf_ycol2 = st.columns(2)
        with _jf_ycol1:
            _jf_month = st.number_input("Monat", min_value=1, max_value=12, value=1, key="_jf_run_month")
        with _jf_ycol2:
            _jf_day = st.number_input(t("settings.job_day_label"), min_value=1, max_value=28, value=1, key="_jf_day_yearly")

    _jf_model_opts = [""] + _CLAUDE_MODELS
    _jf_model = st.selectbox(
        t("settings.job_model_label"),
        options=_jf_model_opts,
        format_func=lambda x: x if x else t("settings.job_model_default"),
        key="_jf_model",
    )

    _jf_submitted = st.form_submit_button(t("settings.save_button"), use_container_width=True)

if _jf_submitted:
    _agent_key = st.session_state.get("_sched_new_agent", list(_SCHEDULABLE_AGENTS.keys())[0])
    _skill_id = st.session_state.get("_sched_new_skill_id")

    skill_name, skill_prompt = "", ""
    if _skill_id:
        _skill = get_skills_repo().get(_skill_id)
        if _skill:
            skill_name, skill_prompt = _skill.name, _skill.prompt

    _new_job = ScheduledJob(
        agent_name=_agent_key,
        skill_name=skill_name,
        skill_prompt=skill_prompt,
        frequency=_jf_freq,
        run_hour=int(_jf_hour),
        run_minute=int(_jf_minute),
        run_weekday=int(_jf_weekday) if _jf_weekday is not None else None,
        run_day=int(_jf_day) if _jf_day is not None else None,
        run_month=int(_jf_month) if _jf_month is not None else None,
        model=_jf_model or None,
    )
    _sched_repo.add(_new_job)
    get_agent_scheduler().reload_jobs()
    st.success(t("settings.job_saved"))
    st.rerun()
