"""
Strukturwandel-Scanner — Claude's eigene Investmentstrategie, Säule 1.

Identifiziert strukturelle Marktverschiebungen bevor der Konsens sie erkennt.
Kandidaten werden direkt in die Watchlist übernommen.
Analysis runs in a background thread so page navigation doesn't kill the job.
"""

import asyncio
import threading
import time

import streamlit as st

from core.i18n import t, current_language
from core.ui.verdicts import cloud_notice
from state import (
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
cloud_notice(_agent._llm.model, provider="claude")
_repo = get_structural_scans_repo()
_skills = get_skills_repo().get_by_area("structural_scan")

if not _skills:
    st.warning(t("structural_scan.no_skills"))
    st.stop()

# ------------------------------------------------------------------
# Background job tracking (session_state — survives reruns)
# ------------------------------------------------------------------

if "_scan_job" not in st.session_state:
    st.session_state["_scan_job"] = {
        "running": False, "done": False, "run_id": None,
        "error": None, "last_error": None, "proposals": [],
    }

_JOB = st.session_state["_scan_job"]

if "scan_run_id" not in st.session_state:
    st.session_state["scan_run_id"] = None

if "scan_proposals" not in st.session_state:
    st.session_state["scan_proposals"] = []


def _run_background(agent, skill_name, skill_prompt, user_focus, language: str, repo, job: dict, enable_thinking: bool = False):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        run, _, proposals = loop.run_until_complete(
            agent.start_scan(
                skill_name=skill_name,
                skill_prompt=skill_prompt,
                user_focus=user_focus,
                repo=repo,
                language=language,
                enable_thinking=enable_thinking,
            )
        )
        job.update({"running": False, "done": True, "run_id": run.id, "error": None, "proposals": proposals})
    except Exception as exc:
        job.update({"running": False, "done": True, "run_id": None, "error": str(exc), "last_error": str(exc)})
    finally:
        loop.close()


# ------------------------------------------------------------------
# Start a new scan
# ------------------------------------------------------------------

with st.expander(t("structural_scan.new_scan_header"), expanded=st.session_state["scan_run_id"] is None and not _JOB["running"]):
    _skill_options = {s.name: s for s in _skills}
    _sel_skill_name = st.selectbox(
        t("structural_scan.skill_label"),
        options=list(_skill_options.keys()),
        key="_scan_skill",
        disabled=_JOB["running"],
    )
    _sel_skill = _skill_options[_sel_skill_name]

    _user_focus = st.text_area(
        t("structural_scan.focus_label"),
        placeholder=t("structural_scan.focus_placeholder"),
        height=80,
        key="_scan_focus",
        disabled=_JOB["running"],
    )

    from core.constants import CLAUDE_SONNET, CLAUDE_OPUS
    _supports_thinking = _agent._llm.model in {CLAUDE_SONNET, CLAUDE_OPUS}
    _use_thinking = st.toggle(
        "Extended Thinking",
        value=False,
        disabled=not _supports_thinking,
        help="Adaptive thinking — bessere Query-Planung, mehr Tokens",
        key="_scan_extended_thinking",
    )

    if st.button(t("structural_scan.start_button"), type="primary", key="_scan_start", disabled=_JOB["running"]):
        _lang = current_language()
        _JOB["running"] = True
        _JOB["done"] = False
        _JOB["run_id"] = None
        _JOB["error"] = None
        _JOB["last_error"] = None
        _JOB["proposals"] = []
        t_bg = threading.Thread(
            target=_run_background,
            args=(_agent, _sel_skill.name, _sel_skill.prompt, _user_focus or None, _lang, _repo, _JOB, _use_thinking),
            daemon=True,
        )
        t_bg.start()
        st.rerun()

# Running indicator — auto-refresh every 5s
if _JOB["running"]:
    st.info(f"⏳ {t('structural_scan.running')} (inkl. Story-Check der Kandidaten …)", icon=":material/hourglass_top:")
    time.sleep(5)
    st.rerun()

# Done: set active run and reset job state
if _JOB["done"]:
    if _JOB["error"]:
        import logging
        logger = logging.getLogger(__name__)
        logger.error("Structural scan error: %s", _JOB['error'])
        st.error("❌ Strukturwandel-Scan fehlgeschlagen. Bitte versuchen Sie es später erneut.")
    elif _JOB["run_id"]:
        st.session_state["scan_run_id"] = _JOB["run_id"]
        st.session_state["scan_proposals"] = _JOB.get("proposals", [])
    _JOB["done"] = False
    if _JOB["run_id"]:
        st.rerun()

# Persistent error
if _JOB["last_error"] and not _JOB["running"]:
    import logging
    logger = logging.getLogger(__name__)
    logger.error("Last structural scan error: %s", _JOB['last_error'])
    st.error("❌ Letzter Scan fehlgeschlagen. Bitte versuchen Sie es später erneut.")

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

        # ── Proposal panel ───────────────────────────────────────────
        if st.session_state["scan_proposals"]:
            st.subheader("📋 Watchlist-Vorschläge")
            st.caption("Claude empfiehlt diese Kandidaten — wähle aus, welche du übernehmen möchtest:")
            for i, p in enumerate(st.session_state["scan_proposals"]):
                st.checkbox(
                    f"**{p['name']}** ({p['ticker']}) · {p['asset_class']}",
                    key=f"scan_prop_{_active_run_id}_{i}",
                )
                if p.get("full_story"):
                    st.caption(p["full_story"][:200])
            if st.button("Zur Watchlist hinzufügen", type="primary", key=f"scan_add_{_active_run_id}"):
                selected = [
                    st.session_state["scan_proposals"][i]
                    for i in range(len(st.session_state["scan_proposals"]))
                    if st.session_state.get(f"scan_prop_{_active_run_id}_{i}", False)
                ]
                if selected:
                    for prop in selected:
                        try:
                            _agent.add_from_proposal(prop)
                        except Exception as exc:
                            st.error(f"Error adding {prop['name']}: {exc}")
                    st.success(f"✅ {len(selected)} Position(en) hinzugefügt!", icon=":material/bookmark_added:")
                    st.session_state["scan_proposals"] = []
                    st.rerun()
                else:
                    st.info("Bitte wähle mindestens eine Position aus.")

        st.divider()

        # ── Follow-up chat ───────────────────────────────────────────
        st.subheader(t("structural_scan.followup_header"))
        _messages = _repo.get_messages(_active_run_id)
        for msg in _messages[2:]:
            with st.chat_message(msg.role):
                st.markdown(msg.content)

        _followup = st.chat_input(t("structural_scan.chat_placeholder"))
        if _followup:
            with st.chat_message("user"):
                st.markdown(_followup)
            with st.chat_message("assistant"):
                with st.spinner("…"):
                    _use_thinking_followup = st.session_state.get("_scan_extended_thinking", False)
                    _reply = asyncio.run(
                        _agent.chat(
                            run_id=_active_run_id,
                            user_message=_followup,
                            repo=_repo,
                            enable_thinking=_use_thinking_followup,
                        )
                    )
                st.markdown(_reply)
            st.rerun()

        if st.button(t("structural_scan.new_scan_button"), key="_scan_new"):
            st.session_state["scan_run_id"] = None
            st.session_state["scan_proposals"] = []
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
                st.session_state["scan_proposals"] = []
                st.rerun()
