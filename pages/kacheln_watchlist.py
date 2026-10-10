"""Die Watchlist als Kacheln — je Titel der Satz, der gerade zählt (core/kacheln.py).

Zusätzlich zur bestehenden Seite, bis sich zeigt, ob die Kacheln tragen (Erik, 10.10.2026).
"""

import streamlit as st

from core.ui.kacheln import seite

st.set_page_config(page_title="Wealth", layout="wide")
seite("watchlist")
