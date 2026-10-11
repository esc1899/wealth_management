"""Was die Titelseite rechnet: Urteilsband, Zaehlung der Urteile, Kursveraenderung."""

from datetime import date, datetime, timezone
from types import SimpleNamespace as NS

from core.titelseite import band, kurs_veraenderung, symbol, urteile_zaehlen
from core.ui.verdicts import VERDICT_CONFIGS


def _a(agent, tag, verdict="fair", summary=None):
    return NS(agent=agent, verdict=verdict, summary=summary,
              created_at=datetime(2026, tag[0], tag[1], 9, tzinfo=timezone.utc))


VON, BIS = date(2026, 3, 1), date(2026, 10, 11)


class TestBand:
    def test_urteil_gilt_bis_zum_naechsten_das_letzte_bis_heute(self):
        s = band([_a("fundamental_analyzer", (5, 1), "fair"), _a("fundamental_analyzer", (8, 1), "überbewertet")],
                 ["fundamental_analyzer"], VON, BIS)
        assert [(x.von, x.bis, x.verdict) for x in s] == [
            (date(2026, 5, 1), date(2026, 8, 1), "fair"),
            (date(2026, 8, 1), BIS, "überbewertet"),
        ]

    def test_urteil_vor_dem_fenster_beginnt_am_rand(self):
        s = band([_a("storychecker", (1, 10), "intact")], ["storychecker"], VON, BIS)
        assert len(s) == 1 and s[0].von == VON and s[0].geprueft_am == date(2026, 1, 10)

    def test_abgeloestes_urteil_vor_dem_fenster_faellt_weg(self):
        s = band([_a("storychecker", (1, 10), "intact"), _a("storychecker", (2, 1), "gemischt")],
                 ["storychecker"], VON, BIS)
        assert [x.verdict for x in s] == ["gemischt"]

    def test_am_selben_tag_zaehlt_das_letzte(self):
        frueh = _a("storychecker", (6, 1), "intact")
        spaet = NS(**{**vars(frueh), "verdict": "gefährdet",
                      "created_at": frueh.created_at.replace(hour=18)})
        s = band([spaet, frueh], ["storychecker"], VON, BIS)
        assert [x.verdict for x in s] == ["gefährdet"]

    def test_check_ohne_urteil_hat_keine_strecke_fremde_agenten_fehlen(self):
        s = band([_a("sector_rotation", (6, 1))], ["storychecker", "consensus_gap"], VON, BIS)
        assert s == []


def test_symbol_findet_ascii_schreibweise():
    assert symbol("gefaehrdet", VERDICT_CONFIGS["storychecker"]) == "🔴"
    assert symbol("unbekannt", VERDICT_CONFIGS["storychecker"]) == "⚪"


def test_urteile_zaehlen():
    assert urteile_zaehlen(["🟢", "🔴", "🟠", "🟡", None]) == {
        "positiv": 1, "kritisch": 2, "mitte": 1, "nie": 1, "alle": 5}


def _k(tag, kurs):
    return NS(date=date(2026, 1, 1).fromordinal(date(2026, 1, 1).toordinal() + tag), close_eur=kurs)


def test_kurs_veraenderung():
    verlauf = [_k(0, 100.0), _k(300, 110.0), _k(330, 120.0)]
    assert round(kurs_veraenderung(verlauf), 2) == 20.0
    assert round(kurs_veraenderung(verlauf, 30), 2) == round((120 / 110 - 1) * 100, 2)
    assert kurs_veraenderung(verlauf[:1]) is None
    assert kurs_veraenderung([_k(0, 100.0), _k(10, 101.0)], 30) is None
