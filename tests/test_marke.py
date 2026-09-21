"""Die Marke in assets/ muss gueltiges XML sein.

Am 21.09.2026 stand ein `--` in einem SVG-Kommentar; das ist in XML verboten,
und ein Browser zeigt eine ungueltige SVG einfach nicht an -- die Seitenleiste
blieb leer, ohne Fehlermeldung. st.logo bettet die Datei als Data-URI ein und
prueft nichts.
"""
from pathlib import Path
from xml.etree import ElementTree

import pytest

ASSETS = Path(__file__).resolve().parent.parent / "assets"


@pytest.mark.parametrize("name", ["marke.svg", "marke-schriftzug.svg"])
def test_marke_ist_gueltiges_svg(name):
    wurzel = ElementTree.parse(ASSETS / name).getroot()
    assert wurzel.tag == "{http://www.w3.org/2000/svg}svg"
    assert wurzel.find("{http://www.w3.org/2000/svg}polyline") is not None   # die Kurslinie
