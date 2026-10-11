"""
Freie Suche — Screening mit Claude + Websuche nach einem Thema (Teil der Seite Suche).
Ohne Skill (``None``) schreibt man die Strategie selbst. Die Vorschläge des Laufs werden
Kandidaten (core/kandidaten.py); den Bericht zeigt die Titelseite des Kandidaten.
"""

import asyncio

import streamlit as st

from core.i18n import t
from core.ui.suche import gemeinsam


def _agent():
    from state import get_search_agent
    return get_search_agent()


def modell() -> str:
    return _agent().model


def starten(skill, anfrage: str, eigene: str, denken: bool) -> None:
    agent = _agent()
    skill_name = skill.name if skill else t("search_chat.custom_skill")
    session = agent.start_session(query=anfrage, skill_name=skill_name,
                                  skill_prompt=skill.prompt if skill else eigene)
    nachricht = (
        f"Please screen for investment opportunities matching this request: "
        f"**{anfrage}**\n\nApply the screening strategy and return a ranked list."
    )
    with st.spinner(t("search_chat.thinking")):
        try:
            _, vorschlaege = asyncio.run(agent.chat(session.id, nachricht, enable_thinking=denken,
                                                    bekannte_ticker=gemeinsam.bekannte_ticker()))
        except Exception as exc:
            st.error(f"⚠️ {t('common.agent_error')}: {exc}")
            return
    gemeinsam.aufnehmen(vorschlaege, "frei", skill_name, session.id)
    st.rerun()


def bericht(lauf_id: int):
    """(wann, Skill, Anfrage, Texte) des Laufs, oder None."""
    agent = _agent()
    session = agent.get_session(lauf_id)
    if session is None:
        return None
    texte = [m.content for m in agent.get_messages(lauf_id) if m.role == "assistant"]
    return session.created_at, session.skill_name, session.query, texte
