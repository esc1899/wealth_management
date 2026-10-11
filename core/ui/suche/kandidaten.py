"""Die Kandidaten auf der Seite Suche: "Offen" als Kacheln, darunter eingeklappt "Ignoriert"
und "Verworfen" (BACKLOG.md, "Suche", 11.10.2026).

Eine Kachel sieht aus wie auf der Watchlist und springt auf die Titelseite des Kandidaten, auf
der auch der Bericht des Laufs steht, der ihn fand. Statt "Jetzt checken" heißt der Knopf
"Genauer prüfen" (Cloud, Websuche kostet), darunter die Entscheidung: auf die Watchlist oder
nicht interessant. Ist noch nichts geprüft, steht statt "nie geprüft" die These der Suche.

Rechnen tut ``core/kandidaten.py``; hier wird nur gezeigt und entschieden.
"""

from __future__ import annotations

from html import escape

import streamlit as st

from core.i18n import fmt_date, t
from core.ui import kacheln as kachel_ui

_SPALTEN = 3
#: So viel These steht in einer Zeile unter "Verworfen" und "Ignoriert".
_THESE_KURZ = 160


def _teil(strategie: str):
    from core.ui.suche import einzeltitel, frei, strukturwandel
    return {"frei": frei, "einzeltitel": einzeltitel, "strukturwandel": strukturwandel}.get(strategie)


def bericht(strategie: str, lauf_id):
    """(wann, Skill, Anfrage, Texte) des Laufs, der den Kandidaten fand; None, wenn er fehlt."""
    teil = _teil(strategie)
    if teil is None or lauf_id is None:
        return None
    return teil.bericht(lauf_id)


def herkunft(k) -> str:
    """Woher er kommt, in einer Zeile: Strategie, Skill, wie oft, wann zuletzt."""
    teile = [t(f"suche.art_{k.strategie}")]
    if k.skill:
        teile.append(k.skill)
    if k.funde > 1:
        teile.append(t("kandidaten.funde").format(n=k.funde))
    if k.zustand == "verworfen" and k.entschieden:
        teile.append(t("kandidaten.verworfen_am").format(datum=fmt_date(k.entschieden)))
    else:
        teile.append(fmt_date(k.beruehrt))
    return " · ".join(teile)


def entscheiden(position_id: int, key: str) -> None:
    """Ja oder Nein. Ein Nein wird gemerkt (unten "Verworfen"), ein Ja legt den Titel auf die
    Watchlist -- mit allen Urteilen, die er als Kandidat bekam."""
    from core import kandidaten
    from state import get_kandidaten_repo, get_positions_repo

    ja, nein = st.columns(2)
    if ja.button(t("kandidaten.auf_die_watchlist"), key=f"{key}-ja", icon=":material/bookmark_add:",
                 width="stretch"):
        kandidaten.auf_die_watchlist(get_positions_repo(), get_kandidaten_repo(), position_id)
        st.toast(t("kandidaten.uebernommen"), icon="✅")
        st.rerun()
    if nein.button(t("kandidaten.nicht_interessant"), key=f"{key}-nein", icon=":material/block:",
                   width="stretch"):
        kandidaten.verwerfen(get_kandidaten_repo(), position_id)
        st.rerun()


def _inhalt(kachel, position) -> str:
    """Wie auf der Watchlist; ohne jedes Urteil statt "nie geprüft" die These der Suche."""
    if kachel.grund != "nie" or not position.story:
        return kachel_ui.inhalt_html(kachel)
    return (f'<div class="wk-notiz">{escape(position.story)}</div>'
            f'<div class="wk-quelle">{escape(t("kandidaten.these_der_suche"))}</div>')


def karte(kachel, position, k) -> None:
    from core.ui.titelseite import jetzt_checken

    st.markdown(kachel_ui.farbe_css(kachel, kachel_ui.farbe(kachel.anlageklasse)), unsafe_allow_html=True)
    with st.container(key=f"wk-karte-{kachel.position_id}"):
        with st.container(key=f"wk-kopf-{kachel.position_id}"):
            st.page_link(kachel_ui.ziel("kandidaten"), label=kachel.name,
                         query_params={"position": kachel.position_id})
            st.markdown(kachel_ui.unter_html(kachel), unsafe_allow_html=True)
        st.markdown(f'<div class="wk-quelle">{escape(herkunft(k))}</div>', unsafe_allow_html=True)
        st.markdown(_inhalt(kachel, position), unsafe_allow_html=True)
        kachel_ui.kaestchen(kachel, "kandidaten")
        jetzt_checken("kandidaten", position, {u.agent: u for u in kachel.urteile},
                      key=f"wk-checken-{kachel.position_id}", klein=True)
        entscheiden(position.id, key=f"wk-entscheiden-{kachel.position_id}")


def _zeile(position, k, key: str) -> None:
    """Eine Zeile unter "Verworfen" oder "Ignoriert": Name, Herkunft, These, wieder aufnehmen."""
    from core import kandidaten
    from state import get_kandidaten_repo

    text, knopf = st.columns([5, 1.4], vertical_alignment="center")
    with text:
        ticker = f" ({position.ticker})" if position.ticker else ""
        st.markdown(f"**{position.name}**{ticker}  \n:gray[{herkunft(k)}]")
        if position.story:
            st.caption(position.story[:_THESE_KURZ] + ("…" if len(position.story) > _THESE_KURZ else ""))
    if knopf.button(t("kandidaten.wieder_aufnehmen"), key=key, width="stretch"):
        kandidaten.wieder_aufnehmen(get_kandidaten_repo(), position.id)
        st.rerun()


def liste() -> None:
    """Die stehende Liste: offene Kandidaten als Kacheln, darunter die beiden Klapper."""
    from core import kandidaten
    from core.kacheln import RANG
    from state import get_kandidaten_repo, get_positions_repo

    teile = kandidaten.listen(get_positions_repo(), get_kandidaten_repo())
    st.subheader(t("kandidaten.titel"))
    st.markdown(kachel_ui.CSS, unsafe_allow_html=True)
    if not teile.offen:
        st.markdown(t("kandidaten.keine_offenen"))
    else:
        st.markdown(t("kandidaten.offen_satz").format(n=len(teile.offen)))
        je_id = {p.id: (p, k) for p, k in teile.offen}
        # Nach dem Vorrang der Kacheln (gefaehrdet zuerst, ungeprueft zuletzt), darin die
        # juengste Beruehrung zuerst -- ein neuer Fund steht oben in seiner Gruppe.
        kacheln = sorted(kachel_ui.kacheln_fuer("kandidaten", [p for p, _ in teile.offen]),
                         key=lambda kc: (RANG[kc.grund], -je_id[kc.position_id][1].beruehrt.timestamp()))
        for start in range(0, len(kacheln), _SPALTEN):
            for spalte, kc in zip(st.columns(_SPALTEN), kacheln[start:start + _SPALTEN]):
                with spalte:
                    p, k = je_id[kc.position_id]
                    karte(kc, p, k)

    if teile.ignoriert:
        with st.expander(t("kandidaten.ignoriert").format(n=len(teile.ignoriert))):
            st.caption(t("kandidaten.ignoriert_satz").format(tage=kandidaten.IGNORIERT_NACH_TAGEN))
            for p, k in teile.ignoriert:
                _zeile(p, k, key=f"kand-ign-{p.id}")
    if teile.verworfen:
        with st.expander(t("kandidaten.verworfen").format(n=len(teile.verworfen))):
            st.caption(t("kandidaten.verworfen_satz"))
            for p, k in teile.verworfen:
                _zeile(p, k, key=f"kand-verw-{p.id}")
