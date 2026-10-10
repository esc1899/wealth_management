"""Vorauswahl einer Position auf einer Analyseseite — aus der Sitzung oder aus der Adresse.

Zwei Wege führen auf eine Analyseseite mit fester Position: ein Knopf, der die Kennung in
``st.session_state`` legt und ``st.switch_page`` ruft (ältere Seiten), und ein Link mit
``?position=…&check=…`` (die Kacheln). Der Link bleibt beim Neuladen gültig und nennt dazu
den Check, dessen Analyse aufgeklappt werden soll.
"""

from __future__ import annotations

from typing import Optional, Tuple

import streamlit as st


def vorauswahl(session_key: str) -> Tuple[Optional[int], Optional[str]]:
    """(Positions-ID, Check) — die Sitzung hat Vorrang, sonst die Adresse; sonst (None, None)."""
    pid = st.session_state.pop(session_key, None)
    if pid is not None:
        return pid, None
    roh = st.query_params.get("position")
    if roh and roh.isdigit():
        return int(roh), st.query_params.get("check")
    return None, None
