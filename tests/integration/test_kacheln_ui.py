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


@pytest.mark.parametrize("seite,wer", [("position_dashboard.py", "muv"), ("watchlist_analysis.py", "rms")])
def test_analyse_waehlt_position_aus_der_adresse(depot_und_watchlist, seite, wer):
    """Der Absprung einer Kachel: ?position=&check= waehlt die Position vor."""
    pos = depot_und_watchlist[wer]
    at = AppTest.from_file(PAGES / seite, default_timeout=30)
    at.query_params["position"] = str(pos.id)
    at.query_params["check"] = "storychecker"
    at.run()
    assert not at.exception, at.exception
    assert pos.name in at.selectbox[0].value
