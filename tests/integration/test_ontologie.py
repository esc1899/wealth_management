"""Ontologie und Formen (22.10.2026, `ontologie/`, ARCHITECTURE.md "Ontologie und Formen").

Kein Wissensgraph und keine echten Daten: Der Demo-Seeder und das Repository fuellen je eine
Datenbank in :memory:, die Signaturen der Agenten und Dienste sagen, was ein Weg zu einem
Modell nimmt; alles wird als RDF projiziert, gegen die Formen geprueft und verworfen. Geprueft
wird fuenferlei:

- Formen und Bild nennen nur Begriffe, die die Ontologie kennt; jeder Begriff hat ein Wort auf
  Deutsch und Englisch; jede FIBO-Adresse ist eine aus FIBO (nur ihre Form, ohne Netz).
- Die Bezeichnungen sind die der YAML: Anlagetypen, -klassen, -arten und ihre Schalter.
- Jedes Feld von `Position` hat eine Schutzstufe, und was die Ontologie "verschluesselt" nennt,
  verschluesselt `PositionsRepository`. Die Wege sind die Toepfe des Guards.
- Seeder, Repository und Code erfuellen alle Formen: Code und Regelwerk sagen dasselbe.
- Jede Form schlaegt an, wenn man die Regel bricht -- sonst bewiese das Gruen nichts.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from rdflib import RDF, RDFS, Graph, Literal, URIRef
from rdflib.namespace import SKOS

from core.encryption import EncryptionService
from core.services.position_story_service import PositionStoryService
from core.storage.base import init_db, migrate_db
from core.storage.models import Position
from core.storage.positions import PositionsRepository
from ontologie import bild
from ontologie import projektion as p
from ontologie.projektion import WM
from tests.integration.test_demo_seed import _mock_download, _mock_fast_info
from tests.unit.test_architecture_guards import (
    CLOUD_AGENTS,
    LOCAL_AGENTS,
    NON_LLM_AGENTS,
    PRIVACY_EXCEPTIONS,
)

WURZEL = Path(__file__).resolve().parents[2]
#: Die Wege, deren Signatur der Test liest: alle Agenten und der eine Dienst ohne Agent.
DIENSTE = [PositionStoryService]
KLASSEN = CLOUD_AGENTS + LOCAL_AGENTS + NON_LLM_AGENTS + DIENSTE


@pytest.fixture(scope="module")
def o() -> Graph:
    return p.ontologie()


def _neue_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    migrate_db(conn)
    return conn


@pytest.fixture
def seed_db():
    """Die Demo, wie `scripts/seed_demo.py` sie baut -- ohne Netz."""
    def _ticker(t):
        m = MagicMock()
        m.fast_info = _mock_fast_info(t)
        return m

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    with patch("yfinance.download", side_effect=_mock_download), \
            patch("yfinance.Ticker", side_effect=_ticker):
        from scripts.seed_demo import seed
        seed(conn=conn)
    yield conn
    conn.close()


@pytest.fixture
def enc() -> EncryptionService:
    return EncryptionService("nur-im-test", b"0123456789abcdef")


@pytest.fixture
def repo_db(enc):
    """Was die Demo nicht hat, ueber das Repository: ISIN, WKN, Anlageart, Kandidat, eine
    Position in beiden Listen, verschluesselt wie in echt."""
    conn = _neue_db()
    repo = PositionsRepository(conn, enc)
    heute = date(2026, 10, 22)
    repo.add(Position(asset_class="Aktie", investment_type="Wertpapiere", name="Siemens",
                      isin="DE0007236101", wkn="723610", ticker="SIE.DE", anlageart="Einzelaktie",
                      quantity=10, unit="Stück", purchase_price=150.0,
                      purchase_date=date(2022, 1, 10), notes="nach der Hauptversammlung",
                      story="Automatisierung", story_skill="Qualität", empfehlung="Kaufen",
                      recommendation_source="Josef", strategy="Langfristig", added_date=heute,
                      in_portfolio=True, in_watchlist=True))
    repo.add(Position(asset_class="Aktienfonds", investment_type="Wertpapiere",
                      name="iShares Core MSCI World", isin="IE00B4L5Y983", ticker="IWDA.AS",
                      anlageart="ETF", unit="Stück", added_date=heute, in_watchlist=True))
    repo.add(Position(asset_class="Aktie", investment_type="Wertpapiere", name="Kandidat AG",
                      ticker="KAND", unit="Stück", added_date=heute))
    repo.add(Position(asset_class="Bargeld", investment_type="Bargeld", name="Girokonto",
                      anlageart="Girokonto", quantity=1, unit="Stück", purchase_price=5000.0,
                      extra_data={"bank": "Test"}, added_date=heute, in_portfolio=True))
    yield conn
    conn.close()


def _alles(seed_db, repo_db) -> list[Graph]:
    return [p.positionen(seed_db, "demo"), p.positionen(repo_db, "repo"), p.wege(KLASSEN)]


# --- Ontologie, Formen und Bild passen zusammen ---------------------------------------------------


def test_formen_nennen_nur_begriffe_der_ontologie(o):
    assert bild.unbekannte_begriffe(o, p.formen()) == []


def test_projektion_nennt_nur_begriffe_der_ontologie(o, seed_db, repo_db):
    bekannt = bild.bekannt(o)
    for g in _alles(seed_db, repo_db):
        genannt = {t for t in g.all_nodes()
                   if isinstance(t, URIRef) and str(t).startswith(str(WM))}
        assert genannt <= bekannt, sorted(map(str, genannt - bekannt))


def test_jeder_begriff_hat_ein_wort_auf_deutsch_und_englisch(o):
    eigene = {s for s in bild.bekannt(o)
              if (s, RDF.type, None) in o and not str(s).startswith(str(WM) + "unbekannt")}
    ohne = []
    for s in eigene:
        sprachen = {getattr(w, "language", None)
                    for eig in (RDFS.label, SKOS.prefLabel) for w in o.objects(s, eig)}
        if not {"de", "en"} <= sprachen:
            ohne.append(bild.kurz(s))
    assert not ohne, f"Ohne deutsches und englisches Wort: {sorted(ohne)}"


def test_fibo_adressen_haben_die_form_von_fibo(o):
    """Ohne Netz laesst sich nicht pruefen, ob es die Klasse gibt (das geschah beim Schreiben,
    gegen die RDF-Dateien von FIBO) -- aber ein Tippfehler im Praefix faellt hier auf."""
    muster = re.compile(r"^https://spec\.edmcouncil\.org/fibo/ontology/(FBC|SEC|FND|BE)/\w+/\w+/[A-Z]\w+$")
    adressen = {str(m) for m in o.objects(None, SKOS.closeMatch)}
    assert adressen and all(muster.match(a) for a in adressen), sorted(adressen)


def test_das_bild_zeichnet_jede_klasse_in_beiden_sprachen(o):
    for lang in ("de", "en"):
        d = bild.schema(lang=lang)
        assert d["unbekannt"] == []
        ids = {k["id"] for k in d["knoten"]}
        assert {str(WM.Titel), str(WM.Position), str(WM.Weg), str(WM.Feld)} <= ids
        assert all(e["von"] in ids and e["zu"] in ids for e in d["kanten"])
    assert "Arten von Dingen" in bild.schema(lang="de")["satz"]
    assert "kinds of things" in bild.schema(lang="en")["satz"]


def test_die_seite_zeigt_satz_bild_und_klapper():
    """Die Seite "Ontologie" unter Einstellungen: erst der Satz, dann das Bild, dann die Grenze
    und die Regeln im Klapper. Keine Datenbank, kein Modell."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(WURZEL / "pages" / "ontologie.py")
    at.run(timeout=30)
    assert not at.exception, at.exception
    assert any("Arten von Dingen" in m.value for m in at.markdown)
    klapper = [e.label for e in at.expander]
    assert any("Privacy-Grenze" in k for k in klapper) and any("Regeln" in k for k in klapper)
    assert any("Storychecker" in m.value for m in at.markdown)


