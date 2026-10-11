"""Seite Suche (11.10.2026, Fassung A): oben die Strategie, ein Suchfeld mit Skill, ein Banner
mit dem Weg zu den Skills, darunter der letzte Lauf."""

from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGES = Path(__file__).resolve().parents[2] / "pages"
BEREICH = {"frei": "search", "einzeltitel": "research", "strukturwandel": "structural_scan"}


def _app():
    """Mit Navigation, damit die Links (Skills, Titelseite) registrierte Seiten finden."""
    def skript(start, ziele):
        import streamlit as st
        st.navigation([st.Page(start)] + [st.Page(z) for z in ziele]).run()

    ziele = [str(PAGES / z) for z in ("skills.py", "position_dashboard.py", "watchlist_analysis.py")]
    return AppTest.from_function(skript, args=(str(PAGES / "suche.py"), ziele), default_timeout=30)


def _text(at) -> str:
    return " ".join([m.value for m in at.markdown] + [i.value for i in at.info])


def _links(at) -> list[str]:
    return [link.label for link in at.get("page_link")]


@pytest.mark.parametrize("art", list(BEREICH))
def test_banner_nennt_strategie_und_verweist_auf_die_skills(art):
    from state import get_skills_repo

    at = _app()
    at.run()
    at.button_group(key="suche_art").set_value(art).run()
    assert not at.exception, f"{art}: {at.exception}"

    skills = get_skills_repo().get_by_area(BEREICH[art])
    if skills:
        assert skills[0].name in _text(at), "Banner nennt den gewaehlten Skill nicht"
    elif art == "strukturwandel":
        assert "noch keine Strategie" in _text(at)
    assert "Strategie einstellen" in _links(at)


def test_eigene_strategie_fragt_nach_dem_fokus():
    at = _app()
    at.run()
    at.selectbox(key="suche_skill_frei").set_value("Eigene Strategie").run()
    assert not at.exception
    assert "eigenen Strategie" in _text(at)
    assert any(a.label.startswith("Strategie-Fokus") for a in at.text_area)


def test_ohne_anfrage_startet_nichts():
    at = _app()
    at.run()
    at.button(key="suche_los_frei").click().run()
    assert not at.exception
    assert any("wonach gesucht" in e.value for e in at.error)


@pytest.fixture
def auf_der_watchlist():
    from core.storage.models import Position
    from state import get_positions_repo

    repo = get_positions_repo()
    p = repo.add(Position(asset_class="Aktie", investment_type="Wertpapiere", name="Beispiel AG",
                          ticker="BSP.DE", unit="Stück", added_date=date.today(), in_watchlist=True))
    yield p
    repo.delete(p.id)


def test_einzeltitel_schon_bekannt_fragt_kein_modell(auf_der_watchlist, monkeypatch):
    """Steht der Titel schon auf der Watchlist, sagt die Seite das und bewertet nicht neu."""
    from core.ui.suche import einzeltitel

    gefragt = []

    class Agent:
        model = "claude-sonnet-5-5"

        def list_sessions(self, limit):
            return []

        def start_session(self, **kw):
            gefragt.append(kw)

    monkeypatch.setattr(einzeltitel, "_agent", Agent)
    at = _app()
    at.run()
    at.button_group(key="suche_art").set_value("einzeltitel").run()
    at.text_input(key="suche_anfrage_einzeltitel").set_value("bsp.de").run()
    at.button(key="suche_los_einzeltitel").click().run()
    assert not at.exception, at.exception
    assert "steht schon auf der Watchlist" in _text(at)
    assert "Zur Titelseite" in _links(at)
    assert not gefragt, "Agent gefragt, obwohl der Titel bekannt ist"


def test_bekannt_findet_name_ticker_und_nichts_sonst(auf_der_watchlist):
    from core.ui.suche.einzeltitel import bekannt

    assert bekannt("Beispiel AG").id == auf_der_watchlist.id
    assert bekannt(" bsp.de ").id == auf_der_watchlist.id
    assert bekannt("Beispiel") is None
    assert bekannt("") is None
