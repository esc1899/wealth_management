"""
Einzeltitel — ein Name, Ticker oder ISIN, bewertet mit Claude + Websuche (Teil der Seite Suche).

Was die Bewertung vorschlägt, wird ein Kandidat wie jeder andere (core/kandidaten.py), mit
"Genauer prüfen" und der Bewertung auf seiner Titelseite. Was schon im Depot oder auf der
Watchlist steht, sagt die Seite vorher, ohne Modell, statt neu zu bewerten.
"""

import asyncio

import streamlit as st

from core.i18n import current_language, t
from core.strategy_config import CUSTOM_STRATEGY_NAME
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
    skill_name = skill.name if skill else CUSTOM_STRATEGY_NAME
    session = agent.start_session(
        ticker=anfrage.upper(),
        strategy_name=skill_name,
        company_name=None,
        custom_prompt=skill.prompt if skill else eigene,
    )
    nachricht = (
        f"Bitte analysiere '{anfrage}'. Falls das kein Ticker-Symbol ist, "
        f"finde zunächst das korrekte Ticker-Symbol und gib mir dann eine "
        f"strukturierte Bewertung gemäß der Analysestrategie."
    )
    with st.spinner(t("research_chat.thinking")):
        try:
            _, vorschlaege = asyncio.run(agent.chat(session.id, nachricht, language=current_language()))
        except Exception as exc:
            st.error(f"⚠️ {t('common.agent_error')}: {exc}")
            return
    gemeinsam.aufnehmen(vorschlaege, "einzeltitel", skill_name, session.id)
    st.rerun()


def hinweis() -> None:
    """Stand der Titel schon im Depot oder auf der Watchlist, sagt die Seite das hier."""
    from state import get_positions_repo

    if (pid := st.session_state.pop("rc_bekannt", None)) is not None:
        if (p := get_positions_repo().get(pid)) is not None:
            hinweis_bekannt(p)


def bericht(lauf_id: int):
    """(wann, Skill, Titel, Texte) der Bewertung, oder None."""
    agent = _agent()
    session = agent.get_session(lauf_id)
    if session is None:
        return None
    titel = session.ticker + (f" ({session.company_name})" if session.company_name else "")
    texte = [m.content for m in agent.get_messages(lauf_id) if m.role == "assistant"]
    return session.created_at, session.strategy_name, titel, texte