def test_das_bild_laesst_sich_zeichnen():
    from core.ui import ontologie_bild

    seite = ontologie_bild.html(bild.schema())
    assert "vis-network" in seite or "vis.Network" in seite
    assert "Kaufdatum" in seite  # ohne Umlaut: pyvis schreibt sie als ü


# --- Die Bezeichnungen sind die der YAML ----------------------------------------------------------


def _yaml() -> dict:
    return yaml.safe_load((WURZEL / "config" / "asset_classes.yaml").read_text())["asset_classes"]


def test_anlageklassen_und_typen_wie_in_der_yaml(o):
    klassen = p.begriffe(o, WM.Anlageklasse)
    typen = p.begriffe(o, WM.Anlagetyp)
    y = _yaml()
    assert set(klassen) == set(y)
    assert set(typen) == {v["investment_type"] for v in y.values()}
    for name, v in y.items():
        k = klassen[name]
        assert o.value(k, WM.gehoertZuTyp) == typen[v["investment_type"]], name
        assert o.value(k, WM.watchlistFaehig).toPython() is bool(v.get("watchlist_eligible")), name
        assert o.value(k, WM.pruefbar).toPython() is bool(v.get("pruefbar", True)), name
        assert o.value(k, WM.kursAutomatisch).toPython() is bool(v.get("auto_fetch")), name


