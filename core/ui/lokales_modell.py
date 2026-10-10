"""Knöpfe, die ein lokales Sprachmodell brauchen: grau, wenn keins da ist, mit Hinweis zum Einrichten.

Die Basis der App (Kacheln, Pflege, Performance) läuft ohne Sprachmodell. Wo sie ein Extra
anbietet, das Ollama braucht (etwa den KI-Entwurf des Portfolio-Narrativs), soll der Knopf
nicht erst beim Klick scheitern: Ist Ollama nicht erreichbar, ist er ausgegraut, und darunter
steht, was zu tun ist. Das Muster gilt für jeden solchen Knopf:

    bereit = lokales_modell_bereit()
    st.button("KI-Entwurf", disabled=not bereit)
    if not bereit:
        hinweis_einrichten()

Die Prüfung fragt Ollama nach seinen Modellen (``/api/tags``, lädt kein Modell) und merkt sich
die Antwort eine Minute, damit nicht jeder Klick auf der Seite eine Anfrage auslöst.
"""

from __future__ import annotations

import streamlit as st

from core.health import Severity, check_ollama_connectivity
from core.i18n import t


@st.cache_data(ttl=60, show_spinner=False)
def _erreichbar(host: str) -> bool:
    return check_ollama_connectivity(host).severity == Severity.OK


def lokales_modell_bereit() -> bool:
    """True, wenn das eingestellte Ollama antwortet."""
    from config import config
    return bool(config.OLLAMA_HOST) and _erreichbar(config.OLLAMA_HOST)


def hinweis_einrichten() -> None:
    """Der Satz unter einem ausgegrauten Knopf: warum grau, und wie man es einrichtet."""
    st.caption(t("lokales_modell.hinweis"))
