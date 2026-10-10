"""Die Kachel je Titel: welcher Satz oben steht, wie sortiert wird, was escaped wird."""

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.kacheln import BEWEGUNG_PROZENT, kachel, sortiert, tagesprozent
from core.storage.models import Position, PositionAnalysis
from core.ui.kacheln import farbe_css, inhalt_html, unter_html, urteil_label, urteile_sortiert, ziel


def _pos(pid=1, name="Munich Re", ticker="MUV2.DE", **kw):
    return Position(id=pid, name=name, ticker=ticker, asset_class="Aktie", investment_type="Wertpapiere",
                    unit="Stück", added_date=date(2026, 1, 1), in_portfolio=True, **kw)


def _bew(day=None, pnl=None, kurs=100.0, rendite=None):
    return SimpleNamespace(day_pnl_pct=day, pnl_pct=pnl, current_price_eur=kurs, dividend_yield_pct=rendite)


def _urteil(agent, verdict, summary="Ein Satz.", tag=1):
    return PositionAnalysis(position_id=1, agent=agent, skill_name="s", verdict=verdict,
                            summary=summary, created_at=datetime(2026, 10, tag, 8, 0))


class TestVorrang:
    def test_storychecker_gefaehrdet_schlaegt_alles(self):
        k = kachel(_pos(), "depot", _bew(day=-9.0), {
            "storychecker": _urteil("storychecker", "gefaehrdet", "Marge bricht ein.", tag=2),
            "fundamental_analyzer": _urteil("fundamental_analyzer", "fair", "Jünger.", tag=8),
        })
        assert k.grund == "gefaehrdet"
        assert k.satz == "Marge bricht ein."
        assert k.satz_agent == "storychecker"

    def test_devils_advocate_kritisch_ist_gefaehrdet(self):
        k = kachel(_pos(), "watchlist", _bew(), {"devils_advocate": _urteil("devils_advocate", "kritisch")})
        assert k.grund == "gefaehrdet"

    def test_starke_bewegung_vor_geprueft(self):
        k = kachel(_pos(), "depot", _bew(day=-BEWEGUNG_PROZENT), {
            "storychecker": _urteil("storychecker", "intact")})
        assert k.grund == "bewegung"

    def test_sonst_der_juengste_satz(self):
        k = kachel(_pos(), "depot", _bew(day=1.0), {
            "storychecker": _urteil("storychecker", "intact", "Alt.", tag=1),
            "consensus_gap": _urteil("consensus_gap", "stabil", "Neu.", tag=5),
        })
        assert (k.grund, k.satz, k.satz_agent) == ("geprueft", "Neu.", "consensus_gap")

    def test_ohne_urteil_nie_geprueft(self):
        k = kachel(_pos(), "depot", _bew(), {})
        assert k.grund == "nie" and k.satz is None

    def test_urteil_ohne_satz_ist_geprueft(self):
        k = kachel(_pos(), "depot", _bew(), {"storychecker": _urteil("storychecker", "intact", None)})
        assert k.grund == "geprueft" and k.satz is None


class TestZahlen:
    def test_watchlist_tag_aus_vortag(self):
        assert tagesprozent(None, 105.0, 100.0) == pytest.approx(5.0)

    def test_depot_tag_aus_bewertung(self):
        assert tagesprozent(-1.5, 105.0, 100.0) == -1.5

    def test_watchlist_ohne_seit_kauf(self):
        k = kachel(_pos(), "watchlist", _bew(day=1.0, pnl=40.0))
        assert k.seit_kauf_prozent is None

    def test_watchlist_seit_aufnahme(self):
        k = kachel(_pos(), "watchlist", _bew(kurs=110.0), aufnahme_kurs=100.0)
        assert k.seit_aufnahme_prozent == pytest.approx(10.0)
        assert kachel(_pos(), "depot", _bew(kurs=110.0), aufnahme_kurs=100.0).seit_aufnahme_prozent is None
        assert kachel(_pos(), "watchlist", _bew(kurs=110.0)).seit_aufnahme_prozent is None

    def test_rendite_in_prozent(self):
        assert kachel(_pos(), "depot", _bew(rendite=0.034)).dividende_prozent == pytest.approx(3.4)

    def test_alle_urteile_auf_der_kachel(self):
        urteile = {"storychecker": _urteil("storychecker", "intact"),
                   "watchlist_checker": _urteil("watchlist_checker", "passend")}
        assert [u.agent for u in kachel(_pos(), "depot", _bew(), urteile).urteile] == ["storychecker"]
        assert {u.agent for u in kachel(_pos(), "watchlist", _bew(), urteile).urteile} == {
            "storychecker", "watchlist_checker"}

    def test_farbe_haengt_an_der_anlageklasse(self):
        k = kachel(_pos(anlageart="ETF"), "depot", _bew())
        assert (k.klasse, k.anlageklasse) == ("ETF", "Aktie")


