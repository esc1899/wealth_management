"""Die Lotsee-Optik: Kopie passt zur Quelle, Theme passt zu den Werten, Regeln nennen nur Variablen.

assets/lotsee/ ist eine Kopie dessen, was ``lotsee/optik/erzeuge.py`` schreibt. Liegt das Repo
lotsee daneben, muss die Kopie gleich sein -- sonst `python3 ~/Projects/lotsee/optik/erzeuge.py
wealth assets/lotsee` laufen lassen. Ohne das Repo (CI) wird dieser eine Test uebersprungen.

Ein ``--`` in einem SVG-Kommentar machte am 21.09.2026 die Marke ungueltig, und die
Seitenleiste blieb still leer; darum wird jedes SVG als XML gelesen.
"""
import re
import runpy
import tomllib
from pathlib import Path
from xml.etree import ElementTree

import pytest

from core.ui import kacheln, optik

WURZEL = Path(__file__).resolve().parent.parent
LOTSEE = Path.home() / "Projects" / "lotsee" / "optik" / "erzeuge.py"
HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")


@pytest.mark.parametrize("name", ["zeichen.svg", "zeichen-klein.svg", "zeichen-schriftzug.svg"])
def test_zeichen_ist_gueltiges_svg(name):
    wurzel = ElementTree.parse(optik.ORDNER / name).getroot()
    assert wurzel.tag == "{http://www.w3.org/2000/svg}svg"


@pytest.mark.skipif(not LOTSEE.exists(), reason="Repo lotsee liegt nicht daneben")
def test_kopie_passt_zur_quelle():
    erzeuge = runpy.run_path(str(LOTSEE))
    for name, inhalt in erzeuge["dateien"](optik.APP).items():
        assert (optik.ORDNER / name).read_text(encoding="utf-8") == inhalt, f"{name} ist veraltet"
    assert (optik.ORDNER / "tokens.json").read_bytes() == (LOTSEE.parent / "tokens.json").read_bytes()


def test_theme_folgt_den_werten():
    thema = tomllib.loads((WURZEL / ".streamlit" / "config.toml").read_text(encoding="utf-8"))["theme"]
    f = optik.tokens()["farben"]
    leit = optik.tokens()["apps"]["wealth"]
    assert thema["backgroundColor"] == f["grund"]
    assert thema["textColor"] == f["text"]
    assert thema["borderColor"] == f["linie"]
    assert thema["secondaryBackgroundColor"] == f["flaeche_leise"]
    assert thema["primaryColor"] == thema["linkColor"] == leit["tief"]
    leiste = thema["sidebar"]
    assert leiste["backgroundColor"] == f["nacht"]
    assert leiste["secondaryBackgroundColor"] == f["nacht_hell"]
    assert leiste["textColor"] == f["text_menue"]
    assert leiste["borderColor"] == f["nacht_linie"]
    assert leiste["primaryColor"] == leit["licht"]


@pytest.mark.parametrize("regeln", [optik.REGELN, kacheln.CSS], ids=["optik", "kacheln"])
def test_regeln_nennen_variablen_nicht_farben(regeln):
    # Weiss auf dem Monogramm ist die eine Ausnahme: es steht auf jeder Klassenfarbe.
    assert HEX.findall(regeln.replace("#FFFFFF", "")) == []


def test_farbe_fuer_plotly():
    assert optik.farbe("leit_tief") == optik.tokens()["apps"]["wealth"]["tief"]
    assert optik.farbe("alarm") == optik.tokens()["zustand"]["alarm"]
