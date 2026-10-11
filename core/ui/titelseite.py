"""Die Titelseite: ein Titel aus Depot oder Watchlist, erreicht über seine Kachel.

Eine lange Seite mit festen Abschnitten (Erik, 11.10.2026, Fassung A). Oben steht der Kopf der
Kachel mit demselben Satz, dann je Abschnitt erst ein Satz, die Zahlen im Klapper. Die
Reihenfolge hängt an der Art: Im Depot zuerst der Kurs (man besitzt den Titel), auf der
Watchlist zuerst die Urteile (man entscheidet über ihn). Unter dem Kurschart liegt auf derselben
Zeitachse das Urteilsband -- je Check, welches Urteil wann galt (``core/titelseite.py``).

Die Seite rechnet nichts Neues und startet von selbst keinen Check; nur der Knopf der
Watchlist holt die Checks eines Titels neu, wie bisher.
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
from core.kacheln import DEPOT_AGENTEN, WATCHLIST_AGENTEN
from core.tagesbild import prozent
from core.titelseite import (FARBE, FARBE_SONST, band, kurs_veraenderung, news_abschnitt,
                             symbol, urteile_zaehlen)
from core.ui import kacheln as kachel_ui
from core.ui.ki import ki_knopf
from core.ui.markdown import llm_markdown
from core.ui.verdicts import VERDICT_CONFIGS, verdict_badge
from core.ui.vorauswahl import vorauswahl

#: Woher ältere Seiten die Position per ``st.switch_page`` mitgeben (Research-Antworten).
SITZUNG = {"depot": "pd_preselect_position_id", "watchlist": "wla_preselect_pos_id"}

ABSCHNITTE = {
    "depot": ("kurs", "urteile", "nachkaufen", "nachrichten", "recherche"),
    "watchlist": ("urteile", "kurs", "nachrichten", "recherche"),
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
    agenten = DEPOT_AGENTEN if art == "depot" else WATCHLIST_AGENTEN
    strecken = band(get_analyses_repo().get_for_position(position.id, limit=1000), agenten, von, heute)
    if not verlauf and not strecken:
        return

    st.plotly_chart(_chart(verlauf, strecken, agenten, von, heute), key="ts-chart")
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
            line=dict(color="#0018A8", width=2), name=t("market_data.price_col"),
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
    agenten = DEPOT_AGENTEN if art == "depot" else WATCHLIST_AGENTEN
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

    # Auch im Depot (11.10.2026): Seit die Seiten der einzelnen Checks ausgeblendet sind, ist das
    # der einzige Weg, einen Depot-Titel ausser der Reihe zu pruefen.
    _checks_erneuern(position, jeweils)


def _checks_erneuern(position, jeweils: dict) -> None:
    """Alle fünf Cloud-Checks für diesen Titel neu, parallel -- in Depot und Watchlist."""
    from config import config
    from core.background_jobs import (run_capital_allocator_job, run_consensus_gap_job,
                                      run_devils_advocate_job, run_fundamental_job,
                                      run_storychecker_job)

    jetzt = datetime.now(timezone.utc)

    def alt(u) -> bool:
        if u is None or u.created_at is None:
            return True
        erstellt = u.created_at if u.created_at.tzinfo else u.created_at.replace(tzinfo=timezone.utc)
        return (jetzt - erstellt).days >= 7

    jobs = [run_storychecker_job, run_consensus_gap_job, run_fundamental_job,
            run_capital_allocator_job, run_devils_advocate_job]
    agenten = ("storychecker", "consensus_gap", "fundamental_analyzer", "capital_allocator", "devils_advocate")
    veraltet = sum(alt(jeweils.get(a)) for a in agenten)
    label = (t("titelseite.checks_erneuern_alt").format(n=veraltet) if veraltet
             else t("titelseite.checks_erneuern"))
    if not ki_knopf(label, wo="cloud", key="ts-checks", type="primary" if veraltet else "secondary"):
        return

    sprache = current_language()
    zustaende = []
    for job in jobs:
        z = {"running": True, "done": False, "count": 0, "error": None}
        threading.Thread(target=job, daemon=True, args=(
            [position], sprache, z, config.DB_PATH, config.ENCRYPTION_KEY, config.LLM_API_KEY,
        )).start()
        zustaende.append(z)
    with st.spinner(t("watchlist_checker.running_parallel_spinner").format(n=len(jobs))):
        while any(z["running"] for z in zustaende):
            time.sleep(1)
    fehler = [z["error"] for z in zustaende if z["error"]]
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
    laeufe = get_news_repo().list_runs(limit=1)
    if not laeufe:
        st.markdown(t("titelseite.news_keiner"))
        return
    lauf = laeufe[0]
    datum = fmt_date(lauf.created_at) if lauf.created_at else "?"
    abschnitt = news_abschnitt(lauf.result, position.ticker)
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
# Die Seite
# ------------------------------------------------------------------

def seite(art: str) -> None:
    """Die Titelseite für ``art`` = "depot" oder "watchlist"; die Position kommt aus der
    Adresse (``?position=&check=``) oder aus der Sitzung."""
    from state import get_portfolio_service

    st.markdown(kachel_ui.CSS + CSS, unsafe_allow_html=True)
    pid, offener_check = vorauswahl(SITZUNG[art])
    dienst = get_portfolio_service()
    alle = dienst.get_portfolio_positions() if art == "depot" else dienst.get_watchlist_positions()
    position = next((p for p in alle if p.id == pid), None) if pid is not None else None

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
