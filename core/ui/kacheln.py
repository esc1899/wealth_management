"""Die Kachel-Ansicht: Depot und Watchlist als Raster, in der Gestalt der Serien-Watchlist.

Seit 23.10.2026 in Blöcken (Aktien, Geldwerte, Sachwerte; ``core.kacheln.bloecke``): oben je Block
ein Feld mit dem, was in ihm auffällt, und einem Sprung zu ihm; darunter je Block sein Kopf in
der Farbe der Familie und seine Kacheln.

Oben ein Monogramm (Ticker) in der Farbe der Anlageklasse, daneben der Name als Absprung in
die Analyse, darunter Anlageart und Ticker (Logos bräuchten einen Lizenzgeber; die Farbe steht
je Klasse in ``config/asset_classes.yaml`` und ist überall in der App dieselbe). Darunter Chips
für die Zahlen, der eine Satz mit seinem Licht davor (Lotsee-Optik, ``core/ui/optik.py``), mit
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
from core.kacheln import Block, Kachel, Urteil, bloecke, kachel
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

# Das Licht vor dem Satz je Grund (wie die Ampel der Startseite: rot, gelb, ohne, hohl).
_NOTIZ = {"gefaehrdet": "rot", "bewegung": "gelb", "geprueft": "", "nie": "leer", "ohne": ""}

#: Der Kopf eines Blocks: Name in der Farbe der Familie, Linie darunter. Eigenes Stueck, weil auch
#: die Seite Positionen ihre Tabellen damit gliedert.
BLOCK_CSS = """
<style>
.wk-block { display: flex; align-items: baseline; flex-wrap: wrap; gap: 12px; margin: 1.4rem 0 0.4rem;
  padding-bottom: 6px; border-bottom: 2px solid var(--farbe); scroll-margin-top: 4rem; }
.wk-block b { font-size: 1.3rem; font-weight: 700; color: var(--farbe); }
.wk-block span { color: var(--lotsee-text-leise); font-size: 0.85rem; }
</style>
"""

CSS = BLOCK_CSS + """
<style>
.wk-einl { color: var(--lotsee-text-leise); margin: -0.4rem 0 0.2rem; max-width: 80ch; }
/* Oben je Block ein Feld (Fassung B, 23.10.2026): im Licht seiner Farbfamilie, Satz und Marken,
   ein Sprung zum Block. --farbe setzt jedes Feld und jeder Kopf selbst (felder_html, block_kopf_html). */
.wk-felder { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px;
  margin: 0.4rem 0 0.8rem; }
a.wk-feld { display: flex; flex-direction: column; gap: 8px; padding: 14px 16px; text-decoration: none;
  color: var(--lotsee-text); border-radius: var(--lotsee-rundung-karte);
  background: color-mix(in srgb, var(--farbe) 7%, var(--lotsee-flaeche));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--farbe) 25%, var(--lotsee-flaeche)); }