def test_anlagearten_wie_in_der_yaml(o):
    klassen = p.begriffe(o, WM.Anlageklasse)
    arten = p.begriffe(o, WM.Anlageart)
    y = _yaml()
    assert set(arten) == {a for v in y.values() for a in v.get("anlagearten", [])}
    for name, v in y.items():
        bei = {lab for a in o.subjects(WM.moeglichBei, klassen[name])
               for lab in o.objects(a, SKOS.prefLabel) if lab.language == "de"}
        assert {str(x) for x in bei} == set(v.get("anlagearten", [])), name


# --- Felder und Wege sind die des Codes -----------------------------------------------------------


def test_jedes_feld_hat_eine_schutzstufe(o):
    """Wer `Position` oder `PortfolioStory` ein Feld gibt, sagt in `wealth.ttl`, wer es sehen
    darf."""
    assert set(p.felder(o)) == p.POSITION_FELDER | p.PORTFOLIO_FELDER


def test_die_portfolio_story_ist_ganz_privat(o):
    """Erik, 23.10.2026: Anders als die Story einer Position bleibt die Portfolio-Story lokal."""
    felder = p.felder(o)
    assert {str(o.value(felder[f], WM.schutz)) for f in p.PORTFOLIO_FELDER} == {str(WM.privat)}


def test_die_empfehlung_ist_privat_und_geht_an_keinen_cloud_weg(o):
    """Erik, 23.10.2026: Die Empfehlung ist privat; der Storychecker braucht sie nicht."""
    assert o.value(WM.empfehlung, WM.schutz) == WM.privat
    for k in CLOUD_AGENTS + DIENSTE:
        assert "empfehlung" not in p.genommene_felder(k), k.__name__


def _rohwerte_stimmen(o, enc, zeile, felder):
    for name, feld in felder.items():
        roh = zeile[name.split(".")[-1]]
        if roh is None:
            continue
        verschluesselt = o.value(feld, WM.verschluesselt).toPython()
        ist_token = isinstance(roh, str) and roh.startswith("gAAAAA")
        assert ist_token is verschluesselt, f"{name}: Ontologie sagt {verschluesselt}, Zeile {roh!r}"
        if ist_token:
            enc.decrypt(roh)


def test_verschluesselt_ist_was_das_repository_verschluesselt(o, enc, repo_db):
    zeile = repo_db.execute("SELECT * FROM positions WHERE name = 'Siemens'").fetchone()
    _rohwerte_stimmen(o, enc, zeile, {k: v for k, v in p.felder(o).items() if "." not in k})


