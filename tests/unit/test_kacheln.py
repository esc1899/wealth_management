"""Die Kachel je Titel: welcher Satz oben steht, wie sortiert wird, was escaped wird."""

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.kacheln import BEWEGUNG_PROZENT, kachel, sortiert, tagesprozent
from core.storage.models import Position, PositionAnalysis
from core.ui.kacheln import farbe_css, inhalt_html, monogramm, unter_html, urteil_label, urteile_sortiert, ziel


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

    def test_rohstoff_ohne_checks_auch_ohne_alte_urteile(self):
        k = kachel(_pos(), "depot", _bew(day=1.0), {
            "storychecker": _urteil("storychecker", "gefaehrdet", "Alt.")}, pruefbar=False)
        assert (k.grund, k.satz, k.urteile, k.nie) == ("ohne", None, [], [])
        assert "Keine Checks für Aktie" in inhalt_html(k)

    def test_rohstoff_mit_starker_bewegung(self):
        k = kachel(_pos(), "depot", _bew(day=-BEWEGUNG_PROZENT), {}, pruefbar=False)
        assert k.grund == "bewegung"

    def test_edelmetall_ist_nicht_pruefbar(self):
        from core.pruefung import pruefbar
        assert pruefbar(SimpleNamespace(asset_class="Aktie"))
        assert pruefbar(SimpleNamespace(asset_class="Unbekannt"))
        assert not pruefbar(SimpleNamespace(asset_class="Edelmetall"))
        assert sortiert([kachel(_pos(1), "depot", _bew(), {}, pruefbar=False),
                         kachel(_pos(2), "depot", _bew(), {})])[0].position_id == 2

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

    def test_monogramm_nur_buchstaben_und_ziffern(self):
        assert monogramm(kachel(_pos(ticker="SIE.DE"), "depot", _bew())) == "SIE"
        assert monogramm(kachel(_pos(ticker='a"};x'), "depot", _bew())) == "AX"
        assert 'content: "SIE"' in farbe_css(kachel(_pos(ticker="SIE.DE"), "depot", _bew()), "#2F5D8A")

    def test_seit_aufnahme_chip(self):
        k = kachel(_pos(), "watchlist", _bew(kurs=110.0), aufnahme_kurs=100.0)
        assert "+10,00 % seit Aufnahme" in inhalt_html(k)

    def test_nie_geprueft_steht_da(self):
        assert "Noch nie geprüft." in inhalt_html(kachel(_pos(), "depot", _bew(), {}))


class TestKaestchen:
    def test_storychecker_ascii_urteil_findet_wort(self):
        k = kachel(_pos(), "depot", _bew(), {"storychecker": _urteil("storychecker", "gefaehrdet")})
        assert urteil_label(k.urteile[0]) == "Story gefährdet"

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
        # Seit dem Durchgang (11.10.2026) auch der Watchlist Checker: seine Seite entfaellt.
        assert ziel("watchlist", "watchlist_checker").endswith("pages/watchlist_analysis.py")
        assert Path(ziel("depot")).is_file()


class TestBloecke:
    """Seit 23.10.2026 stehen die Kacheln in Blöcken (Aktien, Geldwerte, Sachwerte), oben je
    Block ein Feld mit dem, was in ihm auffällt."""

    BLOCK = {"Aktie": "aktien", "Rentenfonds": "geldwerte", "Edelmetall": "sachwerte"}

    def _k(self, pid, name, klasse, urteile=None, day=None):
        p = Position(id=pid, name=name, ticker=f"T{pid}", asset_class=klasse, investment_type="x",
                     unit="Stück", added_date=date(2026, 1, 1), in_portfolio=True)
        return kachel(p, "depot", _bew(day=day), urteile or {}, pruefbar=klasse != "Edelmetall")

    def _bloecke(self, ks):
        from core.kacheln import bloecke
        return bloecke(ks, self.BLOCK.get, ["aktien", "geldwerte", "sachwerte"])

    def test_reihenfolge_der_bloecke_und_vorrang_im_block(self):
        ks = [self._k(1, "Gold", "Edelmetall"),
              self._k(2, "Zeta", "Aktie", {"storychecker": _urteil("storychecker", "intact")}),
              self._k(3, "Alpha", "Aktie", {"storychecker": _urteil("storychecker", "gefährdet")})]
        bs = self._bloecke(ks)
        assert [b.name for b in bs] == ["aktien", "sachwerte"]   # Geldwerte leer: faellt weg
        assert [k.name for k in bs[0].kacheln] == ["Alpha", "Zeta"]
        assert bs[0].zahl == {"gefaehrdet": 1, "bewegung": 0, "nie": 0}

    def test_unbekannte_klasse_steht_zuletzt(self):
        bs = self._bloecke([self._k(1, "X", "Neuland"), self._k(2, "A", "Aktie")])
        assert [b.name for b in bs] == ["aktien", "sonstige"]

    def test_feld_nennt_die_auffaelligen_titel(self):
        from core.ui.kacheln import feld_satz
        ks = [self._k(1, "Alpha", "Aktie", {"storychecker": _urteil("storychecker", "gefährdet")}),
              self._k(2, "Beta", "Aktie", day=-7.0), self._k(3, "Gamma", "Aktie"),
              self._k(4, "Delta", "Aktie"),
              self._k(5, "Eta", "Aktie", {"storychecker": _urteil("storychecker", "intact")})]
        satz = feld_satz(self._bloecke(ks)[0])
        assert satz.startswith("Alpha ist gefährdet, Beta bewegt sich heute um")
        # Drei mit Namen (nie geprüft nach Name: Delta vor Gamma), der vierte als "weitere".
        assert satz.endswith("Delta wurde noch nie geprüft und 1 weitere.")
        assert "Eta" not in satz

    def test_ruhiger_block(self):
        from core.ui.kacheln import feld_satz, felder_html
        b = self._bloecke([self._k(1, "Gold", "Edelmetall")])[0]
        assert feld_satz(b) == "Nichts, was handeln lässt."
        assert "wk-feld ruhig" in felder_html([b]) and "wk-marke" not in felder_html([b])

    def test_feld_escaped_und_springt_zum_block(self):
        from core.ui.kacheln import block_kopf_html, felder_html
        b = self._bloecke([self._k(1, "<b>Böse</b>", "Aktie")])[0]
        html = felder_html([b])
        assert "<b>Böse</b>" not in html and "&lt;b&gt;Böse&lt;/b&gt;" in html
        assert 'href="#block-aktien"' in html and 'id="block-aktien"' in block_kopf_html(b)
        assert "1 nie geprüft" in html and "1 Position" in html


