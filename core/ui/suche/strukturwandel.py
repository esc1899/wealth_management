"""
Strukturwandel — Claude's eigene Investmentstrategie, Säule 1 (Teil der Seite Suche).

Identifiziert strukturelle Marktverschiebungen bevor der Konsens sie erkennt.
Der Scan läuft in einem Hintergrund-Thread, damit ein Seitenwechsel ihn nicht abbricht; seine
Vorschläge werden Kandidaten, sobald die Seite ihn fertig sieht (``nachziehen``).
"""

import asyncio
import logging
import threading
import time

import streamlit as st

from core.i18n import t, current_language
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


def _run_background(agent, skill_name, skill_prompt, user_focus, language: str, repo, job: dict,
                    enable_thinking: bool = False, bekannte_ticker: tuple = ()):
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
                bekannte_ticker=bekannte_ticker,
            )
        )
        job.update({"running": False, "done": True, "run_id": run.id, "error": None,
                    "proposals": proposals, "skill": skill_name})
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
        args=(_agent(), skill.name, skill.prompt, anfrage or None, current_language(), _repo(), job,
              denken, tuple(gemeinsam.bekannte_ticker())),
        daemon=True,
    ).start()
    st.rerun()


def nachziehen() -> None:
    """Läuft der Scan, wartet die Seite; ist er fertig, werden seine Vorschläge Kandidaten."""
    job = _job()
    if job["running"]:
        st.info(f"⏳ {t('structural_scan.running')}", icon=":material/hourglass_top:")
        time.sleep(5)
        st.rerun()
    if job["done"]:
        job["done"] = False
        if job["error"]:
            logger.error("Structural scan error: %s", job["error"])
        elif job["run_id"]:
            gemeinsam.aufnehmen(job.get("proposals", []), "strukturwandel", job.get("skill"), job["run_id"])
            job["proposals"] = []
    if job["last_error"]:
        st.error(t("suche.fehlgeschlagen"))


def bericht(lauf_id: int):
    """(wann, Skill, Fokus, Texte) des Scans, oder None."""
    repo = _repo()
    run = repo.get_run(lauf_id)
    if run is None:
        return None
    texte = [run.result] + [m.content for m in repo.get_messages(lauf_id)[2:] if m.role == "assistant"]
    return run.created_at, run.skill_name, run.user_focus, texte
