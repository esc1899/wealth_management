"""
Strukturwandel-Scanner — Claude's eigene Investmentstrategie, Säule 1.

Identifiziert strukturelle Marktverschiebungen bevor der Konsens sie erkennt.
Kandidaten werden direkt in die Watchlist übernommen.
"""

import asyncio

import streamlit as st

from core.i18n import t
from state import (
    get_positions_repo,
    get_skills_repo,
    get_structural_change_agent,
    get_structural_scans_repo,
)

st.set_page_config(
    page_title="Strukturwandel-Scanner",
    page_icon="🔭",
    layout="wide",
)
st.title(f"🔭 {t('structural_scan.title')}")
st.caption(t("structural_scan.subtitle"))

_agent = get_structural_change_agent()
_repo = get_structural_scans_repo()
_skills = get_skills_repo().get_by_area("structural_scan")

if not _skills:
    st.warning(t("structural_scan.no_skills"))
    st.stop()

# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------

if "scan_run_id" not in st.session_state:
    st.session_state["scan_run_id"] = None

# ------------------------------------------------------------------
# Start a new scan
# ------------------------------------------------------------------

with st.expander(t("structural_scan.new_scan_header"), expanded=st.session_state["scan_run_id"] is None):
    _skill_options = {s.name: s for s in _skills}
    _sel_skill_name = st.selectbox(
        t("structural_scan.skill_label"),
        options=list(_skill_options.keys()),
        key="_scan_skill",
    )
    _sel_skill = _skill_options[_sel_skill_name]

    _user_focus = st.text_area(
        t("structural_scan.focus_label"),
        placeholder=t("structural_scan.focus_placeholder"),
        height=80,
        key="_scan_focus",
    )

    if st.button(t("structural_scan.start_button"), type="primary", key="_scan_start"):
        with st.spinner(t("structural_scan.running")):
            run, report = asyncio.run(
                _agent.start_scan(
                    skill_name=_sel_skill.name,
                    skill_prompt=_sel_skill.prompt,
                    user_focus=_user_focus or None,
                    repo=_repo,
                )
            )
        st.session_state["scan_run_id"] = run.id
        st.rerun()

# ------------------------------------------------------------------
# Active run: report + follow-up chat
# ------------------------------------------------------------------

_active_run_id = st.session_state.get("scan_run_id")

if _active_run_id:
    _run = _repo.get_run(_active_run_id)
    if _run:
        st.subheader(
            f"{t('structural_scan.report_header')} — {_run.created_at.strftime('%d.%m.%Y %H:%M')}"
            + (f" · {_run.skill_name}" if _run.skill_name else "")
        )
        if _run.user_focus:
            st.caption(f"{t('structural_scan.focus_label')}: {_run.user_focus}")

        st.markdown(_run.result)
        st.divider()

        # ── Watchlist summary ────────────────────────────────────────
        _candidates = [
            p for p in get_positions_repo().get_watchlist()
            if p.notes and "Strukturwandel-Scan" in (p.notes or "")
        ]
        if _candidates:
            st.success(
                f"✅ {len(_candidates)} {t('structural_scan.candidates_added')}",
                icon=":material/bookmark_added:",
            )
            with st.expander(t("structural_scan.show_candidates")):
                for c in _candidates:
                    st.markdown(f"- **{c.name}** ({c.ticker or '—'}) · {c.asset_class}")

        # ── Follow-up chat ───────────────────────────────────────────
        st.subheader(t("structural_scan.followup_header"))
        _messages = _repo.get_messages(_active_run_id)
        # Show messages after the initial scan exchange (skip first user+assistant pair)
        for msg in _messages[2:]:
            with st.chat_message(msg.role):
                st.markdown(msg.content)

        _followup = st.chat_input(t("structural_scan.chat_placeholder"))
        if _followup:
            with st.chat_message("user"):
                st.markdown(_followup)
            with st.chat_message("assistant"):
                with st.spinner("…"):
                    _reply = asyncio.run(
                        _agent.chat(
                            run_id=_active_run_id,
                            user_message=_followup,
                            repo=_repo,
                        )
                    )
                st.markdown(_reply)
            st.rerun()

        if st.button(t("structural_scan.new_scan_button"), key="_scan_new"):
            st.session_state["scan_run_id"] = None
            st.rerun()

# ------------------------------------------------------------------
# Scan history
# ------------------------------------------------------------------

_recent = _repo.get_recent_runs(limit=5)
_history = [r for r in _recent if r.id != _active_run_id]

if _history:
    st.divider()
    st.subheader(t("structural_scan.history_header"))
    for _h in _history:
        _label = f"{_h.created_at.strftime('%d.%m.%Y %H:%M')} — {_h.skill_name}"
        if _h.user_focus:
            _label += f" · {_h.user_focus[:40]}"
        with st.expander(_label):
            st.markdown(_h.result)
            if st.button(
                t("structural_scan.continue_button"),
                key=f"_scan_continue_{_h.id}",
            ):
                st.session_state["scan_run_id"] = _h.id
                st.rerun()
