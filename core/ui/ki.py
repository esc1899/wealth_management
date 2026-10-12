"""KI-Knöpfe: ein Stern für alle, die Farbe sagt, wo das Modell rechnet.

Grün heißt lokal (Ollama, die Daten bleiben auf dem Rechner), blau heißt Cloud (Claude & Co.).
Farbe allein liest sich schlecht, darum sagt der Tooltip dasselbe in Worten (Erik, 11.10.2026).
Jeder Knopf, der ein Sprachmodell aufruft, geht über diese Funktion, damit es einheitlich bleibt:

    if ki_knopf(t("..."), wo="lokal", key="ps_check", disabled=not bereit):
        ...

Die Farbe hängt am Schlüssel des umgebenden Containers (``st-key-ki-<wo>-<key>``); ein
ausgegrauter Knopf behält das Grau von Streamlit.
"""

from __future__ import annotations

from typing import Literal

import streamlit as st

from core.i18n import t

Wo = Literal["lokal", "cloud"]

STERN = ":material/auto_awesome:"
# Die Farben sind Variablen der Lotsee-Optik (core/ui/optik.py); Cloud ist die Leitfarbe der App.
FARBE = {"lokal": "var(--lotsee-ki-lokal)", "cloud": "var(--lotsee-ki-cloud)"}

_CSS = "<style>" + "".join(
    f'div[class*="st-key-ki-{wo}-"] button:not(:disabled) [data-testid="stIconMaterial"] {{ color: {farbe}; }}'
    for wo, farbe in FARBE.items()
) + "</style>"


def ki_knopf(label: str, *, wo: Wo, key: str, disabled: bool = False, form: bool = False, **kwargs) -> bool:
    """Ein Knopf mit dem Stern in der Farbe von ``wo``; ``form=True`` für einen Knopf im Formular."""
    st.markdown(_CSS, unsafe_allow_html=True)
    with st.container(key=f"ki-{wo}-{key}"):
        if form:
            return st.form_submit_button(label, icon=STERN, help=t(f"ki.{wo}"), disabled=disabled, **kwargs)
        return st.button(label, key=key, icon=STERN, help=t(f"ki.{wo}"), disabled=disabled, **kwargs)
