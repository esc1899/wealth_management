"""Was alle Teile der Suche gleich tun: Vorschläge zu Kandidaten machen, die bekannten Ticker
mitgeben, nach dem Lauf in einem Satz sagen, was er gebracht hat."""

from typing import Optional

import streamlit as st

from core.i18n import t

_ERGEBNIS = "suche_ergebnis"


def bekannte_ticker() -> list[str]:
    """Was die Strategie nicht wieder vorschlagen soll -- nie das Depot (core/kandidaten.py)."""
    from core.kandidaten import bekannte_ticker as _bekannte
    from state import get_kandidaten_repo, get_positions_repo
    return _bekannte(get_positions_repo(), get_kandidaten_repo())


def aufnehmen(vorschlaege: list[dict], strategie: str, skill: Optional[str], lauf_id: int) -> None:
    """Die Vorschläge des Laufs in die Liste "Offen"; den Satz dazu zeigt ``ergebnis``."""
    from core.kandidaten import aufnehmen as _aufnehmen
    from state import get_kandidaten_repo, get_positions_repo

    a = _aufnehmen(get_positions_repo(), get_kandidaten_repo(), vorschlaege, strategie, skill, lauf_id)
    st.session_state[_ERGEBNIS] = {"strategie": strategie, "lauf_id": lauf_id, "neu": a.neu,
                                   "wieder": a.wieder, "verworfen": a.verworfen, "bekannt": a.bekannt}


def ergebnis(bericht) -> None:
    """Ein Satz zum Lauf dieser Sitzung. Hat er nichts vorgeschlagen, steht sein Bericht
    darunter -- sonst wäre er unsichtbar (der Bericht liegt sonst auf der Titelseite)."""
    from core.ui.markdown import llm_markdown

    e = st.session_state.get(_ERGEBNIS)
    if not e:
        return
    teile = [t(f"suche.ergebnis_{x}").format(n=e[x])
             for x in ("neu", "wieder", "verworfen", "bekannt") if e[x]]
    if teile:
        st.success(t("suche.ergebnis").format(teile=", ".join(teile)), icon=":material/travel_explore:")
        return
    st.info(t("suche.ergebnis_nichts"), icon=":material/search_off:")
    b = bericht(e["strategie"], e["lauf_id"])
    if b:
        with st.expander(t("suche.bericht")):
            for text in b[3]:
                llm_markdown(text)
            st.caption(t("common.ai_disclaimer"))
