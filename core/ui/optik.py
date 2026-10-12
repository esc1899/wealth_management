"""Die Lotsee-Optik in Wealth: Variablen aus assets/lotsee/, Regeln fuer Streamlit von hier.

Die Werte (Farben, Rundungen, Schrift) kommen aus ``assets/lotsee/``, einer Kopie dessen, was
``lotsee/optik/erzeuge.py`` aus ``tokens.json`` macht (seit 12.10.2026, Fassung C2 "Richtfeuer").
Hier stehen nur die Regeln, die Streamlits Bausteine darauf setzen: das Menue mit dem Cursor in
der Leitfarbe, der Lichtschein hinter der Ueberschrift. Jede Regel nennt eine Variable, nie einen
Farbwert -- so aendert sich die Optik in lotsee und kommt mit einer neuen Kopie hierher.
``tests/test_optik.py`` prueft, dass die Kopie zur Quelle passt.

Farben, die nicht durch CSS gehen (Plotly), holt ``farbe()`` aus derselben tokens.json.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import streamlit as st

ORDNER = Path(__file__).resolve().parents[2] / "assets" / "lotsee"
APP = "wealth"

#: Das Zeichen fuer st.logo: mit Schriftzug in der offenen Seitenleiste, klein eingeklappt.
SCHRIFTZUG = str(ORDNER / "zeichen-schriftzug.svg")
ZEICHEN_KLEIN = str(ORDNER / "zeichen-klein.svg")

REGELN = """
[data-testid="stSidebar"] img { height: 2.4rem; width: auto; max-width: 100%; }
[data-testid="stNavSectionHeader"] { text-transform: uppercase; letter-spacing: 0.08em;
  font-size: 0.7rem; color: var(--lotsee-text-menue-leise); }
[data-testid="stSidebarNavLink"] { border-radius: var(--lotsee-rundung-cursor); }
/* Der Cursor: der offene Menuepunkt in der Leitfarbe, Schrift in Nacht (Fassung D, 12.10.2026). */
[data-testid="stSidebarNavLink"][aria-current="page"] { background: var(--lotsee-leit-licht); }
[data-testid="stSidebarNavLink"][aria-current="page"] * { color: var(--lotsee-nacht) !important;
  font-weight: 600; }
/* Licht von oben links hinter der Ueberschrift, wie die Kacheln der Startseite. Der Kopf wird
   durchsichtig, sonst deckt er den Schein ab. */
[data-testid="stMain"] { background: radial-gradient(900px 360px at 12% 0%,
  color-mix(in srgb, var(--lotsee-leit-licht) 14%, transparent), transparent 70%); }
header[data-testid="stHeader"] { background: transparent; }
"""


@lru_cache(maxsize=1)
def _css() -> str:
    return "<style>" + (ORDNER / "lotsee.css").read_text(encoding="utf-8") + REGELN + "</style>"


@lru_cache(maxsize=1)
def tokens() -> dict:
    return json.loads((ORDNER / "tokens.json").read_text(encoding="utf-8"))


def farbe(name: str) -> str:
    """Ein Farbwert fuer Stellen ohne CSS: "leit_tief", "leit_licht" oder ein Name aus
    ``farben``/``zustand`` ("nacht", "alarm")."""
    t = tokens()
    if name.startswith("leit_"):
        return t["apps"][APP][name.removeprefix("leit_")]
    return t["farben"].get(name) or t["zustand"][name]


def einbinden() -> None:
    """Zeichen und Regeln auf jede Seite; app.py ruft es einmal je Lauf."""
    st.logo(SCHRIFTZUG, size="large", icon_image=ZEICHEN_KLEIN)
    st.markdown(_css(), unsafe_allow_html=True)
