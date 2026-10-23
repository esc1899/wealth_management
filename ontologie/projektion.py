"""Datenbank und Code als RDF, nur um sie gegen die Formen zu pruefen (22.10.2026).

Kein Export und kein Wissensgraph: Der Graph entsteht im Speicher, wird geprueft und
verworfen. Zwei Quellen:

- `positionen(conn)` liest die Tabelle `positions` roh, nicht ueber das Repository -- die
  Formen sollen sehen, was in der Zeile steht. Verschluesselte Felder bleiben, was sie sind
  (ein Fernet-Token); die Formen fragen bei ihnen nur, ob sie da sind.
- `wege(klassen)` liest aus den Signaturen der Agenten und Dienste, welche Felder einer
  Position sie annehmen koennen (`wm:nimmt`) -- dieselbe Lesart wie der Guard in
  tests/unit/test_architecture_guards.py, nur je Feld statt je Typ.

Nur fuer Tests: Kein Job und keine Seite importiert dieses Modul, und es sieht nie die echte
Datenbank (CLAUDE.md, "Entwicklungs-Sitzungen laufen auf Demo-Daten").
"""

from __future__ import annotations

import inspect
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import RDF, XSD, Graph, Literal, Namespace, URIRef
from rdflib.namespace import SKOS

from core.storage.models import PortfolioStory, Position, PublicPosition

ORDNER = Path(__file__).resolve().parent
WM = Namespace("urn:lotsee:wealth#")
DING = "urn:lotsee:wealth:"

#: Ein Parameter, der ein Feld meint, aber anders heisst. Die Felder der Portfolio-Story heissen
#: mit Vorsatz (`PortfolioStory.story`), damit sie nicht mit der Story einer Position zusammenfallen.
PARAMETER = {
    "existing_story": "story",
    "story_text": "PortfolioStory.story",
    "story_analysis_text": "PortfolioStory.story",
    "target_year": "PortfolioStory.target_year",
    "liquidity_need": "PortfolioStory.liquidity_need",
}

#: Schluessel und Zeitstempel einer Zeile sind kein Inhalt -- sie haben keine Schutzstufe.
OHNE_SCHUTZ = {"id"}
OHNE_SCHUTZ_PORTFOLIO = {"id", "created_at", "updated_at"}

POSITION_FELDER = set(Position.model_fields) - OHNE_SCHUTZ
PORTFOLIO_FELDER = {f"PortfolioStory.{f}" for f in PortfolioStory.model_fields} - {
    f"PortfolioStory.{f}" for f in OHNE_SCHUTZ_PORTFOLIO}

_POSITION = re.compile(r"\bPosition\b")
_PUBLIC = re.compile(r"\bPublicPosition\b")
_PORTFOLIO = re.compile(r"\bPortfolioStory\w*\b")


def ontologie() -> Graph:
    return Graph().parse(ORDNER / "wealth.ttl")


def formen() -> Graph:
    return Graph().parse(ORDNER / "formen.ttl")


def felder(o: Graph) -> dict[str, URIRef]:
    """Name im Code -> Feld der Ontologie."""
    return {str(o.value(f, WM.imCode)): f for f in o.subjects(RDF.type, WM.Feld)}


def begriffe(o: Graph, klasse: URIRef) -> dict[str, URIRef]:
    """Deutsches prefLabel -> Begriff, fuer Anlagetyp, -klasse und -art. Die Labels sind die
    Schreibweise der YAML und der Spalten."""
    return {str(lab): b
            for b in o.subjects(RDF.type, klasse)
            for lab in o.objects(b, SKOS.prefLabel) if lab.language == "de"}


def _begriff(tabelle: dict[str, URIRef], wert) -> URIRef | None:
    """Ein Wert, den die Ontologie nicht kennt, wird ein unbekannter Begriff -- dann schlaegt
    `sh:class` an, statt dass die Zeile still verschwindet."""
    if wert is None or wert == "":
        return None
    slug = re.sub(r"[^A-Za-z0-9]+", "-", str(wert))
    return tabelle.get(wert) or WM[f"unbekannt-{slug}"]


def _setze(g: Graph, s, p, o) -> None:
    if o is not None and o != "":
        g.add((s, p, o if isinstance(o, (URIRef, Literal)) else Literal(o)))


# --- Die Positionen -------------------------------------------------------------------------------