def test_block_kopf_ohne_anker_fuer_die_seite_positionen():
    from core.ui.kacheln import block_kopf
    assert 'id="block-geldwerte"' in block_kopf("geldwerte", 2)
    html = block_kopf("geldwerte", 2, anker=False)
    assert " id=" not in html and "Geldwerte" in html and "2 Positionen" in html


class TestStandJeCheck:
    """02.11.2026: Story und Fundamental scheiterten am 01.11. im Batch, die Kacheln zeigten ihre
    Urteile vom 01.10. ohne Datum -- als sei alles gelaufen."""

    @staticmethod
    def _dg(checks, tag=20, beendet=True, fehler=None):
        from datetime import timezone
        from core.storage.durchgaenge import Durchgang
        beginn = datetime(2026, 10, tag, 8, 0, tzinfo=timezone.utc)
        return Durchgang(id=tag, liste="depot", position_id=1, ausloeser="job", checks=tuple(checks),
                         begonnen=beginn, beendet=beginn if beendet else None, fehler=fehler)

    def _kachel(self, durchgaenge, urteile=None):
        urteile = urteile if urteile is not None else {
            "storychecker": _urteil("storychecker", "intact", tag=1),
            "consensus_gap": _urteil("consensus_gap", "stabil", tag=21)}
        return kachel(_pos(), "depot", _bew(), urteile,
                      agenten=("storychecker", "consensus_gap"), durchgaenge=durchgaenge)

    def test_gescheitert_altes_urteil_grau_dahinter(self):
        from core.ui.kacheln import kaestchen_text
        k = self._kachel([self._dg(["storychecker", "consensus_gap"], fehler="storychecker: ImportError")])
        assert k.staende["storychecker"].zustand == "gescheitert"
        assert "consensus_gap" not in k.staende              # sein Urteil ist aus diesem Durchgang
        text, _, grau = kaestchen_text(k, "storychecker", k.urteile[0])
        assert grau and text == "Story gescheitert am 20.10.2026 · zuletzt intakt, 01.10.2026"

    def test_laeuft_solange_der_durchgang_offen_ist(self):
        k = self._kachel([self._dg(["storychecker"], beendet=False)])
        assert k.staende["storychecker"].zustand == "laeuft"

    def test_beendet_ohne_urteil(self):
        k = self._kachel([self._dg(["storychecker"])])
        assert k.staende["storychecker"].zustand == "ohne"

    def test_zaehlt_der_juengste_durchgang_mit_diesem_check(self):
        """Das Nachholen laeuft nur mit den gescheiterten Checks; ein juengerer Durchgang ohne
        den Check aendert an seinem Stand nichts."""
        k = self._kachel([self._dg(["consensus_gap"], tag=25),
                          self._dg(["storychecker", "consensus_gap"], tag=20, fehler="storychecker: x")])
        assert k.staende["storychecker"].zustand == "gescheitert"

    def test_neues_urteil_ist_kein_stand_und_traegt_sein_datum(self):
        from core.ui.kacheln import kaestchen_text
        k = self._kachel([self._dg(["storychecker"], tag=1)],
                         {"storychecker": _urteil("storychecker", "intact", tag=2)})
        assert k.staende == {}
        text, _, grau = kaestchen_text(k, "storychecker", k.urteile[0])
        assert not grau and text == "Story intakt · 02.10.2026"

    def test_nie_geprueft_aber_laeuft(self):
        from core.ui.kacheln import kaestchen_text
        k = self._kachel([self._dg(["storychecker"], beendet=False)], {})
        text, icon, grau = kaestchen_text(k, "storychecker", None)
        assert grau and text == "Story läuft seit 20.10.2026" and icon == "⏳"
