"""
Rebalance Chat — conversational portfolio analysis using local Ollama LLM.
"""

import asyncio
from datetime import datetime, timezone

import streamlit as st

from config import config
from core.health import is_local_url
from core.i18n import t
from state import get_agent_scheduler, get_rebalance_agent, get_rebalance_repo, get_scheduled_jobs_repo, get_skills_repo

st.set_page_config(page_title="Invest / Rebalance", page_icon="⚖️", layout="wide")
st.title(f"⚖️ {t('rebalance_chat.title')}")
st.caption(t("rebalance_chat.subtitle"))

agent = get_rebalance_agent()

if is_local_url(config.OLLAMA_HOST):
    st.info(t("rebalance_chat.private_notice").format(model=agent.model), icon="🔒")
else:
    st.warning(t("rebalance_chat.remote_notice").format(host=config.OLLAMA_HOST, model=agent.model), icon="⚠️")
repo = get_rebalance_repo()

# ------------------------------------------------------------------
# Agent freshness check
# ------------------------------------------------------------------

_STALE_DAYS = {"daily": 2, "weekly": 10, "monthly": 35}
_RELEVANT_AGENTS = {"consensus_gap", "structural_scan", "news"}

_all_sched_jobs = get_scheduled_jobs_repo().get_all()
_relevant_jobs = [j for j in _all_sched_jobs if j.agent_name in _RELEVANT_AGENTS]

if _relevant_jobs:
    _now = datetime.now(timezone.utc).replace(tzinfo=None)
    _stale_jobs = []
    for _j in _relevant_jobs:
        if _j.last_run is None:
            _stale_jobs.append(_j)
        else:
            _age_days = (_now - _j.last_run).total_seconds() / 86400
            if _age_days > _STALE_DAYS.get(_j.frequency, 10):
                _stale_jobs.append(_j)

    if _stale_jobs:
        with st.expander(f"⚠️ {t('rebalance_chat.freshness_header')} ({len(_stale_jobs)})", expanded=True):
            st.caption(t("rebalance_chat.freshness_caption"))
            for _j in _stale_jobs:
                _fc1, _fc2 = st.columns([4, 1])
                with _fc1:
                    _last = _j.last_run.strftime("%d.%m.%Y %H:%M") if _j.last_run else t("rebalance_chat.freshness_never")
                    st.markdown(f"🔴 **{_j.agent_name}** — {_j.skill_name}  \n{t('settings.last_run')}: {_last}")
                with _fc2:
                    if st.button(t("rebalance_chat.freshness_run"), key=f"_rb_run_{_j.id}", type="primary"):
                        get_agent_scheduler().run_job_now(_j.id)
                        st.toast(f"▶️ {_j.agent_name} gestartet", icon="▶️")

if "rb_session_id" not in st.session_state:
    st.session_state.rb_session_id = None

# Auto-restore the most recent analysis so navigating away and back doesn't drop the view.
if st.session_state.rb_session_id is None:
    _latest = repo.list_sessions(limit=1)
    if _latest:
        st.session_state.rb_session_id = _latest[0].id


def _session_label(s) -> str:
    """Short list label — prefer the user's request text over the (often generic) strategy name."""
    raw = (s.first_message or "").strip() or s.skill_name
    return raw if len(raw) <= 60 else raw[:60].rstrip() + "…"


# ------------------------------------------------------------------
# Layout: left sidebar | right chat
# ------------------------------------------------------------------

col_sidebar, col_chat = st.columns([1, 2])

# ------------------------------------------------------------------
# Left: new session form + past sessions
# ------------------------------------------------------------------

