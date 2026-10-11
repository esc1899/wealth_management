"""Titelseite eines Kandidaten der Suche -- erreicht über seine Kachel (core/ui/titelseite.py,
core/ui/suche/kandidaten.py). Nicht im Menü."""

import streamlit as st

from core.ui.titelseite import seite

st.set_page_config(page_title="Wealth", layout="wide")
seite("kandidaten")
