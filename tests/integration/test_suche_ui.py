"""Seite Suche (11.10.2026, Fassung A): oben die Strategie, ein Suchfeld mit Skill, ein Banner
mit dem Weg zu den Skills, darunter der letzte Lauf."""

from datetime import date, datetime
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

    ziele = [str(PAGES / z) for z in ("skills.py", "position_dashboard.py", "watchlist_analysis.py", "kandidat.py")]
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


# ------------------------------------------------------------------
# Kandidaten (11.10.2026): ein Lauf legt seine Vorschlaege als Kandidaten ab
# ------------------------------------------------------------------

@pytest.fixture
def aufraeumen():
    """Kandidaten, die ein Test anlegt, samt ihren Positionen wieder weg."""
    from state import get_db_connection

    conn = get_db_connection()
    vorher = {r[0] for r in conn.execute("SELECT position_id FROM kandidaten")}
    yield
    neu = {r[0] for r in conn.execute("SELECT position_id FROM kandidaten")} - vorher
    for pid in neu:
        conn.execute("DELETE FROM kandidaten WHERE position_id = ?", (pid,))
        conn.execute("DELETE FROM positions WHERE id = ?", (pid,))
    conn.commit()


class _Sitzung:
    def __init__(self, i):
        self.id, self.created_at, self.skill_name, self.query = i, datetime(2026, 10, 11, 9, 0), "Skill", "Netzausbau"


class _Nachricht:
    role, content = "assistant", "Bericht: Netzausbau in Europa."


def _freie_suche(monkeypatch, vorschlaege):
    """Die freie Suche ohne Modell: der Lauf liefert ``vorschlaege``, gefragt wird nichts."""
    from core.ui.suche import frei

    gesehen = {}

    class Agent:
        model = "claude-sonnet-5-5"

        def start_session(self, **kw):
            return _Sitzung(901)

        def get_session(self, i):
            return _Sitzung(i)

        def get_messages(self, i):
            return [_Nachricht()]

        async def chat(self, sid, nachricht, enable_thinking=False, bekannte_ticker=()):
            gesehen["bekannt"] = list(bekannte_ticker)
            return "ok", vorschlaege

    monkeypatch.setattr(frei, "_agent", Agent)
    return gesehen


def _vorschlag(ticker, name):
    return {"ticker": ticker, "name": name, "asset_class": "Aktie", "notes": "", "story": f"These zu {name}"}


def test_lauf_legt_kandidaten_ab_und_sagt_es(monkeypatch, aufraeumen, auf_der_watchlist):
    gesehen = _freie_suche(monkeypatch, [_vorschlag("KND1.DE", "Kandidat Eins AG"),
                                         _vorschlag("BSP.DE", "Beispiel AG")])
    at = _app()
    at.run()
    at.text_input(key="suche_anfrage_frei").set_value("Netzausbau").run()
    at.button(key="suche_los_frei").click().run()
    assert not at.exception, at.exception
    assert "BSP.DE" in gesehen["bekannt"], "Watchlist-Ticker gehen als bekannt an die Strategie"
    assert any("1 neue Kandidaten" in s.value and "schon im Depot oder auf der Watchlist" in s.value
               for s in at.success)
    assert "Kandidat Eins AG" in _links(at)
    assert "These zu Kandidat Eins AG" in " ".join(m.value for m in at.markdown)
    assert any(b.label == "Genauer prüfen" for b in at.button)


def test_nicht_interessant_rueckt_nach_verworfen(monkeypatch, aufraeumen):
    from state import get_kandidaten_repo

    _freie_suche(monkeypatch, [_vorschlag("KND2.DE", "Kandidat Zwei AG")])
    at = _app()
    at.run()
    at.text_input(key="suche_anfrage_frei").set_value("Netzausbau").run()
    at.button(key="suche_los_frei").click().run()
    pid = next(k.position_id for k in get_kandidaten_repo().alle() if k.zustand == "offen"
               and k.lauf_id == 901)
    at.button(key=f"wk-entscheiden-{pid}-nein").click().run()
    assert not at.exception, at.exception
    assert get_kandidaten_repo().get(pid).zustand == "verworfen"
    assert any(e.label.startswith("Verworfen") for e in at.expander)
    assert "Kandidat Zwei AG" not in _links(at)


def test_titelseite_des_kandidaten_zeigt_herkunft_und_entscheidung(monkeypatch, aufraeumen):
    from core import kandidaten
    from state import get_kandidaten_repo, get_positions_repo

    _freie_suche(monkeypatch, [])
    kandidaten.aufnehmen(get_positions_repo(), get_kandidaten_repo(),
                         [_vorschlag("KND3.DE", "Kandidat Drei AG")], "frei", "Skill", 901)
    pid = get_positions_repo().get_by_ticker("KND3.DE")[0].id

    at = AppTest.from_file(str(PAGES / "kandidat.py"), default_timeout=30)
    at.query_params["position"] = str(pid)
    at.run()
    assert not at.exception, at.exception
    titel = [s.value for s in at.subheader]
    assert "Herkunft" in titel and "Entscheidung" in titel
    assert any(e.label.startswith("Bericht des Laufs") for e in at.expander)
    assert any(b.label == "Genauer prüfen" for b in at.button)