with col_sidebar:
    st.subheader(t("rebalance_chat.new_session"))

    rebalance_skills = get_skills_repo().get_by_area("rebalance")
    _NEUTRAL_NAME = t("rebalance_chat.neutral_label")

    with st.form("new_rebalance_form"):
        if rebalance_skills:
            skill_names = [s.name for s in rebalance_skills]
            _skill_map = {s.name: s for s in rebalance_skills}
            skill_choice = st.selectbox(t("rebalance_chat.skill_label"), skill_names)
        else:
            # No strategy lens configured — run a neutral review instead of blocking.
            st.caption(t("rebalance_chat.neutral_caption"))
            skill_choice = None
            _skill_map = {}

        context_input = st.text_input(
            t("rebalance_chat.context_label"),
            placeholder=t("rebalance_chat.context_placeholder"),
        ).strip()

        submitted = st.form_submit_button(
            t("rebalance_chat.start_button"), use_container_width=True
        )

    if submitted:
        if skill_choice:
            selected_name = _skill_map[skill_choice].name
            selected_prompt = _skill_map[skill_choice].prompt
        else:
            selected_name = _NEUTRAL_NAME
            selected_prompt = ""
        _rb_error = None
        with st.spinner(t("rebalance_chat.thinking")):
            try:
                session, _ = asyncio.run(
                    agent.start_session(
                        skill_name=selected_name,
                        skill_prompt=selected_prompt,
                        user_context=context_input,
                        repo=repo,
                    )
                )
                st.session_state.rb_session_id = session.id
            except Exception as exc:
                _rb_error = str(exc)
        if _rb_error:
            st.error(f"⚠️ {t('common.agent_error')}: {_rb_error}")
            st.stop()
        st.rerun()

    st.divider()
    st.subheader(t("rebalance_chat.past_sessions"))

    sessions = repo.list_sessions(limit=30)
    if not sessions:
        st.info(t("rebalance_chat.no_sessions"))
    else:
        for s in sessions:
            date_str = s.created_at.strftime("%d.%m.%Y %H:%M")
            label = f"**{_session_label(s)}**  \n{s.skill_name} · {date_str}"
            active = st.session_state.rb_session_id == s.id
            col_btn, col_del = st.columns([5, 1])
            if col_btn.button(
                label,
                key=f"rb_sess_{s.id}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state.rb_session_id = s.id
                st.rerun()
            if col_del.button("🗑", key=f"rb_del_{s.id}"):
                repo.delete_session(s.id)
                if st.session_state.rb_session_id == s.id:
                    st.session_state.rb_session_id = None
                st.rerun()

# ------------------------------------------------------------------
# Right: chat interface
# ------------------------------------------------------------------

with col_chat:
    session_id = st.session_state.rb_session_id

    if session_id is None:
        st.info(t("rebalance_chat.select_or_start"))
    else:
        session = repo.get_session(session_id)
        if session is None:
            st.warning(t("rebalance_chat.session_not_found"))
            st.session_state.rb_session_id = None
        else:
            # Session header with refresh button
            col_title, col_refresh = st.columns([5, 1])
            col_title.markdown(f"### {session.skill_name}")
            col_title.caption(session.created_at.strftime("%d.%m.%Y %H:%M"))

            if col_refresh.button("↻", key="rb_refresh", help=t("rebalance_chat.refresh_tooltip")):
                _rb_error = None
                with st.spinner(t("rebalance_chat.thinking")):
                    try:
                        new_session, _ = asyncio.run(
                            agent.start_session(
                                skill_name=session.skill_name,
                                skill_prompt=session.skill_prompt,
                                user_context="",
                                repo=repo,
                            )
                        )
                        st.session_state.rb_session_id = new_session.id
                    except Exception as exc:
                        _rb_error = str(exc)
                if _rb_error:
                    st.error(f"⚠️ {t('common.agent_error')}: {_rb_error}")
                else:
                    st.toast(t("rebalance_chat.refresh_done"), icon="✅")
                st.rerun()

            messages = repo.get_messages(session_id)
            for msg in messages:
                role = "user" if msg.role == "user" else "assistant"
                with st.chat_message(role):
                    st.markdown(msg.content)
                    if role == "assistant":
                        st.caption(t("common.ai_disclaimer"))

            if prompt := st.chat_input(t("rebalance_chat.chat_placeholder")):
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner(t("rebalance_chat.thinking")):
                        try:
                            response = asyncio.run(
                                agent.chat(session_id, prompt, repo)
                            )
                        except Exception as exc:
                            response = f"⚠️ {t('common.agent_error')}: {exc}"
                    st.markdown(response)
                    st.caption(t("common.ai_disclaimer"))
                st.rerun()
