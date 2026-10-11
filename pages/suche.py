"""
Suche — eine Seite für alle Wege zu neuen Titeln (11.10.2026, BACKLOG.md "Suche", Fassung A).

Oben die Strategie (freie Suche, Einzeltitel, Strukturwandel), darunter ein Suchfeld mit dem
Skill und dem Stern, ein Banner sagt, womit gesucht wird, und verweist auf die Skills. Darunter
der letzte Lauf der Strategie. Jeder Teil (core/ui/suche/) kennt ``modell``, ``starten`` und
``lauf``; das Suchfeld gehört der Seite.
"""

from pathlib import Path

import streamlit as st

from core.constants import supports_effort
from core.i18n import t
from core.ui.ki import ki_knopf
from core.ui.suche import einzeltitel, frei, strukturwandel
from core.ui.verdicts import cloud_notice
from state import get_skills_repo

#: Je Strategie der Bereich ihrer Skills, der Teil, der sie zeigt, und ob das Feld Pflicht ist.
STRATEGIEN = {
    "frei": ("search", frei, True),
    "einzeltitel": ("research", einzeltitel, True),
    "strukturwandel": ("structural_scan", strukturwandel, False),
}
#: Strategien, deren Strategie man auch selbst schreiben kann.
_MIT_EIGENER = {"frei", "einzeltitel"}
#: Absolut, damit ``st.page_link`` die Seite auch findet, wenn die Suche allein läuft (Test).
_SKILLS = str(Path(__file__).resolve().parent / "skills.py")


def _link_skills() -> None:
    """``st.page_link`` kennt nur Seiten, die ``st.navigation`` registriert hat; läuft die Seite
    allein (Rauchtest), fehlt der Link eben."""
    from streamlit.errors import StreamlitAPIException
    try:
        st.page_link(_SKILLS, label=t("suche.einstellen"), icon=":material/tune:")
    except (StreamlitAPIException, KeyError):
        pass


st.set_page_config(page_title=t("suche.title"), page_icon=":material/manage_search:", layout="wide")
st.title(t("suche.title"))
st.caption(t("suche.subtitle"))

art = st.segmented_control(
    t("suche.strategie_label"),
    options=list(STRATEGIEN),
    format_func=lambda a: t(f"suche.art_{a}"),
    default="frei",
    key="suche_art",
    label_visibility="collapsed",
) or "frei"
bereich, teil, pflicht = STRATEGIEN[art]
skills = get_skills_repo().get_by_area(bereich)
_EIGENE = t("search_chat.custom_skill")
namen = [s.name for s in skills] + ([_EIGENE] if art in _MIT_EIGENER else [])

if not namen:
    st.info(t("suche.banner_leer").format(art=t(f"suche.art_{art}")))
    _link_skills()
    st.stop()

# ------------------------------------------------------------------
# Suchfeld: Anfrage, Skill, Stern
# ------------------------------------------------------------------

laeuft = getattr(teil, "laeuft", lambda: False)()
feld, wahl, knopf = st.columns([6, 3, 1.3], vertical_alignment="bottom")
with feld:
    anfrage = st.text_input(
        t(f"suche.feld_{art}"), placeholder=t(f"suche.platzhalter_{art}"),
        key=f"suche_anfrage_{art}", disabled=laeuft,
    ).strip()
with wahl:
    gewaehlt = st.selectbox(t("suche.skill_label"), namen, key=f"suche_skill_{art}", disabled=laeuft)
with knopf:
    los = ki_knopf(t(f"suche.los_{art}"), wo="cloud", key=f"suche_los_{art}", type="primary",
                   disabled=laeuft, width="stretch")
skill = next((s for s in skills if s.name == gewaehlt), None)

eigene = ""
if skill is None:
    eigene = st.text_area(t("search_chat.custom_skill_label"),
                          placeholder=t("search_chat.custom_skill_placeholder"),
                          height=100, key=f"suche_eigene_{art}").strip()

# Banner: womit gesucht wird, und wo man es einstellt.
satz, link = st.columns([6, 1.3], vertical_alignment="center")
with satz:
    if skill is not None:
        st.markdown(t("suche.banner").format(art=t(f"suche.art_{art}"), skill=skill.name))
        st.caption(skill.prompt[:200] + ("…" if len(skill.prompt) > 200 else ""))
    else:
        st.markdown(t("suche.banner_eigene"))
with link:
    _link_skills()

_modell = teil.modell()
denken = False
if supports_effort(_modell):
    denken = st.toggle("Extended Thinking", value=False, key="suche_denken",
                       help="Adaptive thinking — bessere Query-Planung, mehr Tokens")
cloud_notice(_modell, "claude")

if los:
    if pflicht and not anfrage:
        st.error(t(f"suche.pflicht_{art}"))
    elif skill is None and not eigene:
        st.error(t("search_chat.no_focus_error"))
    else:
        teil.starten(skill, anfrage, eigene, denken)

st.divider()
teil.lauf()