def positionen(conn: sqlite3.Connection, quelle: str = "db", o: Graph | None = None) -> Graph:
    """Je Zeile in `positions` ein Titel und eine Position, typisiert nach Depot, Watchlist
    oder Kandidat. `quelle` trennt zwei Datenbanken im selben Graphen -- beide zaehlen ab 1."""
    o = ontologie() if o is None else o
    klassen, typen, arten = (begriffe(o, WM.Anlageklasse), begriffe(o, WM.Anlagetyp),
                             begriffe(o, WM.Anlageart))
    g = Graph()
    g.bind("wm", WM)
    alte_fabrik, conn.row_factory = conn.row_factory, sqlite3.Row
    try:
        zeilen = conn.execute("SELECT * FROM positions").fetchall()
    finally:
        conn.row_factory = alte_fabrik
    for r in zeilen:
        t = URIRef(f"{DING}{quelle}:titel:{r['id']}")
        p = URIRef(f"{DING}{quelle}:position:{r['id']}")
        g.add((t, RDF.type, WM.Titel))
        _setze(g, t, WM.name, r["name"])
        for spalte, eig in (("isin", WM.isin), ("wkn", WM.wkn), ("ticker", WM.ticker)):
            _setze(g, t, eig, r[spalte])
        _setze(g, t, WM.anlageklasse, _begriff(klassen, r["asset_class"]))
        _setze(g, t, WM.anlagetyp, _begriff(typen, r["investment_type"]))
        _setze(g, t, WM.anlageart, _begriff(arten, r["anlageart"]))

        im_depot, auf_watchlist = bool(r["in_portfolio"]), bool(r["in_watchlist"])
        g.add((p, RDF.type, WM.Position))
        if im_depot:
            g.add((p, RDF.type, WM.Depotposition))
        if auf_watchlist:
            g.add((p, RDF.type, WM.WatchlistEintrag))
        if not (im_depot or auf_watchlist):
            g.add((p, RDF.type, WM.Kandidat))
        g.add((p, WM.zuTitel, t))
        g.add((p, WM.imDepot, Literal(im_depot)))
        g.add((p, WM.aufWatchlist, Literal(auf_watchlist)))
        for spalte, eig in (("story", WM.story), ("story_skill", WM.storySkill),
                            ("empfehlung", WM.empfehlung), ("recommendation_source", WM.empfehler),
                            ("strategy", WM.strategie), ("unit", WM.einheit),
                            ("quantity", WM.stueckzahl), ("purchase_price", WM.kaufpreis),
                            ("notes", WM.notiz), ("extra_data", WM.zusatzangaben)):
            _setze(g, p, eig, r[spalte])
        for spalte, eig in (("added_date", WM.aufgenommenAm), ("purchase_date", WM.kaufdatum)):
            if r[spalte]:
                g.add((p, eig, Literal(r[spalte], datatype=XSD.date)))
    return g


# --- Die Wege -------------------------------------------------------------------------------------


def _anmerkung(a) -> str:
    return a if isinstance(a, str) else str(a)


def genommene_felder(klasse: type) -> set[str]:
    """Die Felder, die die oeffentlichen Methoden einer Klasse annehmen koennen: alle aus
    `PublicPosition`, `Position` oder der Portfolio-Story (auch ihre Analyse), wenn ein
    Parameter so getypt ist, sonst einzeln ueber den Namen des Parameters (`ticker`,
    `existing_story`, `liquidity_need`)."""
    da: set[str] = set()
    for name, methode in inspect.getmembers(klasse, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        for pname, param in inspect.signature(methode).parameters.items():
            text = "" if param.annotation is inspect.Parameter.empty else _anmerkung(param.annotation)
            if _PUBLIC.search(text):
                da |= set(PublicPosition.model_fields) - OHNE_SCHUTZ
            elif _POSITION.search(text):
                da |= POSITION_FELDER
            elif _PORTFOLIO.search(text):
                da |= PORTFOLIO_FELDER
            elif (feld := PARAMETER.get(pname, pname)) in POSITION_FELDER | PORTFOLIO_FELDER:
                da.add(feld)
    return da


def wege(klassen: list[type], o: Graph | None = None) -> Graph:
    """Je Klasse, was sie nimmt. Den Weg selbst (Ort, Ausnahme) kennt die Ontologie."""
    o = ontologie() if o is None else o
    je_name = felder(o)
    g = Graph()
    for k in klassen:
        weg = WM[k.__name__]
        for f in sorted(genommene_felder(k)):
            g.add((weg, WM.nimmt, je_name.get(f) or WM[f"unbekannt-{f}"]))
    return g


# --- Pruefen --------------------------------------------------------------------------------------


@dataclass
class Pruefung:
    erfuellt: bool
    verstoesse: list[tuple[str, str]] = field(default_factory=list)  # (Meldung, Knoten)

    @property
    def satz(self) -> str:
        if self.erfuellt:
            return "Daten und Code erfüllen alle Formen."
        je: dict[str, int] = {}
        for meldung, _ in self.verstoesse:
            je[meldung] = je.get(meldung, 0) + 1
        teile = [f"{n}× {m}" for m, n in sorted(je.items(), key=lambda x: -x[1])]
        return f"{len(self.verstoesse)} Verstöße: " + "; ".join(teile)


def pruefen(*graphen: Graph) -> Pruefung:
    """Die Graphen zusammen mit der Ontologie gegen die Formen. Die Ontologie geht in die Daten:
    Felder und Wege stehen in ihr, und `sh:targetClass wm:Position` trifft ueber ihr
    `rdfs:subClassOf` auch Depot, Watchlist und Kandidat. Ohne RDFS-Inferenz: Sie machte aus
    `rdfs:range` jeden unbekannten Wert zu einem der Klasse, und `sh:class` schluege nie an."""
    from pyshacl import validate

    daten = ontologie()
    for g in graphen:
        daten += g
    sh = Namespace("http://www.w3.org/ns/shacl#")
    erfuellt, bericht, _ = validate(daten, shacl_graph=formen(), ont_graph=None,
                                    inference="none", advanced=True)
    verstoesse = sorted(
        (str(bericht.value(e, sh.resultMessage)), str(bericht.value(e, sh.focusNode)))
        for e in bericht.subjects(RDF.type, sh.ValidationResult)
    )
    return Pruefung(bool(erfuellt), verstoesse)