def test_verschluesselt_wie_im_repository_der_portfolio_story(o, enc):
    from datetime import datetime, timezone

    from core.storage.models import PortfolioStory
    from core.storage.portfolio_story import PortfolioStoryRepository

    conn = _neue_db()
    jetzt = datetime(2026, 10, 23, tzinfo=timezone.utc)
    PortfolioStoryRepository(conn, enc).save(PortfolioStory(
        story="Ruhestand mit 60", target_year=2040, liquidity_need="2028: Wohnung",
        priority="Sicherheit", created_at=jetzt, updated_at=jetzt))
    zeile = conn.execute("SELECT * FROM portfolio_story").fetchone()
    _rohwerte_stimmen(o, enc, zeile, {k: v for k, v in p.felder(o).items()
                                      if k.startswith("PortfolioStory.")})
    conn.close()


def test_die_wege_sind_die_toepfe_des_guards(o):
    je_ort = {ort: {str(o.value(w, WM.imCode)) for w in o.subjects(WM.laeuftBei, ort)}
              for ort in (WM.cloud, WM.lokal, WM.ohneModell)}
    assert je_ort[WM.cloud] == {k.__name__ for k in CLOUD_AGENTS + DIENSTE}
    assert je_ort[WM.lokal] == {k.__name__ for k in LOCAL_AGENTS}
    assert je_ort[WM.ohneModell] == {k.__name__ for k in NON_LLM_AGENTS}
    ausnahmen = {str(o.value(w, WM.imCode)) for w in o.subjects(WM.ausnahme, None)}
    assert ausnahmen == {k.__name__ for k in PRIVACY_EXCEPTIONS}


def test_jeder_dienst_mit_cloud_modell_ist_ein_weg():
    """Ein Dienst, dem `state_services.py` ein Cloud-Modell gibt, steht in DIENSTE -- sonst
    liest niemand seine Signatur, und der Guard der Agenten sieht ihn nicht."""
    text = (WURZEL / "state_services.py").read_text(encoding="utf-8")
    gebaut = set()
    for block in re.split(r"\ndef ", text):
        if "_make_public_provider(" in block:
            gebaut |= set(re.findall(r"return (\w+)\(", block))
    assert gebaut == {k.__name__ for k in DIENSTE}


# --- Der Alltag erfuellt alle Formen --------------------------------------------------------------


def test_demo_repository_und_code_erfuellen_alle_formen(seed_db, repo_db):
    ergebnis = p.pruefen(*_alles(seed_db, repo_db))
    assert ergebnis.erfuellt, ergebnis.satz


def test_die_demo_hat_jede_rolle(seed_db, repo_db):
    g = p.positionen(seed_db, "demo") + p.positionen(repo_db, "repo")
    for rolle in (WM.Depotposition, WM.WatchlistEintrag, WM.Kandidat):
        assert (None, RDF.type, rolle) in g, rolle


# --- Jede Form schlaegt an, wenn man die Regel bricht ---------------------------------------------

BRUECHE_SQL = {
    "Eine ISIN hat zwölf Zeichen": "UPDATE positions SET isin = 'DE72361' WHERE name = 'Siemens'",
    "Eine WKN hat sechs Zeichen": "UPDATE positions SET wkn = '7236-10' WHERE name = 'Siemens'",
    "Ein Ticker ist ein Yahoo-Symbol": "UPDATE positions SET ticker = 'sie de' WHERE name = 'Siemens'",
    "genau eine Anlageklasse aus der YAML": "UPDATE positions SET asset_class = 'Aktien' WHERE name = 'Siemens'",
    "einen Anlagetyp, den die YAML kennt": "UPDATE positions SET investment_type = 'Edelmetalle' WHERE name = 'Siemens'",
    "Der Anlagetyp folgt aus der Anlageklasse": "UPDATE positions SET investment_type = 'Renten' WHERE name = 'Siemens'",
    "Eine Anlageart ist eine aus der YAML": "UPDATE positions SET anlageart = 'Aktienzertifikat' WHERE name = 'Siemens'",
    "möglich ist": "UPDATE positions SET anlageart = 'REIT' WHERE name = 'Siemens'",
    "Auf die Watchlist kommt nur": "UPDATE positions SET in_watchlist = 1 WHERE name = 'Girokonto'",
}


