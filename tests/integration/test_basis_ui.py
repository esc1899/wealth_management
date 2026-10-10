"""Die Basis ohne Sprachmodell: Portfolio-Story in der Pflege, KI-Knopf grau ohne Ollama."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import core.ui.lokales_modell as lokales_modell
from core.health import HealthCheck, Severity

PAGES = Path(__file__).resolve().parents[2] / "pages"


@pytest.fixture
def ollama(monkeypatch):
    """Stellt ein, ob Ollama antwortet -- ohne Netz, und ohne die gemerkte Antwort."""
    def stellen(erreichbar: bool):
        ergebnis = HealthCheck("ollama_ok" if erreichbar else "ollama_unreachable",
                               Severity.OK if erreichbar else Severity.ERROR, "http://localhost:11434")
        monkeypatch.setattr(lokales_modell, "check_ollama_connectivity", lambda host: ergebnis)
        lokales_modell._erreichbar.clear()
    yield stellen
    lokales_modell._erreichbar.clear()


def _ki_knopf(at):
    return next(b for b in at.button if "KI-Entwurf" in b.label)


def test_ohne_ollama_ist_der_entwurf_grau_mit_hinweis(ollama):
    ollama(False)
    at = AppTest.from_file(PAGES / "portfolio_narrativ.py", default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    assert _ki_knopf(at).disabled
    assert any("Ollama installieren" in c.value for c in at.caption)


def test_mit_ollama_ist_der_entwurf_frei(ollama):
    ollama(True)
    at = AppTest.from_file(PAGES / "portfolio_narrativ.py", default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    assert not _ki_knopf(at).disabled
    assert not any("Ollama installieren" in c.value for c in at.caption)


def test_bereit_folgt_der_pruefung(ollama):
    ollama(True)
    assert lokales_modell.lokales_modell_bereit()
    ollama(False)
    assert not lokales_modell.lokales_modell_bereit()


@pytest.mark.parametrize("seite", ["portfolio_story.py", "dividend_calendar.py"])
def test_gekuerzte_seiten_laden(seite):
    at = AppTest.from_file(PAGES / seite, default_timeout=30)
    at.run()
    assert not at.exception, at.exception


def test_portfolio_checker_ohne_story_formular():
    at = AppTest.from_file(PAGES / "portfolio_story.py", default_timeout=30)
    at.run()
    assert not at.text_area, "das Story-Formular gehoert jetzt zur Pflege"
