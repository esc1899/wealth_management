"""Die Titelseite: ein Titel aus Depot oder Watchlist, erreicht über seine Kachel.

Eine lange Seite mit festen Abschnitten (Erik, 11.10.2026, Fassung A). Oben steht der Kopf der
Kachel mit demselben Satz, dann je Abschnitt erst ein Satz, die Zahlen im Klapper. Die
Reihenfolge hängt an der Art: Im Depot zuerst der Kurs (man besitzt den Titel), auf der
Watchlist zuerst die Urteile (man entscheidet über ihn). Unter dem Kurschart liegt auf derselben
Zeitachse das Urteilsband -- je Check, welches Urteil wann galt (``core/titelseite.py``).

Die Seite rechnet nichts Neues und startet von selbst keinen Check; nur der Knopf "Jetzt
checken" lässt einen Durchgang laufen -- die Auswahl der Liste für diesen Titel, ein Datum
(``core/pruefung.py``). Derselbe Knopf steht auf der Kachel.
"""

from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta, timezone
from html import escape

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from core.i18n import current_language, fmt_date, t
from core.pruefung import pruefbar
from core.tagesbild import prozent
from core.ui import optik
from core.titelseite import (FARBE, FARBE_SONST, band, kurs_veraenderung, news_abschnitt,
                             symbol, urteile_zaehlen)
from core.ui import kacheln as kachel_ui
from core.ui.ki import ki_knopf
from core.ui.markdown import llm_markdown
from core.ui.verdicts import VERDICT_CONFIGS, verdict_badge
from core.ui.vorauswahl import vorauswahl

#: Woher ältere Seiten die Position per ``st.switch_page`` mitgeben (Research-Antworten).
SITZUNG = {"depot": "pd_preselect_position_id", "watchlist": "wla_preselect_pos_id",
           "kandidaten": "kand_preselect_pos_id"}

#: Ein Kandidat hat keinen Kurs und keine Nachrichten (die Jobs holen nur Depot und Watchlist);
#: statt dessen die Entscheidung und woher er kommt -- mit dem Bericht des Laufs.
ABSCHNITTE = {
    "depot": ("kurs", "urteile", "nachkaufen", "nachrichten", "recherche"),
    "watchlist": ("urteile", "kurs", "nachrichten", "recherche"),
    "kandidaten": ("urteile", "entscheidung", "herkunft"),
}

CSS = """
<style>
.ts-kopf { border-radius: 4px 4px 0 0; padding: 12px 16px 10px; margin-bottom: 10px; }
.ts-name { color: #FFFFFF; font-size: 1.45rem; font-weight: 600; line-height: 1.25; }
.ts-kopf .wk-unter { font-size: 0.78rem; }
div.st-key-ts-satz .wk-notiz { max-height: none; font-size: 1rem; }
div.st-key-ts-satz { max-width: 80ch; }
.ts-urteil { font-size: 0.95rem; }
.ts-datum { color: #8A92A3; font-size: 0.8rem; font-variant-numeric: tabular-nums; }
.ts-nie { color: #8A92A3; font-style: italic; }
</style>
"""


def _agent(agent: str) -> str:
    return t(f"kacheln.agent_{agent}")


def _zurueck(art: str) -> None:
    """Der Weg zurück auf die Kacheln. ``st.page_link`` kennt nur Seiten, die ``st.navigation``
    registriert hat; wird die Seite allein geladen (Rauchtests), fehlt der Link eben."""
    from streamlit.errors import StreamlitAPIException
    try:
        st.page_link(kachel_ui.KACHELN[art], label=t(f"titelseite.zurueck_{art}"))
    except (StreamlitAPIException, KeyError):
        pass


def _kopf(k) -> None:
    hintergrund = kachel_ui.farbe(k.anlageklasse)
    if not kachel_ui._HEX.fullmatch(hintergrund):
        hintergrund = kachel_ui._FARBE_SONST
    st.markdown(
        f'<div class="ts-kopf" style="background: {hintergrund}">'
        f'<div class="ts-name">{escape(k.name)}</div>{kachel_ui.unter_html(k)}</div>',
        unsafe_allow_html=True,
    )
    with st.container(key="ts-satz"):
        st.markdown(kachel_ui.inhalt_html(k), unsafe_allow_html=True)


# ------------------------------------------------------------------
# Kurs und Urteilsband
# ------------------------------------------------------------------

