"""Titelseite eines Depot-Titels — erreicht über seine Kachel (core/ui/titelseite.py).

Seit 11.10.2026 statt der Positionsanalyse mit Auswahlbox; Dateiname und Adresse bleiben, damit
Links der Kacheln und von älteren Seiten weiter tragen.
"""

import streamlit as st

from core.ui.titelseite import seite

st.set_page_config(page_title="Wealth", layout="wide")
seite("depot")
