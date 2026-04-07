"""
Rebalance Chat — conversational portfolio analysis using local Ollama LLM.
"""

import asyncio
from datetime import datetime, timezone

import streamlit as st

from config import config
from core.health import is_local_url
from core.i18n import t
from state import get_agent_scheduler, get_analyses_repo, get_positions_repo, get_rebalance_agent, get_rebalance_repo, get_scheduled_jobs_repo, get_skills_repo

st.set_page_config(page_title="Invest / Rebalance", page_icon="⚖️", layout="wide")
st.title(f"⚖️ {t('rebalance_chat.title')}")
st.caption(t("rebalance_chat.subtitle"))

agent = get_rebalance_agent()

if is_local_url(config.OLLAMA_HOST):
    st.info(t("rebalance_chat.private_notice").format(model=agent._llm.model), icon="🔒")
else:
    st.warning(t("rebalance_chat.remote_notice").format(host=config.OLLAMA_HOST, model=agent._llm.model), icon="⚠️")
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

# ------------------------------------------------------------------
# Agent signals overview — per-position verdict summary
# ------------------------------------------------------------------

_positions_repo = get_positions_repo()
_analyses_repo = get_analyses_repo()
_portfolio = _positions_repo.get_portfolio()

if _portfolio:
    _pos_ids = [p.id for p in _portfolio if p.id]
    _story_v  = _analyses_repo.get_latest_bulk(_pos_ids, "storychecker")
    _fund_v   = _analyses_repo.get_latest_bulk(_pos_ids, "fundamental")
    _gap_v    = _analyses_repo.get_latest_bulk(_pos_ids, "consensus_gap")

    _S_ICONS  = {"intact": "🟢", "gemischt": "🟡", "gefaehrdet": "🔴"}
    _F_ICONS  = {"unterbewertet": "🟢", "fair": "🟡", "überbewertet": "🔴", "unbekannt": "⚪"}
    _G_ICONS  = {"wächst": "🟢", "stabil": "🟡", "schließt": "🟠", "eingeholt": "🔴"}

    with st.expander("📊 Agent-Signale — Einzelpositionen", expanded=False):
        _header = st.columns([3, 1, 1, 1])
        _header[0].markdown("**Position**")
        _header[1].markdown("**Thesis**")
        _header[2].markdown("**Fundamental**")
        _header[3].markdown("**Konsens-Lücke**")
        st.divider()
        for _p in sorted(_portfolio, key=lambda p: p.name.lower()):
            if not _p.id:
                continue
            _sv = _story_v.get(_p.id)
            _fv = _fund_v.get(_p.id)
            _gv = _gap_v.get(_p.id)

            _s_cell = f"{_S_ICONS.get(_sv.verdict, '⚪')} {_sv.verdict}" if _sv and _sv.verdict else "—"
            _f_cell = f"{_F_ICONS.get(_fv.verdict, '⚪')} {_fv.verdict}" if _fv and _fv.verdict else "—"
            _g_cell = f"{_G_ICONS.get(_gv.verdict, '⚪')} {_gv.verdict}" if _gv and _gv.verdict else "—"

            _row = st.columns([3, 1, 1, 1])
            _label = f"**{_p.ticker or _p.name}**" + (f" · {_p.name}" if _p.ticker and _p.ticker != _p.name else "")
            _row[0].markdown(_label)
            _row[1].markdown(_s_cell)
            _row[2].markdown(_f_cell)
            _row[3].markdown(_g_cell)

            # Show summaries on hover via caption if any verdict has a summary
            _summaries = []
            if _sv and _sv.summary:
                _summaries.append(f"Thesis: {_sv.summary}")
            if _fv and _fv.summary:
                _summaries.append(f"Fundamental: {_fv.summary}")
            if _gv and _gv.summary:
                _summaries.append(f"Lücke: {_gv.summary}")
            if _summaries:
                _row[0].caption(" · ".join(_summaries))

if "rb_session_id" not in st.session_state:
    st.session_state.rb_session_id = None

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

    with st.form("new_rebalance_form"):
        if rebalance_skills:
            skill_names = [s.name for s in rebalance_skills]
            _skill_map = {s.name: s for s in rebalance_skills}
            skill_choice = st.selectbox(t("rebalance_chat.skill_label"), skill_names)
        else:
            st.warning(t("rebalance_chat.no_skill"))
            skill_choice = None

        context_input = st.text_input(
            t("rebalance_chat.context_label"),
            placeholder=t("rebalance_chat.context_placeholder"),
        ).strip()

        submitted = st.form_submit_button(
            t("rebalance_chat.start_button"), use_container_width=True
        )

    if submitted and skill_choice:
        selected_skill = _skill_map[skill_choice]
        _rb_error = None
        with st.spinner(t("rebalance_chat.thinking")):
            try:
                session, _ = asyncio.run(
                    agent.start_session(
                        skill_name=selected_skill.name,
                        skill_prompt=selected_skill.prompt,
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
            label = f"**{s.skill_name}**  \n{date_str}"
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
            st.markdown(f"### {session.skill_name}")
            st.caption(session.created_at.strftime("%d.%m.%Y %H:%M"))

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