def _kurs(art: str, position) -> None:
    from state import get_analyses_repo, get_market_agent

    st.subheader(t("titelseite.kurs"))
    if not position.ticker:
        st.markdown(t("titelseite.ohne_ticker"))
        return

    verlauf = get_market_agent().get_historical(position.ticker, days=365)
    heute = datetime.now(timezone.utc).date()
    jahr, monat = kurs_veraenderung(verlauf), kurs_veraenderung(verlauf, 30)
    if jahr is None:
        st.markdown(t("titelseite.kurs_ohne"))
    elif monat is None:
        st.markdown(t("titelseite.kurs_satz_jahr").format(jahr=prozent(jahr)))
    else:
        st.markdown(t("titelseite.kurs_satz").format(jahr=prozent(jahr), monat=prozent(monat)))

    von = verlauf[0].date if verlauf else heute - timedelta(days=365)
    agenten = auswahl_der_liste(art) if pruefbar(position) else ()
    strecken = band(get_analyses_repo().get_for_position(position.id, limit=1000), agenten, von, heute)
    if not verlauf and not strecken:
        return

    st.plotly_chart(_chart(verlauf, strecken, agenten, von, heute), key="ts-chart")
    if agenten:
        st.caption(t("titelseite.band_hinweis"))


def _chart(verlauf, strecken, agenten, von: date, bis: date) -> go.Figure:
    """Kurs oben, Urteilsband unten -- eine Figur mit geteilter Zeitachse, damit beide im
    selben Massstab stehen."""
    namen = [_agent(a) for a in agenten]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.68, 0.32],
                        vertical_spacing=0.05)
    if verlauf:
        fig.add_trace(go.Scatter(
            x=[h.date for h in verlauf], y=[h.close_eur for h in verlauf], mode="lines",
            line=dict(color=optik.farbe("leit_tief"), width=2), name=t("market_data.price_col"),
            hovertemplate="%{x|%d.%m.%Y}: %{y:,.2f} €<extra></extra>",
        ), row=1, col=1)

    # Unsichtbare Anker, damit jede Zeile steht -- auch die eines Checks, der nie lief.
    fig.add_trace(go.Scatter(x=[von] * len(namen), y=namen, mode="markers", marker=dict(opacity=0),
                             hoverinfo="skip", showlegend=False), row=2, col=1)
    for s in strecken:
        config = VERDICT_CONFIGS.get(s.agent, {})
        zeichen = symbol(s.verdict, config)
        wort = config.get(s.verdict or "", (None, s.verdict or "—"))[1]
        hover = f"{_agent(s.agent)}: {wort} ({fmt_date(s.geprueft_am)})"
        if s.summary:
            hover += "<br>" + escape(s.summary[:140])
        farbe = FARBE.get(zeichen, FARBE_SONST)
        fig.add_trace(go.Scatter(
            x=[s.von, s.bis], y=[_agent(s.agent)] * 2, mode="lines", line=dict(color=farbe, width=14),
            hovertext=hover, hoverinfo="text", showlegend=False,
        ), row=2, col=1)
        if s.geprueft_am >= von:
            fig.add_trace(go.Scatter(
                x=[s.geprueft_am], y=[_agent(s.agent)], mode="markers",
                marker=dict(color="#FFFFFF", size=7, line=dict(color=farbe, width=2)),
                hovertext=hover, hoverinfo="text", showlegend=False,
            ), row=2, col=1)

    fig.update_yaxes(type="category", categoryorder="array", categoryarray=list(reversed(namen)),
                     row=2, col=1)
    fig.update_xaxes(range=[von, bis + timedelta(days=2)])
    fig.update_layout(height=200 + 26 * len(namen), margin=dict(t=10, b=10, l=10, r=10),
                      showlegend=False, hovermode="closest")
    return fig


# ------------------------------------------------------------------
# Urteile
# ------------------------------------------------------------------

def _volltext(analyse) -> str | None:
    """Der lange Text eines Checks: gespeichert an der Analyse oder als letzte Antwort seiner
    Sitzung. Fehlt er (verfallen, nie gespeichert), steht nur der Satz da."""
    if analyse.analysis_text:
        return analyse.analysis_text
    if not analyse.session_id:
        return None
    from state import (get_capital_allocator_repo, get_consensus_gap_agent, get_devils_advocate_repo,
                       get_fundamental_analyzer_agent, get_storychecker_agent)
    quelle = {
        "storychecker": get_storychecker_agent,
        "consensus_gap": get_consensus_gap_agent,
        "fundamental_analyzer": get_fundamental_analyzer_agent,
        "capital_allocator": get_capital_allocator_repo,
        "devils_advocate": get_devils_advocate_repo,
    }.get(analyse.agent)
    if quelle is None:
        return None
    try:
        nachrichten = quelle().get_messages(analyse.session_id)
    except Exception:
        return None
    return next((m.content for m in reversed(nachrichten)
                 if getattr(m, "role", "assistant") == "assistant"), None)