a.wk-feld:hover { box-shadow: 0 0 0 1px var(--farbe); }
.wk-feld-kopf { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
/* Unterstrichen, damit das Feld auch ohne Maus als Sprung erkennbar ist (iPad). */
.wk-feld-name { font-weight: 700; font-size: 1.05rem; color: var(--farbe); text-decoration: underline;
  text-decoration-thickness: 1px; text-underline-offset: 3px; }
.wk-feld-zahl { color: var(--lotsee-text-leise); font-size: 0.8rem; }
.wk-feld-satz { font-size: 0.88rem; line-height: 1.45; }
a.wk-feld.ruhig .wk-feld-satz { color: var(--lotsee-text-leise); }
.wk-marken { display: flex; flex-wrap: wrap; gap: 6px; }
.wk-marke { display: inline-flex; align-items: center; gap: 6px; font-size: 0.74rem; padding: 1px 8px;
  border-radius: var(--lotsee-rundung-chip); background: var(--lotsee-flaeche);
  box-shadow: 0 0 0 1px var(--lotsee-linie); }
.wk-marke::before { content: ""; width: 8px; height: 8px; border-radius: 50%; box-sizing: border-box; }
.wk-marke.rot::before { background: var(--lotsee-zustand-alarm); }
.wk-marke.gelb::before { background: var(--lotsee-zustand-hinweis); }
.wk-marke.leer::before { border: 2px solid var(--lotsee-zustand-blind); }
div[class*="st-key-wk-karte-"] { background: var(--lotsee-flaeche); border-radius: var(--lotsee-rundung-karte);
  box-shadow: 0 1px 2px rgba(11, 30, 45, 0.08), 0 0 0 1px var(--lotsee-linie);
  padding: 14px 16px 12px; gap: 0.5rem; overflow: hidden; }
/* Der Kopf: links das Monogramm in der Farbe der Anlageklasse (Kuerzel und Farbe je Kachel aus
   farbe_css), daneben Name und Zeile darunter. */
div[class*="st-key-wk-kopf-"] { position: relative; padding-left: 52px; min-height: 40px; gap: 0;
  justify-content: center; }
div[class*="st-key-wk-kopf-"]::before { position: absolute; left: 0; top: 50%; transform: translateY(-50%);
  width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center;
  color: #FFFFFF; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.02em; }
div[class*="st-key-wk-kopf-"] [data-testid="stPageLink-NavLink"] { padding: 0; }
div[class*="st-key-wk-kopf-"] [data-testid="stPageLink-NavLink"] p { font-weight: 600;
  font-size: 1rem; color: var(--lotsee-text); line-height: 1.3; }
div[class*="st-key-wk-kopf-"] [data-testid="stPageLink-NavLink"]:hover p { text-decoration: underline; }
/* Streamlit gibt jedem Markdown-Block -1rem Abstand nach unten; in der Kachel rechnete der Kopf
   seine Hoehe darum eine Zeile zu knapp. */
div[class*="st-key-wk-karte-"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
/* Lange Namen umbrechen statt mit "..." abschneiden; der Kopf waechst mit. */
div[class*="st-key-wk-kopf-"] [data-testid="stPageLink-NavLink"] * { white-space: normal !important;
  overflow: visible !important; text-overflow: clip !important; }
.wk-unter { color: var(--lotsee-text-leise); font-size: 0.75rem; }
.wk-unter b { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-weight: 600; }
.wk-chips { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 7px; }
.wk-chip { font-size: 0.74rem; padding: 1px 7px; border-radius: var(--lotsee-rundung-chip);
  background: var(--lotsee-flaeche-leise); white-space: nowrap; font-variant-numeric: tabular-nums; }
.wk-chip.plus { color: var(--lotsee-zustand-plus); } .wk-chip.minus { color: var(--lotsee-zustand-minus); }
/* Der Satz mit seinem Licht davor: rot gefaehrdet, Bernstein Bewegung, grau geprueft, hohl nie
   geprueft (Blindzeit ist eine Aussage). */
.wk-notiz { position: relative; font-size: 0.88rem; line-height: 1.4; padding-left: 20px;
  overflow-wrap: anywhere; max-height: calc(4 * 1.4em); overflow-y: auto; }
.wk-notiz::before { content: ""; position: absolute; left: 1px; top: 0.4em; width: 10px; height: 10px;
  border-radius: 50%; background: var(--lotsee-zustand-ruhig); box-sizing: border-box; }
.wk-notiz.rot::before { background: var(--lotsee-zustand-alarm);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--lotsee-zustand-alarm) 15%, transparent); }
.wk-notiz.gelb::before { background: var(--lotsee-zustand-hinweis);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--lotsee-zustand-hinweis) 20%, transparent); }
.wk-notiz.leer { color: var(--lotsee-text-leise); font-style: italic; }
.wk-notiz.leer::before { background: transparent; border: 2px solid var(--lotsee-zustand-blind); }
.wk-quelle { color: var(--lotsee-text-leise); font-size: 0.74rem; margin-top: 4px; padding-left: 20px; }
div[class*="st-key-wk-urteile-"] { gap: 4px !important; margin-top: 4px; padding-top: 8px;
  border-top: 1px solid var(--lotsee-linie-leise); }
