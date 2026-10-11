"""
Strukturwandel — Claude's eigene Investmentstrategie, Säule 1 (Teil der Seite Suche).

Identifiziert strukturelle Marktverschiebungen bevor der Konsens sie erkennt.
Der Scan läuft in einem Hintergrund-Thread, damit ein Seitenwechsel ihn nicht abbricht.
"""

import asyncio
import logging
import threading
import time

import streamlit as st

from core.i18n import t, current_language
from core.ui.markdown import llm_markdown
from core.ui.suche import gemeinsam

logger = logging.getLogger(__name__)


def _agent():
    from state import get_structural_change_agent
    return get_structural_change_agent()


def _repo():
    from state import get_structural_scans_repo
    return get_structural_scans_repo()


def _job() -> dict:
    if "_scan_job" not in st.session_state:
        st.session_state["_scan_job"] = {
            "running": False, "done": False, "run_id": None,
            "error": None, "last_error": None, "proposals": [],
        }
    return st.session_state["_scan_job"]


def modell() -> str:
    return _agent()._llm.model


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


def laeuft() -> bool:
    return _job()["running"]


def starten(skill, anfrage: str, eigene: str, denken: bool) -> None:
    job = _job()
    job.update({"running": True, "done": False, "run_id": None, "error": None,
                "last_error": None, "proposals": []})
    threading.Thread(
        target=_run_background,
        args=(_agent(), skill.name, skill.prompt, anfrage or None, current_language(), _repo(), job, denken),
        daemon=True,
    ).start()
    st.rerun()


def lauf() -> None:
    """Der laufende oder letzte Scan: Vorschläge, darunter eingeklappt Bericht und Rückfrage."""
    job, repo = _job(), _repo()

    if job["running"]:
        st.info(f"⏳ {t('structural_scan.running')}", icon=":material/hourglass_top:")
        time.sleep(5)
        st.rerun()

    if job["done"]:
        if job["error"]:
            logger.error("Structural scan error: %s", job["error"])
        elif job["run_id"]:
            st.session_state["scan_run_id"] = job["run_id"]
            st.session_state["scan_proposals"] = job.get("proposals", [])
        job["done"] = False

    if job["last_error"]:
        st.error(t("suche.fehlgeschlagen"))

    if st.session_state.get("scan_run_id") is None:
        letzte = repo.get_recent_runs(limit=1)
        st.session_state["scan_run_id"] = letzte[0].id if letzte else None
    run_id = st.session_state["scan_run_id"]
    run = repo.get_run(run_id) if run_id else None
    if run is None:
        st.info(t("suche.noch_kein_lauf"))
        return

    gemeinsam.kopf(run.created_at, run.skill_name, run.user_focus)
    if gemeinsam.vorschlaege(st.session_state.get("scan_proposals", []), f"scan_prop_{run_id}",
                             _agent().add_from_proposal, text="full_story"):
        st.session_state["scan_proposals"] = []
        st.rerun()

    with st.expander(t("suche.bericht")):
        llm_markdown(run.result)
        for msg in repo.get_messages(run_id)[2:]:
            with st.chat_message(msg.role):
                llm_markdown(msg.content)
        if frage := st.chat_input(t("structural_scan.chat_placeholder"), key="scan_frage"):
            with st.spinner("…"):
                asyncio.run(_agent().chat(run_id=run_id, user_message=frage, repo=repo,
                                          enable_thinking=st.session_state.get("suche_denken", False)))
            st.rerun()