def _urteile(art: str, position, offener_check: str | None) -> None:
    from state import get_analysis_service

    st.subheader(t("titelseite.urteile"))
    if not pruefbar(position):
        st.markdown(t("kacheln.ohne_checks").format(klasse=position.asset_class))
        return
    agenten = auswahl_der_liste(art)
    dienst = get_analysis_service()
    jeweils = {a: dienst.get_verdict(position.id, a) for a in agenten}

    zahl = urteile_zaehlen([symbol(u.verdict, VERDICT_CONFIGS.get(a, {})) if u else None
                            for a, u in jeweils.items()])
    teile = [t(f"titelseite.urteile_{teil}").format(n=zahl[teil])
             for teil in ("positiv", "kritisch", "mitte", "nie") if zahl[teil]]
    st.markdown(t("titelseite.urteile_satz").format(alle=zahl["alle"], teile=", ".join(teile)))

    for agent, u in jeweils.items():
        with st.container(key=f"ts-urteil-{agent}"):
            if u is None:
                st.markdown(f'<div class="ts-urteil"><b>{escape(_agent(agent))}</b> '
                            f'<span class="ts-nie">— {escape(t("titelseite.nie"))}</span></div>',
                            unsafe_allow_html=True)
                continue
            badge = verdict_badge(u.verdict, VERDICT_CONFIGS.get(agent, {}))
            datum = fmt_date(u.created_at) if u.created_at else ""
            st.markdown(f"**{_agent(agent)}** {badge} :gray[· {datum}]")
            if u.summary:
                llm_markdown(f"_{u.summary}_")
            text = _volltext(u)
            if text:
                with st.expander(t("titelseite.volltext"), expanded=offener_check == agent):
                    llm_markdown(text)

    jetzt_checken(art, position, jeweils, key="ts-checks")


def auswahl_der_liste(art: str) -> tuple[str, ...]:
    """Die gewählten Checks der Liste (Einstellungen), in fester Reihenfolge."""
    from core.pruefung import auswahl
    from state import get_app_config_repo
    return auswahl(get_app_config_repo(), art)


def _veraltet(u, jetzt: datetime) -> bool:
    if u is None or u.created_at is None:
        return True
    erstellt = u.created_at if u.created_at.tzinfo else u.created_at.replace(tzinfo=timezone.utc)
    return (jetzt - erstellt).days >= 7


def jetzt_checken(art: str, position, jeweils: dict, key: str, klein: bool = False) -> None:
    """Der Knopf "Jetzt checken": ein Durchgang mit der Auswahl der Liste für diesen Titel
    (``core/background_jobs.py::run_durchgang``). Auf der Titelseite und auf der Kachel;
    ``jeweils`` = je Check das jüngste Urteil oder None. Bei Kandidaten heißt er "Genauer
    prüfen" und zählt als Berührung (die 60 Tage bis "Ignoriert" beginnen neu)."""
    from config import config
    from core.background_jobs import run_durchgang

    agenten = auswahl_der_liste(art)
    if not agenten or not pruefbar(position):
        return
    jetzt = datetime.now(timezone.utc)
    veraltet = sum(_veraltet(jeweils.get(a), jetzt) for a in agenten)
    if art == "kandidaten":
        label = t("kandidaten.genauer_pruefen")
    else:
        label = (t("titelseite.checks_erneuern_alt").format(n=veraltet) if veraltet
                 else t("titelseite.checks_erneuern"))
    if not ki_knopf(label, wo="cloud", key=key,
                    type="primary" if veraltet and not klein else "secondary",
                    width="stretch" if klein else "content"):
        return
    if art == "kandidaten":
        from state import get_kandidaten_repo
        get_kandidaten_repo().beruehren(position.id)

    zustand = {"running": True, "done": False, "count": 0, "error": None}
    threading.Thread(target=run_durchgang, daemon=True, args=(
        position, art, agenten, current_language(), zustand,
        config.DB_PATH, config.ENCRYPTION_KEY, config.LLM_API_KEY,
    )).start()
    with st.spinner(t("titelseite.checks_laufen").format(n=len(agenten), name=position.name)):
        while zustand["running"]:
            time.sleep(1)
    fehler = zustand.get("fehler") or ([zustand["error"]] if zustand["error"] else [])
    for f in fehler:
        st.error(f)
    if not fehler:
        st.toast(t("watchlist_analysis.update_done"), icon="✅")
        st.rerun()