class TestSortierung:
    def test_nach_vorrang_dann_name(self):
        ks = [
            kachel(_pos(1, "Zeta"), "depot", _bew(), {"storychecker": _urteil("storychecker", "intact")}),
            kachel(_pos(2, "Alpha"), "depot", _bew(), {}),
            kachel(_pos(3, "Beta"), "depot", _bew(day=-6.0)),
            kachel(_pos(4, "Gamma"), "depot", _bew(day=9.0)),
            kachel(_pos(5, "Omega"), "depot", _bew(), {"storychecker": _urteil("storychecker", "gefährdet")}),
        ]
        assert [k.name for k in sortiert(ks)] == ["Omega", "Gamma", "Beta", "Zeta", "Alpha"]


class TestHtml:
    def test_satz_des_modells_wird_escaped(self):
        k = kachel(_pos(), "depot", _bew(), {
            "storychecker": _urteil("storychecker", "intact", '<script>alert(1)</script>')})
        html = inhalt_html(k)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_kopfzeile_escaped(self):
        k = kachel(_pos(ticker="<X>", anlageart="<b>"), "depot", _bew())
        html = unter_html(k)
        assert "<b>&lt;X&gt;</b>" in html and "&lt;b&gt;" in html

    def test_farbe_nur_als_hex(self):
        k = kachel(_pos(), "depot", _bew())
        assert "#2F5D8A" in farbe_css(k, "#2F5D8A")
        boese = farbe_css(k, "red;} body{display:none")
        assert "display:none" not in boese and "#5E6B7A" in boese

    def test_seit_aufnahme_chip(self):
        k = kachel(_pos(), "watchlist", _bew(kurs=110.0), aufnahme_kurs=100.0)
        assert "+10,00 % seit Aufnahme" in inhalt_html(k)

    def test_nie_geprueft_steht_da(self):
        assert "Noch nie geprüft." in inhalt_html(kachel(_pos(), "depot", _bew(), {}))


class TestKaestchen:
    def test_storychecker_ascii_urteil_findet_wort(self):
        k = kachel(_pos(), "depot", _bew(), {"storychecker": _urteil("storychecker", "gefaehrdet")})
        assert urteil_label(k.urteile[0]) == "Storychecker Gefährdet"

    def test_nach_text_sortiert(self):
        k = kachel(_pos(), "watchlist", _bew(), {
            "storychecker": _urteil("storychecker", "gemischt"),
            "devils_advocate": _urteil("devils_advocate", "fragil"),
            "consensus_gap": _urteil("consensus_gap", "stabil"),
        })
        assert [u.agent for u in urteile_sortiert(k)] == ["devils_advocate", "consensus_gap", "storychecker"]

    def test_ziele(self):
        assert ziel("depot").endswith("pages/position_dashboard.py")
        assert ziel("depot", "devils_advocate").endswith("pages/position_dashboard.py")
        assert ziel("watchlist", "storychecker").endswith("pages/watchlist_analysis.py")
        assert ziel("watchlist", "watchlist_checker").endswith("pages/watchlist_checker.py")
        assert Path(ziel("depot")).is_file()