@pytest.mark.parametrize("meldung,sql", BRUECHE_SQL.items(), ids=list(BRUECHE_SQL))
def test_jede_datenform_schlaegt_an(repo_db, meldung, sql):
    repo_db.execute(sql)
    ergebnis = p.pruefen(p.positionen(repo_db))
    assert not ergebnis.erfuellt
    assert any(meldung in m for m, _ in ergebnis.verstoesse), ergebnis.satz


def _news_mit_position():
    """Ein Cloud-Agent, dem jemand die ganze Position gibt -- genau der Fehler, den die
    Grenze verhindern soll."""
    class NewsAgent:
        def fetch(self, position: Position) -> str:
            return position.name
    return NewsAgent


def _news_mit_menge():
    """Derselbe Fehler, ohne `Position`: ein einzelner Parameter, der wie ein Bestandsfeld heisst."""
    class NewsAgent:
        def fetch(self, ticker: str, quantity: float) -> str:
            return ticker
    return NewsAgent


def _news_mit_portfolio_story():
    """Die Portfolio-Story an einen Cloud-Agenten -- sie muss lokal bleiben."""
    from core.storage.models import PortfolioStory

    class NewsAgent:
        def fetch(self, ticker: str, ziel: PortfolioStory) -> str:
            return ticker
    return NewsAgent


def _news_mit_empfehlung():
    class NewsAgent:
        def fetch(self, ticker: str, empfehlung: str) -> str:
            return ticker
    return NewsAgent


BRUECHE_WEGE = {
    "nie den Bestand (ganze Position)": (lambda: p.wege([_news_mit_position()]), "nie den Bestand"),
    "nie die Portfolio-Story": (lambda: p.wege([_news_mit_portfolio_story()]), "nie den Bestand"),
    "nie die Empfehlung": (lambda: p.wege([_news_mit_empfehlung()]), "nie den Bestand"),
    "nie den Bestand (ein Parameter)": (lambda: p.wege([_news_mit_menge()]), "nie den Bestand"),
    "Ausnahme nur in der Cloud": (
        lambda: Graph().add((WM.DividendCalendarAgent, WM.ausnahme, Literal("weil"))),
        "Eine Ausnahme gibt es nur"),
    "Weg ohne Ort": (lambda: Graph().add((WM.NeuerAgent, RDF.type, WM.Weg)),
                     "Jeder Weg läuft an genau einem Ort"),
    "Feld ohne Kenntnis": (lambda: Graph().add((WM.NewsAgent, WM.nimmt, WM["unbekannt-geheim"])),
                           "nur Felder, die die Ontologie kennt"),
    "Feld mit zwei Stufen": (lambda: Graph().add((WM.stueckzahl, WM.schutz, WM.oeffentlich)),
                             "genau eine Schutzstufe"),
}


@pytest.mark.parametrize("name", list(BRUECHE_WEGE))
def test_jede_grenzform_schlaegt_an(name):
    bau, meldung = BRUECHE_WEGE[name]
    ergebnis = p.pruefen(bau())
    assert not ergebnis.erfuellt
    assert any(meldung in m for m, _ in ergebnis.verstoesse), ergebnis.satz


def test_der_storychecker_braucht_keine_ausnahme_mehr():
    """Seit 23.10.2026 nimmt er `PublicPosition` wie alle: nichts Privates, keine Empfehlung."""
    from agents.storychecker_agent import StorycheckerAgent

    nimmt = p.genommene_felder(StorycheckerAgent)
    felder = p.felder(p.ontologie())
    o = p.ontologie()
    assert "story" in nimmt
    assert all(o.value(felder[f], WM.schutz) != WM.privat for f in nimmt), sorted(nimmt)
