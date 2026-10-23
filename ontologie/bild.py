"""Die Ontologie als Bild (22.10.2026, Erik): nicht die Daten, sondern ihr Schema.

Eine Kopie des Gedankens aus Serien (`serien-empfehler/ontologie/bild.py`), kein Import, mit
zwei Zusaetzen fuer Wealth: Jedes Feld traegt im Kasten das Zeichen seiner Schutzstufe
(○ oeffentlich, ◐ watchlist-artig, ● privat, 🔒 verschluesselt), und was FIBO dazu sagt,
steht als gestrichelter Pfeil zu einem grauen Kasten (`skos:closeMatch`).

Liest `wealth.ttl` und `formen.ttl` und gibt Knoten und Kanten zurueck; gezeichnet wird in
`core/ui/ontologie_bild.py` fuer die Seite "Ontologie" unter Einstellungen. Nichts ist hier
nachgezeichnet. Nennt eine Form einen Begriff, den die Ontologie nicht kennt, steht er in
`unbekannt` und als roter Kasten im Bild. Keine Datenbank: Das Bild prueft nichts, das tut
`tests/integration/test_ontologie.py`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from rdflib import OWL, RDF, RDFS, BNode, Graph, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import SH, SKOS

ORDNER = Path(__file__).resolve().parent
WM = Namespace("urn:lotsee:wealth#")
FIBO = "https://spec.edmcouncil.org/fibo/ontology/"
#: Vorsilben, unter denen das Bild fremde Begriffe kurz schreibt.
KURZ = {str(SKOS): "skos:", str(WM): ""}

ZEICHEN = {WM.oeffentlich: "○", WM.watchlistArtig: "◐", WM.privat: "●"}
SCHLOSS = "🔒"

#: Saetze des Bildes, je Sprache. Die Seite selbst nimmt ihre Texte aus translations/.
TEXT = {
    "de": {"ist_ein": "ist ein", "entspricht": "entspricht (FIBO)", "regeln": "Regeln",
           "begriffe": "Begriffe", "fibo": "In FIBO", "unbekannt": "unbekannt",
           "fehlt": "Eine Form nennt diesen Begriff, die Ontologie kennt ihn nicht.",
           "ausnahme": "Ausnahme"},
    "en": {"ist_ein": "is a", "entspricht": "matches (FIBO)", "regeln": "rules",
           "begriffe": "Terms", "fibo": "In FIBO", "unbekannt": "unknown",
           "fehlt": "A shape names this term, the ontology does not know it.",
           "ausnahme": "exception"},
}


def ontologie() -> Graph:
    return Graph().parse(ORDNER / "wealth.ttl")


def formen() -> Graph:
    return Graph().parse(ORDNER / "formen.ttl")


def kurz(iri) -> str:
    s = str(iri)
    if s.startswith(FIBO):
        return "fibo:" + s.rstrip("/").rsplit("/", 1)[-1]
    for lang, vorsilbe in KURZ.items():
        if s.startswith(lang):
            return vorsilbe + s[len(lang):]
    return s


def _wm(t) -> bool:
    return isinstance(t, URIRef) and str(t).startswith(str(WM))


def bekannt(o: Graph) -> set[URIRef]:
    return {s for s in o.subjects() if _wm(s)}


def genannt(f: Graph) -> set[URIRef]:
    """Was die Formen aus `wm:` nennen, auch im Text ihrer SPARQL-Abfragen; die Namen der
    Formen selbst (`…Form`) sind keine Begriffe."""
    da = {t for t in f.all_nodes() if _wm(t)}
    for abfrage in f.objects(None, SH.select):
        da |= {WM[n] for n in re.findall(r"\bwm:(\w+)", str(abfrage))}
    return {t for t in da if not str(t).endswith("Form")}


def unbekannte_begriffe(o: Graph, f: Graph) -> list[str]:
    return sorted(kurz(t) for t in genannt(f) - bekannt(o))


def _wort(o: Graph, k, lang: str, *eigenschaften) -> str:
    """Das Label in der Sprache, sonst deutsch, sonst die Kurzform."""
    for eig in eigenschaften or (RDFS.label, SKOS.prefLabel):
        werte = list(o.objects(k, eig))
        for sprache in (lang, "de"):
            for w in werte:
                if getattr(w, "language", None) == sprache:
                    return str(w)
    return kurz(k)


def _kommentar(o: Graph, k, lang: str) -> str:
    werte = list(o.objects(k, RDFS.comment)) + list(o.objects(k, SKOS.definition))
    for sprache in (lang, "de"):
        for w in werte:
            if getattr(w, "language", None) == sprache:
                return str(w)
    return ""


def _klassen_in(o: Graph, k) -> list:
    if isinstance(k, BNode) and (liste := o.value(k, OWL.unionOf)) is not None:
        return list(Collection(o, liste))
    return [] if k is None else [k]


def domaenen(o: Graph, p) -> list:
    return _klassen_in(o, o.value(p, RDFS.domain))


def _darunter(g: Graph, knoten) -> set:
    gesehen, rand = {knoten}, [knoten]
    while rand:
        k = rand.pop()
        for x in g.objects(k, None):
            if not isinstance(x, URIRef) and x not in gesehen and (x, None, None) in g:
                gesehen.add(x)
                rand.append(x)
    return gesehen


def formen_je_klasse(o: Graph, f: Graph) -> dict[URIRef, list[str]]:
    """Die Meldungen der Formen nach der Klasse, fuer die sie gelten (`sh:targetClass`)."""
    je: dict[URIRef, list[str]] = {}
    for form in f.subjects(RDF.type, SH.NodeShape):
        ziele = list(f.objects(form, SH.targetClass))
        for p in f.objects(form, SH.targetSubjectsOf):
            ziele += domaenen(o, p)
        meldungen = sorted({str(m) for s in _darunter(f, form) for m in f.objects(s, SH.message)})
        for z in ziele:
            je.setdefault(z, []).extend(m for m in meldungen if m not in je.get(z, []))
    return je


def _absaetze(*teile: str) -> str:
    return "\n\n".join(t for t in teile if t)


def _in_zeilen(woerter: list[str], je: int = 4) -> list[str]:
    return [" | ".join(woerter[i:i + je]) for i in range(0, len(woerter), je)]


def _feldzeile(o: Graph, p, lang: str) -> str:
    zeichen = ZEICHEN.get(o.value(p, WM.schutz), "·")
    schloss = f" {SCHLOSS}" if str(o.value(p, WM.verschluesselt)).lower() == "true" else ""
    return f"{zeichen} {_wort(o, p, lang)}{schloss}"


def wege_je_ort(o: Graph, lang: str = "de") -> list[dict[str, Any]]:
    """Die Wege zu einem Modell nach Ort, fuer den Klapper der Seite."""
    orte = []
    for ort in (WM.cloud, WM.lokal, WM.ohneModell):
        wege = sorted(o.subjects(WM.laeuftBei, ort), key=lambda w: _wort(o, w, lang))
        orte.append({"ort": _wort(o, ort, lang), "erklaerung": _kommentar(o, ort, lang),
                     "wege": [{"name": _wort(o, w, lang), "code": str(o.value(w, WM.imCode)),
                               "ausnahme": str(o.value(w, WM.ausnahme) or "")} for w in wege]})
    return orte


def felder_je_stufe(o: Graph, lang: str = "de") -> list[dict[str, Any]]:
    """Die Felder einer Position nach Schutzstufe, fuer den Klapper der Seite."""
    stufen = []
    for stufe in (WM.oeffentlich, WM.watchlistArtig, WM.privat):
        felder = sorted(o.subjects(WM.schutz, stufe), key=lambda p: _wort(o, p, lang))
        stufen.append({"stufe": f"{ZEICHEN[stufe]} {_wort(o, stufe, lang)}",
                       "erklaerung": _kommentar(o, stufe, lang),
                       "felder": [_feldzeile(o, p, lang)[2:] for p in felder]})
    return stufen


def schema(o: Graph | None = None, f: Graph | None = None, lang: str = "de") -> dict[str, Any]:
    """Knoten und Kanten des Bildes, dazu ein Satz und was unbekannt ist.

    Knoten: `id`, `name`, `art` (klasse, begriffe, fremd, fehlt), `zeilen`, `titel`, `formen`,
    `meldungen`. Kanten: `von`, `zu`, `name`, `art` (eigenschaft, ist_ein, entspricht),
    `titel`."""
    o = ontologie() if o is None else o
    f = formen() if f is None else f
    tx = TEXT.get(lang, TEXT["de"])
    klassen = sorted(k for k in o.subjects(RDF.type, OWL.Class) if _wm(k))
    je_form = formen_je_klasse(o, f)
    knoten: dict[str, dict[str, Any]] = {}
    kanten: list[dict[str, Any]] = []

    def fremd(iri) -> str:
        knoten.setdefault(str(iri), {"id": str(iri), "name": kurz(iri), "art": "fremd",
                                     "zeilen": [kurz(iri)], "titel": str(iri), "formen": 0,
                                     "meldungen": []})
        return str(iri)

    def werte_von(k) -> list:
        return sorted((p for p in o.subjects(RDF.type, OWL.DatatypeProperty)
                       if k in domaenen(o, p)),
                      key=lambda p: (list(ZEICHEN).index(o.value(p, WM.schutz))
                                     if o.value(p, WM.schutz) in ZEICHEN else -1,
                                     _wort(o, p, lang)))

    for k in klassen:
        name = _wort(o, k, lang)
        ist_begriff = (k, RDFS.subClassOf, SKOS.Concept) in o
        glieder = sorted(o.subjects(RDF.type, k), key=lambda i: _wort(o, i, lang))
        meldungen = je_form.get(k, [])
        zeilen = [name] + [_feldzeile(o, p, lang) for p in werte_von(k)]
        tipp = []
        if k == WM.Weg:
            for ort in wege_je_ort(o, lang):
                zeilen.append(f"{ort['ort']}: {len(ort['wege'])}")
                tipp.append(f"{ort['ort']}: " + ", ".join(
                    w["name"] + (f" ({tx['ausnahme']})" if w["ausnahme"] else "")
                    for w in ort["wege"]))
        elif k == WM.Feld:
            zeilen.append("  ".join(f"{s['stufe'][0]} {len(s['felder'])}"
                                    for s in felder_je_stufe(o, lang)))
            tipp += [f"{s['stufe']}: " + ", ".join(s["felder"]) for s in felder_je_stufe(o, lang)]
        elif glieder:
            woerter = [_wort(o, i, lang) for i in glieder]
            # Mehr als drei Zeilen machen den Kasten zum Bild im Bild: dann nur die Zahl.
            zeilen += (_in_zeilen(woerter) if len(woerter) <= 16
                       else [f"{len(woerter)} {tx['begriffe']}"])
            tipp.append(f"{tx['begriffe']}: " + ", ".join(woerter))
            treffer = [f"{_wort(o, i, lang)} ≈ {kurz(m)}" for i in glieder
                       for m in o.objects(i, SKOS.closeMatch)]
            if treffer:
                tipp.append(f"{tx['fibo']}: " + ", ".join(treffer))
        if meldungen:
            zeilen.append(f"§ {len(meldungen)} {tx['regeln']}")
        knoten[str(k)] = {
            "id": str(k), "name": name, "art": "begriffe" if ist_begriff else "klasse",
            "zeilen": zeilen, "formen": len(meldungen), "meldungen": meldungen,
            "titel": _absaetze(f"{name} ({kurz(k)})", _kommentar(o, k, lang), *tipp,
                               *(f"§ {m}" for m in meldungen))}
        for oben in o.objects(k, RDFS.subClassOf):
            if oben == SKOS.Concept:
                continue
            ziel = str(oben) if oben in klassen else fremd(oben)
            kanten.append({"von": str(k), "zu": ziel, "name": tx["ist_ein"], "art": "ist_ein",
                           "titel": f"{name} {tx['ist_ein']} {_wort(o, oben, lang)}"})
        for m in o.objects(k, SKOS.closeMatch):
            kanten.append({"von": str(k), "zu": fremd(m), "name": tx["entspricht"],
                           "art": "entspricht", "titel": str(m)})

    beziehungen = set(o.subjects(RDF.type, OWL.ObjectProperty)) | {
        p for p in o.subjects(RDF.type, OWL.AnnotationProperty) if o.value(p, RDFS.domain)}
    for p in sorted(beziehungen):
        r = o.value(p, RDFS.range)
        if r is None:
            continue
        for d in domaenen(o, p):
            kanten.append({
                "von": str(d) if d in klassen else fremd(d),
                "zu": str(r) if r in klassen else fremd(r), "name": _wort(o, p, lang),
                "art": "eigenschaft",
                "titel": _absaetze(f"{_wort(o, p, lang)} ({kurz(p)})", _kommentar(o, p, lang))})

    unbekannt = unbekannte_begriffe(o, f)
    for name in unbekannt:
        knoten[f"fehlt:{name}"] = {"id": f"fehlt:{name}", "name": name, "art": "fehlt",
                                   "zeilen": [f"{tx['unbekannt']}: {name}"], "formen": 0,
                                   "meldungen": [], "titel": tx["fehlt"]}

    n_regeln = len({m for ms in je_form.values() for m in ms})
    n_bez = len({k["name"] for k in kanten if k["art"] == "eigenschaft"})
    n_dinge = sum(1 for k in klassen if (k, RDFS.subClassOf, SKOS.Concept) not in o)
    n_listen = len(klassen) - n_dinge
    n_felder = len(set(o.subjects(RDF.type, WM.Feld)))
    n_fibo = len({str(m) for m in o.objects(None, SKOS.closeMatch)})
    if lang == "en":
        satz = (f"Wealth knows {n_dinge} kinds of things, {n_listen} lists of terms and "
                f"{n_bez} relations between them; {n_regeln} rules say what must hold. "
                f"Each of the {n_felder} fields of a position has a protection level, and "
                f"{n_fibo} terms point to their counterpart in FIBO.")
        satz += (" The rules only name terms the ontology knows." if not unbekannt
                 else " The rules name terms the ontology does not know: "
                 + ", ".join(unbekannt) + ".")
    else:
        satz = (f"Wealth kennt {n_dinge} Arten von Dingen, {n_listen} Listen von Begriffen "
                f"und {n_bez} Beziehungen zwischen ihnen; {n_regeln} Regeln sagen, was für "
                f"sie gelten muss. Jedes der {n_felder} Felder einer Position hat eine "
                f"Schutzstufe, und {n_fibo} Begriffe zeigen auf ihr Gegenstück in FIBO.")
        satz += (" Die Regeln nennen nur Begriffe, die die Ontologie kennt." if not unbekannt
                 else " Die Regeln nennen Begriffe, die die Ontologie nicht kennt: "
                 + ", ".join(unbekannt) + ".")
    return {"satz": satz, "knoten": list(knoten.values()), "kanten": kanten,
            "unbekannt": unbekannt}
