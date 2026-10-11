"""
Freie Suche — Screening mit Claude + Websuche nach einem Thema (Teil der Seite Suche).
Ohne Skill (``None``) schreibt man die Strategie selbst.
"""

import asyncio

import streamlit as st

from core.i18n import t
from core.ui.markdown import llm_markdown
from core.ui.suche import gemeinsam


def _agent():
    from state import get_search_agent
    return get_search_agent()


def modell() -> str:
    return _agent().model


def starten(skill, anfrage: str, eigene: str, denken: bool) -> None:
    agent = _agent()
    session = agent.start_session(
        query=anfrage,
        skill_name=skill.name if skill else t("search_chat.custom_skill"),
        skill_prompt=skill.prompt if skill else eigene,
    )
    st.session_state.sc_session_id = session.id
    st.session_state.sc_proposals = []
    nachricht = (
        f"Please screen for investment opportunities matching this request: "
        f"**{anfrage}**\n\nApply the screening strategy and return a ranked list."
    )
    with st.spinner(t("search_chat.thinking")):
        try:
            _, st.session_state.sc_proposals = asyncio.run(agent.chat(session.id, nachricht, enable_thinking=denken))
        except Exception as exc:
            st.error(f"⚠️ {t('common.agent_error')}: {exc}")
            return
    st.rerun()


def lauf() -> None:
    """Der letzte Lauf: Vorschläge, darunter eingeklappt Bericht und Rückfrage."""
    agent = _agent()
    if st.session_state.get("sc_session_id") is None:
        letzte = agent.list_sessions(limit=1)
        st.session_state.sc_session_id = letzte[0].id if letzte else None
    session_id = st.session_state.sc_session_id
    session = agent.get_session(session_id) if session_id else None
    if session is None:
        st.info(t("suche.noch_kein_lauf"))
        return

    gemeinsam.kopf(session.created_at, session.skill_name, session.query)
    if gemeinsam.vorschlaege(st.session_state.get("sc_proposals", []), f"sc_prop_{session_id}",
                             lambda p: agent.add_from_proposal(session_id, p)):
        st.session_state.sc_proposals = []
        st.rerun()

    with st.expander(t("suche.bericht")):
        for msg in agent.get_messages(session_id)[1:]:
            with st.chat_message("user" if msg.role == "user" else "assistant"):
                llm_markdown(msg.content)
        st.caption(t("common.ai_disclaimer"))
        if frage := st.chat_input(t("search_chat.chat_placeholder"), key="sc_frage"):
            with st.spinner(t("search_chat.searching")):
                try:
                    _, st.session_state.sc_proposals = asyncio.run(agent.chat(
                        session_id, frage, enable_thinking=st.session_state.get("suche_denken", False)))
                except Exception as exc:
                    st.error(f"⚠️ {t('common.agent_error')}: {exc}")
                    return
            st.rerun()
