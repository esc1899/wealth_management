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


def _check_knopf(at):
    return next(b for b in at.button if b.key == "ps_check")


@pytest.mark.parametrize("erreichbar", [False, True])
def test_story_check_ist_grau_ohne_ollama(ollama, erreichbar):
    ollama(erreichbar)
    at = AppTest.from_file(PAGES / "portfolio_narrativ.py", default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    assert _check_knopf(at).disabled is not erreichbar
    assert next(b for b in at.button if b.key == "pr_check").disabled is not erreichbar


def test_story_check_ohne_lauf_sagt_nie_gemessen(ollama):
    ollama(False)
    at = AppTest.from_file(PAGES / "portfolio_narrativ.py", default_timeout=30)
    at.run()
    assert any("noch nie" in i.value for i in at.info)


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


def test_ki_knoepfe_sagen_wo_das_modell_rechnet(ollama):
    """Ein Stern fuer alle KI-Knoepfe; der Tooltip sagt lokal oder Cloud (core/ui/ki.py)."""
    ollama(True)
    at = AppTest.from_file(PAGES / "portfolio_narrativ.py", default_timeout=30)
    at.run()
    assert "Lokales Sprachmodell" in _check_knopf(at).help
    assert "Lokales Sprachmodell" in _ki_knopf(at).help


def test_dividenden_klapper_anteilszuwachs_je_titel(monkeypatch):
    """Kurs als Verlauf, Zu- und Abgaenge je Zeitraum, darunter der Klapper je Titel."""
    import core.composition_drift as cd
    import core.dividend_calendar as dk
    beitrag = dk.DividendContribution("A", "Alpha", "Aktie", 12.0, 1.0)
    monkeypatch.setattr(dk, "compute_monthly_cashflow_forecast", lambda v, months_ahead=12: [
        dk.MonthlyForecast("2026-11", 1.0, [beitrag])])
    monkeypatch.setattr(cd, "portfolio_income_series", lambda s: [
        {"date": "2026-01-01", "total_annual_dividend_eur": 1.0}])
    monkeypatch.setattr(cd, "value_decomposition_series", lambda s, classes=None: [
        {"date": "2026-01-01", "cum_price_effect": 0.0, "cum_quantity_effect": 0.0},
        {"date": "2026-02-01", "cum_price_effect": 10.0, "cum_quantity_effect": 50.0}])
    monkeypatch.setattr(cd, "flows_by_period", lambda s, classes=None, period="month": [
        {"period": "2026-02", "zukaeufe": 80.0, "verkaeufe": -30.0, "saldo": 50.0}])
    monkeypatch.setattr(cd, "value_decomposition_by_ticker", lambda s, classes=None: [
        {"ticker": "XEON", "name": "Geldmarkt", "asset_class": "ETF", "price_effect": 1.0,
         "quantity_effect": 60.0, "groesster_schritt": {"date": "2026-02-01", "q0": 0.0,
                                                          "q1": 2.0, "quantity_effect": 60.0}},
        {"ticker": "A", "name": "Alpha", "asset_class": "Aktie", "price_effect": 9.0,
         "quantity_effect": -10.0, "groesster_schritt": None},
    ])
    at = AppTest.from_file(PAGES / "dividend_calendar.py", default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    assert any("netto für 50 € zugekauft" in m.value for m in at.markdown)
    assert at.get("plotly_chart"), "Kurslinie und Balken fehlen"
    klapper = next(e for e in at.expander if e.label == "Woher kommt der Anteilszuwachs?")
    assert "Geldmarkt (ETF)" in klapper.markdown[0].value
    tabelle = klapper.dataframe[0].value
    assert list(tabelle["Titel"]) == ["Geldmarkt (XEON)", "Alpha (A)"]
    assert tabelle["Größter Sprung"][0] == "01.02.2026: neu → 2 (+60 €)"