# ------------------------------------------------------------------
# Nachkaufen, Nachrichten, Recherche
# ------------------------------------------------------------------

def _nachkaufen(position) -> None:
    from core.accumulation import accumulation_for_position
    from core.shareholder_yield import cached_buyback_yield_map
    from state import get_analysis_service, get_market_agent

    st.subheader(t("titelseite.nachkaufen"))
    dienst = get_analysis_service()
    renditen = {v.symbol.upper(): v.dividend_yield_pct
                for v in get_market_agent().get_portfolio_valuation(include_watchlist=True) if v.symbol}
    rueckkaeufe = cached_buyback_yield_map((position.ticker,) if position.ticker else ())
    acc = accumulation_for_position(position.ticker, dienst.get_verdict(position.id, "storychecker"),
                                    dienst.get_verdict(position.id, "fundamental_analyzer"),
                                    renditen, rueckkaeufe)
    satz = verdict_badge(acc.verdict, VERDICT_CONFIGS["accumulation"])
    if acc.binding:
        satz += f" — {t(acc.binding)}"
    st.markdown(satz, help=t("accumulation.help"))
    with st.expander(t("titelseite.woraus")):
        st.dataframe(
            [{t("accumulation.comp_col_name"): t(c.name), t("accumulation.comp_col_value"): c.value,
              t("accumulation.comp_col_rating"): c.rating} for c in (acc.engine_parts + acc.components)],
            width="stretch", hide_index=True,
        )


def _nachrichten(position) -> None:
    from state import get_news_repo

    st.subheader(t("titelseite.nachrichten"))
    if not position.ticker:
        st.markdown(t("titelseite.ohne_ticker"))
        return
    laeufe = get_news_repo().list_runs(limit=30)
    if not laeufe:
        st.markdown(t("titelseite.news_keiner"))
        return
    # Der juengste Lauf, der den Titel kennt: ein Digest oder die Suche nach einer starken
    # Bewegung (core/bewegung.py). Bis 11.10.2026 nur der letzte Digest -- der kannte die
    # Uebernahme bei Schneider Electric nicht.
    lauf, abschnitt = next(((l, a) for l in laeufe if (a := news_abschnitt(l.result, position.ticker))),
                           (laeufe[0], None))
    datum = fmt_date(lauf.created_at) if lauf.created_at else "?"
    if not abschnitt:
        st.markdown(t("titelseite.news_nichts").format(datum=datum, ticker=position.ticker))
        return
    zeilen = [z for z in abschnitt.split("\n")[1:] if z.strip()]
    st.markdown(t("titelseite.news_aus").format(datum=datum))
    if zeilen:
        llm_markdown(f"_{zeilen[0].lstrip('- ')}_")
    with st.expander(t("titelseite.news_voll")):
        llm_markdown(abschnitt)


def _recherche(art: str, position) -> None:
    """Antworten aus Claude Code zu diesem Ticker; auf der Watchlist dazu die Recherche, die
    den Titel vorgeschlagen hat. Ohne beides fehlt der Abschnitt."""
    from state import get_cowork_repo, get_research_queue_repo

    if not position.ticker:
        return
    antworten = get_research_queue_repo().list_answers_for_ticker(position.ticker)
    eintraege = []
    if art == "watchlist":
        # Vorschläge kommen meist ohne Börsensuffix (SAP vs. SAP.DE).
        basis = position.ticker.split(".")[0].upper()
        cowork = get_cowork_repo()
        ids = {s.research_id for s in cowork.list_suggestions()
               if s.ticker and s.ticker.split(".")[0].upper() == basis}
        eintraege = sorted((e for rid in ids if (e := cowork.get_by_research_id(rid)) and e.body_markdown),
                           key=lambda e: e.date, reverse=True)
    if not antworten and not eintraege:
        return

    st.subheader(t("titelseite.recherche"))
    if antworten:
        juengste = max((a.created_at or "")[:10] for a in antworten)
        st.markdown(t("titelseite.recherche_satz").format(n=len(antworten), datum=fmt_date(juengste)
                                                         if juengste else "?"))
        for a in antworten:
            with st.expander(f"{(a.created_at or '')[:10]} · {t('research_request.answer_label').format(id=a.id)}"):
                llm_markdown(a.answer_md)
    for e in eintraege:
        st.markdown(t("titelseite.recherche_vorschlag").format(id=e.research_id, datum=fmt_date(e.date)))
        with st.expander(t("titelseite.recherche_lesen")):
            llm_markdown(e.body_markdown)


