"""Die Ontologie als Bild zum Ziehen (22.10.2026): zeichnet, was `ontologie/bild.py` aus
`ontologie/wealth.ttl` und `formen.ttl` liest, mit pyvis -- eine Kopie von
`serien-empfehler/ui/ontologie_bild.py`, kein Import.

Faehrt man mit der Maus ueber einen Kasten oder Pfeil, steht dort sein `rdfs:comment` und was
die Formen verlangen. Die Farben kommen aus der Lotsee-Optik (`core/ui/optik.py`), als Werte,
weil das Bild im Rahmen das CSS der Seite nicht sieht.
"""

from __future__ import annotations

from core.ui import optik

#: Wie bei Sound und Serien: 0.3 beruhigt das Netz, sonst dreht es sich lange weiter.
DAEMPFUNG = 0.3


def _aussehen() -> tuple[dict, dict]:
    f = optik.farbe
    knoten = {  # Fuellung, Rand, Form, Schriftgroesse
        "klasse": (f("flaeche"), f("leit_tief"), "box", 15),
        "begriffe": (f("flaeche_leise"), f("leit_tief"), "box", 12),
        "fremd": (f("flaeche_leise"), f("linie"), "box", 11),
        "fehlt": (f("flaeche"), f("alarm"), "box", 12),
    }
    linie = {  # Farbe, gestrichelt
        "eigenschaft": (f("leit_tief"), False),
        "ist_ein": (f("linie"), True),
        "entspricht": (f("linie"), True),
    }
    return knoten, linie


def _sicher(text: str) -> str:
    """pyvis schreibt Beschriftungen als JSON in ein `<script>`; ohne spitze Klammern kann
    keine es schliessen."""
    return text.replace("<", "‹").replace(">", "›")


def html(d: dict, hoehe: int = 760) -> str:
    """Das Bild als HTML-Seite, ohne Netz (pyvis mit eingebettetem vis.js)."""
    from pyvis.network import Network

    aussehen, linie = _aussehen()
    netz = Network(height=f"{hoehe}px", width="100%", directed=True, cdn_resources="in_line",
                   bgcolor=optik.farbe("grund"), font_color=optik.farbe("text"))
    netz.barnes_hut(gravity=-6000, spring_length=180, damping=DAEMPFUNG)
    for k in d["knoten"]:
        fuellung, rand, form, groesse = aussehen[k["art"]]
        netz.add_node(k["id"], label=_sicher("\n".join(k["zeilen"])), title=_sicher(k["titel"]),
                      shape=form, borderWidth=3 if k["formen"] else 1,
                      color={"background": fuellung, "border": rand},
                      font={"size": groesse, "face": "-apple-system, sans-serif"})
    for e in d["kanten"]:
        farbe, strich = linie[e["art"]]
        netz.add_edge(e["von"], e["zu"], label=_sicher(e["name"]), title=_sicher(e["titel"]),
                      color=farbe, dashes=strich, arrows="to",
                      font={"size": 11 if e["art"] == "eigenschaft" else 9,
                            "color": optik.farbe("text_leise")})
    return netz.generate_html(notebook=False)
