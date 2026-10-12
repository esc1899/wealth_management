"""UI-Rauchtest der beiden Kachel-Seiten: Sie bauen sich ohne Ausnahme auf."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGES = Path(__file__).resolve().parents[2] / "pages"


def _app(seite: str) -> AppTest:
    """Die Kachel-Seite in einer Navigation mit ihren Zielseiten -- ``st.page_link`` kennt nur
    Seiten, die ``st.navigation`` registriert hat (in der App tut das app.py)."""
    def skript(start, ziele):
        import streamlit as st
        st.navigation([st.Page(start)] + [st.Page(z) for z in ziele]).run()

    ziele = [str(PAGES / z) for z in ("position_dashboard.py", "watchlist_analysis.py", "watchlist_checker.py")]
    return AppTest.from_function(skript, args=(str(PAGES / seite), ziele), default_timeout=30)


@pytest.mark.parametrize("seite", ["kacheln_depot.py", "kacheln_watchlist.py"])
def test_seite_laedt(seite):
    at = _app(seite)
    at.run()
    assert not at.exception, f"Page threw exception: {at.exception}"
    assert at.title, "Titel fehlt"


@pytest.fixture
def depot_und_watchlist(request):
    """Drei Titel: einer gefährdet, einer geprüft, einer auf der Watchlist ohne Urteil."""
    from datetime import date

    from core.storage.models import Position
    from state import get_analyses_repo, get_positions_repo

    repo, analysen = get_positions_repo(), get_analyses_repo()

    def neu(name, ticker, **kw):
        return repo.add(Position(asset_class="Aktie", investment_type="Wertpapiere", name=name,
                                 ticker=ticker, unit="Stück", added_date=date.today(), **kw))

    novo = neu("Novo Nordisk", "NOVO-B.CO", quantity=5.0, in_portfolio=True)
    muv = neu("Munich Re", "MUV2.DE", quantity=3.0, in_portfolio=True)
    rms = neu("Hermès", "RMS.PA", in_watchlist=True)
    analysen.save(novo.id, "storychecker", "s", "gefaehrdet", "Die Marge <bricht> ein.")
    analysen.save(muv.id, "storychecker", "s", "intact", "These hält.")

    def aufraeumen():
        ids = (novo.id, muv.id, rms.id)
        analysen._conn.execute(
            f"DELETE FROM position_analyses WHERE position_id IN ({','.join('?' * len(ids))})", ids)
        analysen._conn.commit()
        for i in ids:
            repo.delete(i)

    request.addfinalizer(aufraeumen)
    return {"novo": novo, "muv": muv, "rms": rms}


def _karten(at):
    """Je Kachel ihr Satz (Inhalt) -- in der Reihenfolge der Seite."""
    return [m.value for m in at.markdown if 'class="wk-notiz' in m.value]


def test_depot_zeigt_gefaehrdetes_zuerst(depot_und_watchlist):
    at = _app("kacheln_depot.py")
    at.run()
    assert not at.exception, at.exception
    karten = _karten(at)
    assert len(karten) == 2
    assert "Die Marge &lt;bricht&gt; ein." in karten[0]
    assert "These hält." in karten[1]


def test_watchlist_ohne_urteil_sagt_nie_geprueft(depot_und_watchlist):
    at = _app("kacheln_watchlist.py")
    at.run()
    assert not at.exception, at.exception
    karten = _karten(at)
    assert len(karten) == 1 and "Noch nie geprüft." in karten[0]


def test_kachel_zeigt_die_auswahl_und_jetzt_checken(depot_und_watchlist):
    """Je gewaehlter Check ein Kaestchen, auch ohne Urteil; darunter der Knopf je Titel."""
    rms = depot_und_watchlist["rms"]
    at = _app("kacheln_watchlist.py")
    at.run()
    assert not at.exception, at.exception
    knopf = next(b for b in at.button if b.key == f"wk-checken-{rms.id}")
    assert knopf.label.startswith("Jetzt checken") and "Cloud" in knopf.help


@pytest.mark.parametrize("seite,wer", [("position_dashboard.py", "muv"), ("watchlist_analysis.py", "rms")])
def test_titelseite_zeigt_position_aus_der_adresse(depot_und_watchlist, seite, wer):
    """Der Absprung einer Kachel: ?position=&check= zeigt die Titelseite dieser Position."""
    pos = depot_und_watchlist[wer]
    at = AppTest.from_file(PAGES / seite, default_timeout=30)
    at.query_params["position"] = str(pos.id)
    at.query_params["check"] = "storychecker"
    at.run()
    assert not at.exception, at.exception
    assert any('class="ts-name"' in m.value and pos.name in m.value for m in at.markdown)
    assert not at.selectbox, "Die Auswahlbox ist weg -- man kommt ueber die Kachel"
    knopf = next(b for b in at.button if b.key == "ts-checks")
    assert "Cloud" in knopf.help, "die Checks neu pruefen geht in Depot und Watchlist, mit Cloud-Stern"


@pytest.mark.parametrize("seite", ["position_dashboard.py", "watchlist_analysis.py"])
def test_titelseite_ohne_position_verweist_auf_die_kacheln(seite):
    at = AppTest.from_file(PAGES / seite, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    assert at.title and at.title[0].value


def test_titelseite_urteile_und_band(depot_und_watchlist):
    """Ein Urteil steht mit Satz, die uebrigen Checks als "nie geprueft"; der Chart steht."""
    pos = depot_und_watchlist["novo"]
    at = AppTest.from_file(PAGES / "position_dashboard.py", default_timeout=30)
    at.query_params["position"] = str(pos.id)
    at.run()
    assert not at.exception, at.exception
    texte = " ".join(m.value for m in at.markdown)
    assert "Von 4 Checks: 1 kritisch, 3 nie geprüft." in texte
    assert "nie geprüft" in texte


# ---------------------------------------------------------------------------
# Der Tag oben auf dem Depot (12.10.2026): dieselbe Zeile wie auf der Analyse
# ---------------------------------------------------------------------------

def _bewertung(symbol, wert, tag, ausgeschlossen=False):
    from types import SimpleNamespace

    return SimpleNamespace(symbol=symbol, name=symbol, in_portfolio=True, current_value_eur=wert,
                           day_pnl_eur=tag, analysis_excluded=ausgeschlossen, position_id=None)


def test_tagesperformance_summen_wie_die_analyse():
    from core.ui.tagesperformance import summen

    s = summen([_bewertung("A", 1000.0, 10.0), _bewertung("B", 500.0, -5.0, ausgeschlossen=True),
                _bewertung("C", None, None)])
    assert (s.analyse, s.vermoegen, s.ausgeschlossen, s.ausgeschlossen_zahl) == (1000.0, 1500.0, 500.0, 1)


def test_depot_zeigt_den_tag_wie_die_analyse(depot_und_watchlist, monkeypatch):
    from unittest.mock import MagicMock

    import state

    markt = MagicMock()
    markt.get_portfolio_valuation.return_value = [_bewertung("AAA", 1010.0, 10.0),
                                                  _bewertung("BBB", 495.0, -5.0)]
    markt.get_latest_fetch_time.return_value = None
    monkeypatch.setattr(state, "get_market_agent", lambda: markt)

    depot = _app("kacheln_depot.py")
    depot.run()
    assert not depot.exception, depot.exception
    # Die Zeile kommt aus core/ui/tagesperformance.zeigen -- dieselbe Funktion wie auf der Analyse.
    zeile = next(m.value for m in depot.markdown if m.value.startswith("**Heute:"))
    assert "+5,00" in zeile and "+0.33% Analyse" in zeile and "+0.33% Gesamt" in zeile
    assert depot.get("plotly_chart"), "das Tages-Chart fehlt"
