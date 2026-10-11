"""
Einzeltitel — ein Name, Ticker oder ISIN, bewertet mit Claude + Websuche (Teil der Seite Suche).

Stufe 1 der Suche (11.10.2026): bewerten, dann auf Wunsch direkt auf die Watchlist. Stufe 2
("Genauer pruefen") kommt mit den Kandidaten (BACKLOG.md, "Suche"). Was schon im Depot oder auf
der Watchlist steht, sagt die Seite vorher, ohne Modell, statt neu zu bewerten.
"""

import asyncio
from typing import Optional

import streamlit as st

from core.i18n import current_language, t
from core.strategy_config import CUSTOM_STRATEGY_NAME
from core.ui.markdown import llm_markdown
from core.ui.suche import gemeinsam


def _agent():
    from state import get_research_agent
    return get_research_agent()


def modell() -> str:
    return _agent().model


def bekannt(eingabe: str):
    """Die Position, die schon so heißt oder diesen Ticker oder diese ISIN trägt, sonst None."""
    from state import get_positions_repo

    gesucht = eingabe.strip().casefold()
    if not gesucht:
        return None
    for p in get_positions_repo().get_all():
        if not (p.in_portfolio or p.in_watchlist):
            continue
        if gesucht in {(x or "").strip().casefold() for x in (p.name, p.ticker, p.isin, p.wkn)}:
            return p
    return None


def hinweis_bekannt(p) -> None:
    from streamlit.errors import StreamlitAPIException

    from core.ui import kacheln as kachel_ui

    art = "depot" if p.in_portfolio else "watchlist"
    st.info(t(f"suche.bekannt_{art}").format(name=p.name), icon=":material/info:")
    try:
        st.page_link(kachel_ui.ziel(art), label=t("suche.zur_titelseite"), query_params={"position": p.id})
    except (StreamlitAPIException, KeyError):
        pass


def starten(skill, anfrage: str, eigene: str, denken: bool) -> None:
    vorhanden = bekannt(anfrage)
    if vorhanden is not None:
        st.session_state.rc_bekannt = vorhanden.id
        st.rerun()
    agent = _agent()
    session = agent.start_session(
        ticker=anfrage.upper(),
        strategy_name=skill.name if skill else CUSTOM_STRATEGY_NAME,
        company_name=None,
        custom_prompt=skill.prompt if skill else eigene,
    )
    st.session_state.rc_session_id = session.id
    st.session_state.rc_proposals = []
    nachricht = (
        f"Bitte analysiere '{anfrage}'. Falls das kein Ticker-Symbol ist, "
        f"finde zunächst das korrekte Ticker-Symbol und gib mir dann eine "
        f"strukturierte Bewertung gemäß der Analysestrategie."
    )
    with st.spinner(t("research_chat.thinking")):
        try:
            _, st.session_state.rc_proposals = asyncio.run(agent.chat(session.id, nachricht, language=current_language()))
        except Exception as exc:
            st.error(f"⚠️ {t('common.agent_error')}: {exc}")
            return
    st.rerun()


def lauf() -> None:
    """Die letzte Bewertung: offen, denn sie ist das Ergebnis; darunter die Rückfrage."""
    from state import get_positions_repo

    if (pid := st.session_state.pop("rc_bekannt", None)) is not None:
        if (p := get_positions_repo().get(pid)) is not None:
            hinweis_bekannt(p)
            return

    agent = _agent()
    if st.session_state.get("rc_session_id") is None:
        letzte = agent.list_sessions(limit=1)
        st.session_state.rc_session_id = letzte[0].id if letzte else None
    session_id = st.session_state.rc_session_id
    session = agent.get_session(session_id) if session_id else None
    if session is None:
        st.info(t("suche.noch_kein_lauf"))
        return

    titel = session.ticker + (f" ({session.company_name})" if session.company_name else "")
    gemeinsam.kopf(session.created_at, session.strategy_name, titel)
    if gemeinsam.vorschlaege(st.session_state.get("rc_proposals", []), f"rc_prop_{session_id}",
                             lambda p: agent.add_from_proposal(session_id, p)):
        st.session_state.rc_proposals = []
        st.rerun()

    with st.expander(t("suche.bewertung"), expanded=True):
        for msg in agent.get_messages(session_id)[1:]:
            if msg.role == "tool":
                continue
            with st.chat_message("user" if msg.role == "user" else "assistant"):
                llm_markdown(msg.content)
        st.caption(t("common.ai_disclaimer"))
        if frage := st.chat_input(t("research_chat.chat_placeholder"), key="rc_frage"):
            with st.spinner(t("research_chat.analysing")):
                try:
                    _, st.session_state.rc_proposals = asyncio.run(
                        agent.chat(session_id, frage, language=current_language()))
                except Exception as exc:
                    st.error(f"⚠️ {t('common.agent_error')}: {exc}")
                    return
            st.rerun()