# ------------------------------------------------------------------
# Nur Kandidaten: Entscheidung und Herkunft
# ------------------------------------------------------------------

def _entscheidung(position) -> None:
    """Ja oder Nein; ist er schon verworfen, steht das da, mit dem Weg zurück."""
    from core import kandidaten
    from core.ui.suche.kandidaten import entscheiden
    from state import get_kandidaten_repo

    st.subheader(t("kandidaten.entscheidung"))
    k = get_kandidaten_repo().get(position.id)
    if k is not None and k.zustand == "verworfen":
        st.markdown(t("kandidaten.ist_verworfen").format(datum=fmt_date(k.entschieden) if k.entschieden else "?"))
        if st.button(t("kandidaten.wieder_aufnehmen"), key="ts-wieder"):
            kandidaten.wieder_aufnehmen(get_kandidaten_repo(), position.id)
            st.rerun()
        return
    st.markdown(t("kandidaten.entscheidung_satz"))
    entscheiden(position.id, key="ts-entscheiden")


def _herkunft(position) -> None:
    """Woher der Kandidat kommt: der Lauf, der ihn fand, mit seinem Bericht; dazu die These."""
    from core.ui.suche.kandidaten import bericht, herkunft
    from state import get_kandidaten_repo

    k = get_kandidaten_repo().get(position.id)
    if k is None:
        return
    st.subheader(t("kandidaten.herkunft"))
    st.markdown(herkunft(k))
    if position.story:
        llm_markdown(f"_{position.story}_")
    b = bericht(k.strategie, k.lauf_id)
    if b is None:
        st.markdown(t("kandidaten.bericht_fehlt"))
        return
    wann, skill, anfrage, texte = b
    zeile = " · ".join(x for x in (fmt_date(wann) if wann else None, skill, anfrage) if x)
    with st.expander(t("kandidaten.bericht").format(lauf=zeile)):
        for text in texte:
            llm_markdown(text)
        st.caption(t("common.ai_disclaimer"))


# ------------------------------------------------------------------
# Die Seite
# ------------------------------------------------------------------

def _position(art: str, pid: int):
    """Die Position, wenn sie zur Art gehört: im Depot, auf der Watchlist oder offener bzw.
    verworfener Kandidat."""
    from state import get_kandidaten_repo, get_portfolio_service, get_positions_repo

    if art == "kandidaten":
        k = get_kandidaten_repo().get(pid)
        p = get_positions_repo().get(pid) if k is not None and k.zustand != "uebernommen" else None
        return p if p is not None and not (p.in_portfolio or p.in_watchlist) else None
    dienst = get_portfolio_service()
    alle = dienst.get_portfolio_positions() if art == "depot" else dienst.get_watchlist_positions()
    return next((p for p in alle if p.id == pid), None)


def seite(art: str) -> None:
    """Die Titelseite für ``art`` = "depot" oder "watchlist"; die Position kommt aus der
    Adresse (``?position=&check=``) oder aus der Sitzung."""
    st.markdown(kachel_ui.CSS + CSS, unsafe_allow_html=True)
    pid, offener_check = vorauswahl(SITZUNG[art])
    position = _position(art, pid) if pid is not None else None

    _zurueck(art)
    if position is None:
        st.title(t("titelseite.ohne_titel"))
        st.markdown(t(f"titelseite.ohne_titel_{art}"))
        return

    k = kachel_ui.kacheln_fuer(art, [position])[0]
    _kopf(k)
    for abschnitt in ABSCHNITTE[art]:
        if abschnitt == "kurs":
            _kurs(art, position)
        elif abschnitt == "urteile":
            _urteile(art, position, offener_check)
        elif abschnitt == "nachkaufen":
            _nachkaufen(position)
        elif abschnitt == "nachrichten":
            _nachrichten(position)
        elif abschnitt == "recherche":
            _recherche(art, position)
        elif abschnitt == "entscheidung":
            _entscheidung(position)
        elif abschnitt == "herkunft":
            _herkunft(position)