div[class*="st-key-wk-urteile-"] [data-testid="stPageLink-NavLink"] { border: 1px solid var(--lotsee-linie);
  border-radius: var(--lotsee-rundung-cursor); padding: 1px 8px; background: var(--lotsee-flaeche); }
div[class*="st-key-wk-urteile-"] [data-testid="stPageLink-NavLink"]:hover { border-color: var(--lotsee-leit-tief); }
div[class*="st-key-wk-urteile-"] [data-testid="stPageLink-NavLink"] p { font-size: 0.74rem;
  color: var(--lotsee-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
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

#: So viele Titel nennt das Feld eines Blocks mit Namen, der Rest steht als "und n weitere" da.
_FELD_TITEL = 3

# Das Licht einer Marke je Grund, wie vor dem Satz der Kachel.
_MARKE = {"gefaehrdet": "rot", "bewegung": "gelb", "nie": "leer"}


def block_name(block: str) -> str:
    return t(f"kacheln.block_{block}")


def block_farbe(block: str) -> str:
    """Die Farbe der Familie (asset_classes.yaml, ``bloecke``); was nicht wie #RRGGBB aussieht,
    kommt nicht ins CSS."""
    from core.asset_class_config import get_asset_class_registry
    f = get_asset_class_registry().block_farbe(block) or _FARBE_SONST
    return f if _HEX.fullmatch(f) else _FARBE_SONST


def _anker(block: str) -> str:
    return "block-" + re.sub(r"[^a-z0-9]", "", block.lower())


def _positionen(n: int) -> str:
    return t("kacheln.position_eins") if n == 1 else t("kacheln.positionen").format(n=n)


def feld_satz(b: Block) -> str:
    """Der Satz im Feld eines Blocks: die auffaelligen Titel mit Namen, nach Vorrang; ohne sie
    "nichts, was handeln laesst". Klartext -- escaped wird beim Einsetzen."""
    teile = []
    for k in b.auffaellig[:_FELD_TITEL]:
        if k.grund == "gefaehrdet":
            teile.append(t("kacheln.feld_gefaehrdet").format(name=k.name))
        elif k.grund == "bewegung":
            teile.append(t("kacheln.feld_bewegung").format(name=k.name, prozent=prozent(k.tag_prozent)))
        else:
            teile.append(t("kacheln.feld_nie").format(name=k.name))
    if not teile:
        return t("kacheln.feld_ruhig")
    satz = ", ".join(teile)
    if (rest := len(b.auffaellig) - len(teile)) > 0:
        satz += " " + t("kacheln.feld_weitere").format(n=rest)
    return satz + "."


def felder_html(gruppen: list[Block]) -> str:
    """Oben auf der Seite je Block ein Feld: Name, Zahl der Positionen, der Satz und je Grund eine
    Marke; das ganze Feld springt zu seinem Block."""
    felder = []
    for b in gruppen:
        marken = "".join(
            f'<span class="wk-marke {_MARKE[g]}">{escape(t(f"kacheln.marke_{g}").format(n=n))}</span>'
            for g, n in b.zahl.items() if n)
        felder.append(
            f'<a class="wk-feld{"" if b.auffaellig else " ruhig"}" href="#{_anker(b.name)}" '
            f'style="--farbe: {block_farbe(b.name)}">'
            f'<span class="wk-feld-kopf"><span class="wk-feld-name">{escape(block_name(b.name))}</span>'
            f'<span class="wk-feld-zahl">{escape(_positionen(len(b.kacheln)))}</span></span>'
            f'<span class="wk-feld-satz">{escape(feld_satz(b))}</span>'
            + (f'<span class="wk-marken">{marken}</span>' if marken else "") + "</a>")
    return f'<div class="wk-felder">{"".join(felder)}</div>'


def block_kopf(block: str, anzahl: int, anker: bool = True) -> str:
    """Der Kopf eines Blocks mit der Zahl seiner Positionen. ``anker``: das Sprungziel der Felder
    -- nur einmal je Seite, sonst gaebe es dieselbe ID zweimal."""
    ziel = f' id="{_anker(block)}"' if anker else ""
    return (f'<div class="wk-block"{ziel} style="--farbe: {block_farbe(block)}">'
            f'<b>{escape(block_name(block))}</b><span>{escape(_positionen(anzahl))}</span></div>')


def block_kopf_html(b: Block) -> str:
    return block_kopf(b.name, len(b.kacheln))


def monogramm(k: Kachel) -> str:
    """Das Kuerzel im Kopf: der Ticker ohne Boersenendung, hoechstens vier Zeichen (Logos
    braeuchten einen Lizenzgeber). Nur Buchstaben und Ziffern -- es landet in einem CSS-String."""
    roh = (k.ticker or "").split(".")[0] or k.name
    return re.sub(r"[^A-Z0-9]", "", roh.upper())[:4] or "?"


def farbe_css(k: Kachel, hintergrund: str) -> str:
    """Das Monogramm dieser einen Kachel in der Farbe ihrer Klasse. Die Farbe kommt aus der
    YAML-Datei; was nicht wie #RRGGBB aussieht, kommt nicht ins CSS."""
    if not _HEX.fullmatch(hintergrund):
        hintergrund = _FARBE_SONST
    i = int(k.position_id)
    return (f'<style>div.st-key-wk-kopf-{i}::before {{ content: "{monogramm(k)}"; '
            f"background: {hintergrund}; }}</style>")


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
    elif k.grund == "ohne":
        satz = t("kacheln.ohne_checks").format(klasse=k.anlageklasse)
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
    """Eine Kachel: Kopf mit Monogramm, Name (Absprung), Anlageart und Ticker; darunter Inhalt,
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
    from core.pruefung import auswahl, pruefbar

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
                              bewegung_grund=bewegung.grund(lauf.result, p.ticker) if lauf else None,
                              pruefbar=pruefbar(p)))
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


def _heute() -> None:
    """Oben auf dem Depot der Tag (12.10.2026): Erik schaute taeglich zuerst auf der Analyse
    nach ihm. Dieselbe Anzeige wie dort (core/ui/tagesperformance.py), flacher, mit Kursstand."""
    from core.ui import tagesperformance
    from state import get_market_agent

    agent = get_market_agent()
    st.caption(tagesperformance.kursstand(agent.get_latest_fetch_time()))
    tagesperformance.zeigen(agent.get_portfolio_valuation(), hoehe=280)


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
        _heute()
        _portfolio_satz()

    from core.asset_class_config import get_asset_class_registry

    klassen = get_asset_class_registry()
    gruppen = bloecke(kacheln_fuer(art, positionen), klassen.block_von, klassen.bloecke())
    je_id = {p.id: p for p in positionen}

    st.markdown(felder_html(gruppen), unsafe_allow_html=True)
    if ohne:
        st.caption(t("kacheln.ohne_ticker").format(n=ohne))

    for b in gruppen:
        st.markdown(block_kopf_html(b), unsafe_allow_html=True)
        # Zeile für Zeile, damit die Kacheln oben auf einer Linie stehen (wie bei den Serien).
        for start in range(0, len(b.kacheln), _SPALTEN):
            spalten = st.columns(_SPALTEN)
            for spalte, k in zip(spalten, b.kacheln[start:start + _SPALTEN]):
                with spalte:
                    karte(k, art, je_id[k.position_id])
