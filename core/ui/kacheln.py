"""Die Kachel-Ansicht: Depot und Watchlist als Raster, in der Gestalt der Serien-Watchlist.

Oben ein Kopf in der Farbe der Anlageklasse mit dem Namen als Absprung in die Analyse,
darunter Anlageart und Ticker; dieselbe Farbe läuft als Streifen an der linken Kante (Logos
bräuchten einen Lizenzgeber; die Farbe steht je Klasse in ``config/asset_classes.yaml`` und
ist überall in der App dieselbe). Darunter Chips für die Zahlen, der eine Satz als Notiz mit
fester Höhe (lange Sätze scrollen) und je Check ein Kästchen, das zu genau diesem Check springt. Was auf der Kachel steht und in welcher Reihenfolge, entscheidet ``core.kacheln``.

Alles, was aus der Datenbank kommt (Namen, Sätze der Checker), geht durch ``html.escape``,
bevor es in ``unsafe_allow_html`` landet — die Sätze stammen von einem Sprachmodell, das
Webseiten gelesen hat. Titel und Kästchen sind ``st.page_link``: Streamlit setzt ihren Text
selbst, als Text.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path
from typing import Optional

import streamlit as st

from core.i18n import fmt_date, t
from core.kacheln import Kachel, Urteil, kachel, sortiert
from core.tagesbild import prozent
from core.ui.verdicts import VERDICT_CONFIGS

#: Wohin Titel und Kästchen springen. Die Zielseiten lesen ``?position=…&check=…``
#: (core/ui/vorauswahl.py) und klappen den angeklickten Check auf.
#: Absolute Pfade: Streamlit loest einen Seitenpfad relativ zur Einstiegsdatei auf (app.py),
#: ein absoluter bleibt absolut -- so findet ``st.page_link`` die Seite auch im Test.
_SEITEN = Path(__file__).resolve().parents[2] / "pages"
ANALYSE = {"depot": str(_SEITEN / "position_dashboard.py"), "watchlist": str(_SEITEN / "watchlist_analysis.py"),
           "kandidaten": str(_SEITEN / "kandidat.py")}
#: Zurück von der Titelseite auf die Kacheln; die Kandidaten stehen auf der Suche.
KACHELN = {"depot": str(_SEITEN / "kacheln_depot.py"), "watchlist": str(_SEITEN / "kacheln_watchlist.py"),
           "kandidaten": str(_SEITEN / "suche.py")}

_SPALTEN = 3
_FARBE_SONST = "#5E6B7A"

# Linienfarbe der Notiz je Grund (wie die Ampel der Startseite: rot, gelb, ohne).
_NOTIZ = {"gefaehrdet": "rot", "bewegung": "gelb", "geprueft": "", "nie": "leer"}

CSS = """
<style>
.wk-einl { color: #5B6372; margin: -0.4rem 0 0.2rem; max-width: 80ch; }
.wk-zaehler { color: #5B6372; font-size: 0.85rem; margin-bottom: 0.8rem; }
div[class*="st-key-wk-karte-"] { border: 1px solid #D6DAE3; border-left-width: 5px;
  border-radius: 4px; background: #FFFFFF; padding: 0 12px 10px; gap: 0.45rem; overflow: hidden; }
div[class*="st-key-wk-kopf-"] { margin: 0 -12px; padding: 8px 12px 9px; gap: 0; }
div[class*="st-key-wk-kopf-"] [data-testid="stPageLink-NavLink"] { padding: 0; }
div[class*="st-key-wk-kopf-"] [data-testid="stPageLink-NavLink"] p { font-weight: 600;
  font-size: 1rem; color: #FFFFFF; line-height: 1.3; }
div[class*="st-key-wk-kopf-"] [data-testid="stPageLink-NavLink"]:hover p { text-decoration: underline; }
/* Streamlit gibt jedem Markdown-Block -1rem Abstand nach unten; in der Kachel rechnete der Kopf
   seine Hoehe darum eine Zeile zu knapp, und die letzte Zeile ragte ueber den Farbbalken. */
div[class*="st-key-wk-karte-"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
/* Lange Namen umbrechen statt mit "..." abschneiden; der Kopf waechst mit. */
div[class*="st-key-wk-kopf-"] [data-testid="stPageLink-NavLink"] * { white-space: normal !important;
  overflow: visible !important; text-overflow: clip !important; }
.wk-unter { color: rgba(255, 255, 255, 0.82); font-size: 0.72rem; letter-spacing: 0.04em; }
.wk-unter b { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-weight: 600; }
.wk-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 7px; }
.wk-chip { font-size: 0.74rem; padding: 1px 7px; border-radius: 3px; background: #F2F4F8;
  white-space: nowrap; font-variant-numeric: tabular-nums; }
.wk-chip.plus { color: #1A7F4B; } .wk-chip.minus { color: #C0262D; }
.wk-notiz { font-size: 0.86rem; line-height: 1.4; padding-left: 9px; border-left: 2px solid #D6DAE3;
  overflow-wrap: anywhere; max-height: calc(4 * 1.4em); overflow-y: auto; }
.wk-notiz.rot { border-left-color: #C0262D; } .wk-notiz.gelb { border-left-color: #B26A00; }
.wk-notiz.leer { color: #8A92A3; font-style: italic; }
.wk-quelle { color: #8A92A3; font-size: 0.74rem; margin-top: 4px; }
div[class*="st-key-wk-urteile-"] { gap: 4px !important; margin-top: 4px; }
div[class*="st-key-wk-urteile-"] [data-testid="stPageLink-NavLink"] { border: 1px solid #D6DAE3;
  border-radius: 3px; padding: 1px 7px; background: #FFFFFF; }
div[class*="st-key-wk-urteile-"] [data-testid="stPageLink-NavLink"]:hover { border-color: #0018A8; }
div[class*="st-key-wk-urteile-"] [data-testid="stPageLink-NavLink"] p { font-size: 0.74rem;
  color: #3A4150; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
"""


def _agent(agent: str) -> str:
    return t(f"kacheln.agent_{agent}")


def _verdict_eintrag(u: Urteil) -> tuple[str, str]:
    """(Symbol, Wort) aus VERDICT_CONFIGS; die ASCII-Schreibweise des Storycheckers findet
    dort ihren Umlaut-Schlüssel."""
    config = VERDICT_CONFIGS.get(u.agent, {})
    verdict = u.verdict or ""
    if verdict not in config:
        verdict = verdict.replace("ae", "ä").replace("oe", "ö").replace("ue", "ü")
    return config.get(verdict, ("⚪", u.verdict or "—"))


def urteil_label(u: Urteil) -> str:
    """Der Text eines Kästchens, als halber Satz: "Story gefährdet", "Konsens stabil". Das Urteil
    klein, ausser es traegt selbst Grossbuchstaben ("Fair Value") -- dann ist es ein Begriff."""
    wort = _verdict_eintrag(u)[1]
    if wort[1:] == wort[1:].lower():
        wort = wort[:1].lower() + wort[1:]
    return f"{_agent(u.agent)} {wort}"


def urteile_sortiert(k: Kachel) -> list[Urteil]:
    """Die Kästchen nach ihrem Text — so stehen sie auf jeder Kachel an derselben Stelle."""
    return sorted(k.urteile, key=lambda u: urteil_label(u).lower())


def ziel(art: str, agent: Optional[str] = None) -> str:
    """Die Seite, auf die Titel (agent=None) oder Kästchen springen: die Titelseite, die mit
    ``check`` den angeklickten Check aufklappt."""
    return ANALYSE[art]


def farbe(anlageklasse: str) -> str:
    from core.asset_class_config import get_asset_class_registry
    cfg = get_asset_class_registry().get(anlageklasse)
    return cfg.farbe if cfg else _FARBE_SONST


_HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def farbe_css(k: Kachel, hintergrund: str) -> str:
    """Kopf und Streifen dieser einen Kachel in der Farbe ihrer Klasse. Die Farbe kommt aus der
    YAML-Datei; was nicht wie #RRGGBB aussieht, kommt nicht ins CSS."""
    if not _HEX.fullmatch(hintergrund):
        hintergrund = _FARBE_SONST
    i = int(k.position_id)
    return (f"<style>div.st-key-wk-kopf-{i} {{ background: {hintergrund}; }} "
            f"div.st-key-wk-karte-{i} {{ border-left-color: {hintergrund}; }}</style>")


def unter_html(k: Kachel) -> str:
    """Die Zeile unter dem Namen: Anlageart und Ticker."""
    ticker = f" · <b>{escape(k.ticker)}</b>" if k.ticker else ""
    return f'<div class="wk-unter">{escape(k.klasse)}{ticker}</div>'


def _prozent_chip(wert: Optional[float], zusatz: str) -> str:
    if wert is None:
        return ""
    art = "plus" if wert > 0.005 else "minus" if wert < -0.005 else ""
    return f'<span class="wk-chip {art}">{escape(prozent(wert))} {escape(zusatz)}</span>'


def inhalt_html(k: Kachel) -> str:
    """Chips, Satz und Quelle als HTML. Eigene Funktion, damit die Tests sie ohne Streamlit lesen."""
    chips = [_prozent_chip(k.tag_prozent, t("kacheln.heute")),
             _prozent_chip(k.seit_kauf_prozent, t("kacheln.seit_kauf")),
             _prozent_chip(k.seit_aufnahme_prozent, t("kacheln.seit_aufnahme"))]
    if k.seit_kauf_prozent is None and k.seit_aufnahme_prozent is None and k.kurs_eur is not None:
        kurs = f"{k.kurs_eur:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
        chips.append(f'<span class="wk-chip">{escape(t("kacheln.kurs"))} {kurs} €</span>')
    if k.dividende_prozent:
        rendite = f"{k.dividende_prozent:.1f}".replace(".", ",")
        chips.append(f'<span class="wk-chip">{rendite} % {escape(t("kacheln.dividende"))}</span>')

    if k.grund == "bewegung" and k.bewegung_grund:
        satz = t("kacheln.bewegung_grund").format(prozent=prozent(k.tag_prozent), grund=k.bewegung_grund)
    elif k.grund == "bewegung":
        satz = t("kacheln.bewegung").format(prozent=prozent(k.tag_prozent))
    elif k.grund == "nie":
        satz = t("kacheln.nie")
    else:
        satz = k.satz or t("kacheln.ohne_satz")

    quelle = ""
    if k.grund == "bewegung" and k.bewegung_grund:
        quelle = f'<div class="wk-quelle">{escape(t("kacheln.agent_news"))}</div>'
    elif k.satz_agent and k.grund != "bewegung":
        datum = f", {fmt_date(k.satz_datum)}" if k.satz_datum else ""
        quelle = f'<div class="wk-quelle">{escape(_agent(k.satz_agent))}{escape(datum)}</div>'

    chips_html = "".join(c for c in chips if c)
    return (f'<div class="wk-chips">{chips_html}</div>' if chips_html else "") + \
        f'<div class="wk-notiz {_NOTIZ[k.grund]}">{escape(satz)}</div>{quelle}'


def karte(k: Kachel, art: str, position=None) -> None:
    """Eine Kachel: farbiger Kopf mit Name (Absprung), Anlageart und Ticker; darunter Inhalt,
    die Kästchen der gewählten Checks (auch der nie gelaufenen) und mit ``position`` der Knopf
    "Jetzt checken"."""
    st.markdown(farbe_css(k, farbe(k.anlageklasse)), unsafe_allow_html=True)
    with st.container(key=f"wk-karte-{k.position_id}"):
        with st.container(key=f"wk-kopf-{k.position_id}"):
            st.page_link(ziel(art), label=k.name, query_params={"position": k.position_id})
            st.markdown(unter_html(k), unsafe_allow_html=True)
        st.markdown(inhalt_html(k), unsafe_allow_html=True)
        kaestchen(k, art)
        if position is not None:
            from core.ui.titelseite import jetzt_checken
            jetzt_checken(art, position, {u.agent: u for u in k.urteile},
                          key=f"wk-checken-{k.position_id}", klein=True)


def kaestchen(k: Kachel, art: str) -> None:
    """Je gewaehlter Check ein Kaestchen, das zu genau diesem Check springt."""
    if not (k.urteile or k.nie):
        return
    # Untereinander und volle Breite: alle Kaestchen gleich gross, nie zwei in einer Reihe.
    with st.container(key=f"wk-urteile-{k.position_id}"):
        for u in urteile_sortiert(k):
            st.page_link(
                ziel(art, u.agent), label=urteil_label(u), icon=_verdict_eintrag(u)[0],
                query_params={"position": k.position_id, "check": u.agent}, width="stretch",
            )
        # Blindzeit ist eine Aussage: ein gewaehlter Check, der fuer den Titel nie lief.
        for agent in k.nie:
            st.page_link(
                ziel(art, agent), label=t("kacheln.check_nie").format(check=_agent(agent)),
                icon="⚪", query_params={"position": k.position_id, "check": agent},
                width="stretch",
            )


def kacheln_fuer(art: str, positionen: list) -> list[Kachel]:
    """Die Kacheln zu ``positionen`` (mit Ticker und ID), unsortiert. Auch die Titelseite baut
    ihren Kopf daraus, damit dort derselbe Satz steht wie auf der Kachel."""
    from datetime import date as _date

    from state import (get_analysis_service, get_app_config_repo, get_market_agent, get_market_repo,
                       get_news_repo)
    from core import bewegung
    from core.pruefung import auswahl

    # Nur gespeicherte Bewertungen — die Seite holt keine Kurse (das tun Kachel- und Kurs-Job).
    bewertungen = {
        v.position_id: v
        for v in get_market_agent().get_portfolio_valuation(include_watchlist=True)
        if v.position_id is not None
    }
    markt = get_market_repo()
    analysen = get_analysis_service()
    ids = [p.id for p in positionen]
    agenten = auswahl(get_app_config_repo(), art)
    schwelle = bewegung.schwelle(get_app_config_repo())
    # Der Grund einer starken Bewegung: was der Job kurse heute fuer den Titel gesucht hat.
    gesucht = bewegung.heute_gesucht(get_news_repo().list_runs(limit=30), _date.today())
    je_agent = {a: analysen.get_verdicts(ids, a) for a in agenten}

    kacheln = []
    for p in positionen:
        v = bewertungen.get(p.id)
        vortag = None
        aufnahme = None
        if art == "watchlist" and p.ticker:
            if v is None or v.day_pnl_pct is None:
                vortag = markt.get_prev_close(p.ticker)
            # Gespeicherter Schlusskurs am Aufnahmetag (oder der letzte davor) -- nie geholt.
            aufnahme = markt.get_price_for_date_or_prior(p.ticker, p.added_date.isoformat(), max_days_back=7)
        urteile = {a: je_agent[a][p.id] for a in agenten if p.id in je_agent[a]}
        lauf = gesucht.get((p.ticker or "").upper())
        kacheln.append(kachel(p, art, v, urteile, vortag, aufnahme, agenten=agenten, schwelle=schwelle,
                              bewegung_grund=bewegung.grund(lauf.result, p.ticker) if lauf else None))
    return kacheln


#: Die Seite mit Story und Portfolio Checker (Pflege).
PORTFOLIO_STORY = str(_SEITEN / "portfolio_narrativ.py")


def _portfolio_satz() -> None:
    """Oben auf dem Depot ein Satz des Portfolio Checkers: das Depot als Ganzes gegen die Story.
    Er laeuft am Ende von "Depot pruefen" oder per Knopf auf der Seite Portfolio-Story."""
    from streamlit.errors import StreamlitAPIException
    from state import get_portfolio_story_repo

    a = get_portfolio_story_repo().get_latest_analysis()
    if a is None:
        satz = t("kacheln.portfolio_nie")
    else:
        satz = t("kacheln.portfolio_satz").format(
            urteil=escape(a.verdict or "?"), satz=escape(a.summary or ""),
            datum=fmt_date(a.created_at) if a.created_at else "?")
    st.markdown(f'<div class="wk-einl">{satz}</div>', unsafe_allow_html=True)
    try:
        st.page_link(PORTFOLIO_STORY, label=t("kacheln.portfolio_link"))
    except (StreamlitAPIException, KeyError):
        pass


def seite(art: str) -> None:
    """Die ganze Seite für ``art`` = "depot" oder "watchlist"."""
    from state import get_portfolio_service

    st.title(t(f"kacheln.titel_{art}"))
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="wk-einl">{escape(t("kacheln.einleitung"))}</div>', unsafe_allow_html=True)

    dienst = get_portfolio_service()
    alle = dienst.get_portfolio_positions() if art == "depot" else dienst.get_watchlist_positions()
    positionen = [p for p in alle if p.ticker and p.id is not None]
    ohne = len(alle) - len(positionen)
    if not positionen:
        st.info(t(f"kacheln.leer_{art}"))
        return

    if art == "depot":
        _portfolio_satz()

    kacheln = sortiert(kacheln_fuer(art, positionen))
    je_id = {p.id: p for p in positionen}

    zahl = {g: sum(1 for k in kacheln if k.grund == g) for g in ("gefaehrdet", "bewegung", "nie")}
    st.markdown(f'<div class="wk-zaehler">{escape(t("kacheln.zaehler").format(**zahl))}</div>',
                unsafe_allow_html=True)
    if ohne:
        st.caption(t("kacheln.ohne_ticker").format(n=ohne))

    # Zeile für Zeile, damit die Kacheln oben auf einer Linie stehen (wie bei den Serien).
    for start in range(0, len(kacheln), _SPALTEN):
        spalten = st.columns(_SPALTEN)
        for spalte, k in zip(spalten, kacheln[start:start + _SPALTEN]):
            with spalte:
                karte(k, art, je_id[k.position_id])
