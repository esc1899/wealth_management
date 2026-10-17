"""Starke Kursbewegung: Schwelle, Auswahl, Grund auf der Kachel und der Lauf im Job kurse
(core/bewegung.py, core/scheduler.py::bewegungen_nachrichten)."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from core import bewegung
from core.kacheln import kachel
from core.storage.app_config import AppConfigRepository
from core.storage.base import init_db, migrate_db
from core.storage.models import Position


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    migrate_db(c)
    yield c
    c.close()


def test_schwelle_einstellung_und_standard(conn):
    cfg = AppConfigRepository(conn)
    assert bewegung.schwelle(cfg) == bewegung.STANDARD_PROZENT
    bewegung.schwelle_setzen(cfg, 7.5)
    assert bewegung.schwelle(cfg) == 7.5
    cfg.set("bewegung_prozent", "Unsinn")
    assert bewegung.schwelle(cfg) == bewegung.STANDARD_PROZENT


def test_staerkste_mit_deckel_und_schon_gesuchten():
    bewegt = {"A": 5.0, "B": -9.0, "C": 4.1, "D": 3.9, "E": 6.0, "F": None}
    assert bewegung.staerkste(bewegt, 4.0, schon=[]) == [("B", -9.0), ("E", 6.0), ("A", 5.0)]
    # Heute schon zwei gesucht: nur noch einer, und nie derselbe zweimal.
    assert bewegung.staerkste(bewegt, 4.0, schon=["b", "X"]) == [("E", 6.0)]
    assert bewegung.staerkste(bewegt, 4.0, schon=["B", "E", "A"]) == []
    assert bewegung.staerkste(bewegt, 8.0, schon=[]) == [("B", -9.0)]


def test_heute_gesucht_nur_bewegungslaeufe_von_heute():
    heute = datetime.now(timezone.utc)
    laeufe = [
        SimpleNamespace(skill_name=bewegung.LAUF, tickers="SND.DE", created_at=heute),
        SimpleNamespace(skill_name="Standard", tickers="SAP.DE, ALV.DE", created_at=heute),
        SimpleNamespace(skill_name=bewegung.LAUF, tickers="MUV2.DE", created_at=datetime(2026, 1, 2, tzinfo=timezone.utc)),
    ]
    assert set(bewegung.heute_gesucht(laeufe, heute.astimezone().date())) == {"SND.DE"}


def test_grund_ist_der_erste_punkt():
    digest = ("## SND.DE — Schneider Electric\n"
              "- Schneider kündigt die Übernahme von X an (10.10.)\n"
              "- Analysten sehen Synergien\n"
              "- **Assessment:** 🟡 Worth monitoring\n")
    assert bewegung.grund(digest, "SND.DE") == "Schneider kündigt die Übernahme von X an (10.10.)"
    assert bewegung.grund(digest, "SAP.DE") is None
    assert bewegung.grund("## SND.DE — S\n- **Assessment:** 🟢", "SND.DE") is None


def _pos():
    return Position(id=1, name="Schneider Electric SE", ticker="SND.DE", asset_class="Aktie",
                    investment_type="Wertpapiere", unit="Stück", added_date=date(2026, 1, 1),
                    in_portfolio=True)


def test_kachel_nennt_den_grund_und_folgt_der_schwelle():
    from core.ui.kacheln import inhalt_html

    bew = SimpleNamespace(day_pnl_pct=6.0, pnl_pct=None, current_price_eur=200.0, dividend_yield_pct=None)
    k = kachel(_pos(), "depot", bew, {}, bewegung_grund="Übernahme angekündigt.")
    assert k.grund == "bewegung" and k.bewegung_grund == "Übernahme angekündigt."
    html = inhalt_html(k)
    assert "Übernahme angekündigt." in html and "Nachrichten" in html
    # Mit hoeherer Schwelle ist es keine starke Bewegung -- und dann auch kein Grund.
    k = kachel(_pos(), "depot", bew, {}, schwelle=8.0, bewegung_grund="Übernahme angekündigt.")
    assert k.grund != "bewegung" and k.bewegung_grund is None


# --- Der Lauf im Job kurse ------------------------------------------------------

def _dienst_mit_bewegungen(tmp_path):
    """Fuenf Titel, vier davon ueber 4 % -- der Deckel laesst drei durch."""
    from core.scheduler import AgentSchedulerService
    from core.storage.base import build_encryption_service, get_connection
    from core.storage.market_data import MarketDataRepository
    from core.storage.models import PriceRecord
    from core.storage.positions import PositionsRepository

    pfad = str(tmp_path / "b.db")
    c = get_connection(pfad)
    init_db(c)
    migrate_db(c)
    d = AgentSchedulerService(db_path=pfad, encryption_key="test-key", anthropic_api_key="k",
                              default_claude_model="claude-sonnet-5-5")
    enc = build_encryption_service("test-key", d._salt_path)
    positionen, markt = PositionsRepository(c, enc), MarketDataRepository(c)
    for name, ticker, prozent, depot in [("Schneider", "SND.DE", 7.0, True), ("Hermes", "RMS.PA", -5.0, False),
                                         ("SAP", "SAP.DE", 4.5, True), ("Allianz", "ALV.DE", 4.2, True),
                                         ("Munich Re", "MUV2.DE", 1.0, True)]:
        positionen.add(Position(asset_class="Aktie", investment_type="Wertpapiere", name=name, ticker=ticker,
                                unit="Stück", added_date=date(2026, 1, 1), in_portfolio=depot,
                                in_watchlist=not depot))
        markt.upsert_price(PriceRecord(symbol=ticker, price_eur=100 * (1 + prozent / 100), currency_original="EUR",
                                       price_original=100.0, exchange_rate=1.0,
                                       fetched_at=datetime.now(timezone.utc), previous_close_eur=100.0))
    c.close()
    return d, pfad


def test_bewegungen_nachrichten_sucht_die_staerksten_einmal(tmp_path, monkeypatch):
    from agents.news_agent import NewsAgent

    d, _ = _dienst_mit_bewegungen(tmp_path)
    gesucht = []

    async def start_run(self, tickers, ticker_names, skill_name, skill_prompt, user_context, repo,
                        websuche_pflicht=False, max_suchen=None):
        assert websuche_pflicht and skill_name == bewegung.LAUF and max_suchen == bewegung.SUCHEN
        assert set(ticker_names) == set(tickers)          # nur Ticker und Name
        gesucht.append(tickers[0])
        return repo.save_run(skill_name, tickers, f"## {tickers[0]} — x\n- Grund\n"), ""
    monkeypatch.setattr(NewsAgent, "start_run", start_run)

    zeilen = []
    assert d.bewegungen_nachrichten(aus=zeilen.append) == 3
    assert gesucht == ["SND.DE", "RMS.PA", "SAP.DE"]
    assert d.bewegungen_nachrichten(aus=zeilen.append) == 0      # Deckel erreicht, nichts doppelt
    assert "keine neue" in zeilen[-1]


def test_bewegung_nimmt_das_modell_ihres_bereichs(tmp_path, monkeypatch):
    from agents.news_agent import NewsAgent
    from core import pruefung
    from core.storage.base import get_connection

    d, pfad = _dienst_mit_bewegungen(tmp_path)
    c = get_connection(pfad)
    cfg = AppConfigRepository(c)
    cfg.set("model_public_news", "claude-sonnet-5-5")
    pruefung.modell_setzen(cfg, "bewegung", "claude-haiku-4-5")
    c.close()
    gebaut = []
    monkeypatch.setattr(type(d), "_make_scheduled_llm",
                        lambda self, agent, model, conn: gebaut.append((agent, model)) or SimpleNamespace())

    async def start_run(self, tickers, ticker_names, skill_name, skill_prompt, user_context, repo,
                        websuche_pflicht=False, max_suchen=None):
        return repo.save_run(skill_name, tickers, "x"), ""
    monkeypatch.setattr(NewsAgent, "start_run", start_run)
    d.bewegungen_nachrichten(aus=lambda z: None)
    assert gebaut == [(bewegung.AGENT, "claude-haiku-4-5")]   # gebucht als bewegung, nicht news_digest


def test_bewegung_ohne_eigenes_modell_folgt_dem_news_digest(conn):
    from core import pruefung

    cfg = AppConfigRepository(conn)
    cfg.set("model_public_news", "claude-sonnet-5-5")
    assert pruefung.modell(cfg, "bewegung") == "claude-sonnet-5-5"


def test_bewegung_als_batch_einmal_eingereicht_und_abgeholt(tmp_path, monkeypatch):
    import json

    from config import config
    from core.llm.claude import ClaudeProvider
    from core.storage.base import get_connection
    from core.storage.batch_queue import BatchQueueRepository
    from core.storage.news import NewsRepository

    d, pfad = _dienst_mit_bewegungen(tmp_path)
    monkeypatch.setattr(config, "USE_BATCH_API", True)
    eingereicht = []

    async def submit_batch(self, requests):
        eingereicht.append(requests)
        return "msgbatch_1"
    monkeypatch.setattr(ClaudeProvider, "submit_batch", submit_batch)

    zeilen = []
    assert d.bewegungen_nachrichten(aus=zeilen.append, batch=True) == 3
    assert [r["custom_id"] for r in eingereicht[0]] == ["bewegung_0", "bewegung_1", "bewegung_2"]
    assert "Schneider" in json.dumps(eingereicht[0][0]["params"]["messages"])
    assert eingereicht[0][0]["params"]["tools"][0]["max_uses"] == bewegung.SUCHEN
    # Solange der Batch offen ist, gilt er als gesucht: kein zweites Mal.
    assert d.bewegungen_nachrichten(aus=zeilen.append, batch=True) == 0
    assert len(eingereicht) == 1
    assert d.wartet()["was"] == ["Kursbewegung"]

    # Abholen: je Titel ein Lauf "Bewegung", wie live; die Suche bucht unter "bewegung".
    c = get_connection(pfad)
    offen = BatchQueueRepository(c).get_pending()[0]
    assert offen.agent_name == bewegung.AGENT
    gebucht = []
    monkeypatch.setattr(type(d), "_book_batch_usage",
                        staticmethod(lambda agent, skill, message, conn, lauf=None: gebucht.append(agent)))
    def antwort(cid, treffer):
        suche = SimpleNamespace(type="web_search_tool_result", content=treffer)
        text = SimpleNamespace(type="text", text="## RMS.PA — Hermes\n- Prognose gesenkt\n")
        return SimpleNamespace(custom_id=cid, result=SimpleNamespace(
            type="succeeded", message=SimpleNamespace(content=[suche, text], model="claude-haiku-4-5")))
    # Ohne einen Treffer kein Lauf (wie live): Der Titel darf am selben Tag noch einmal.
    assert d._process_batch_results(offen.agent_name, offen.skill_name,
                                    [antwort("bewegung_1", []), antwort("bewegung_1", [{"url": "u"}])],
                                    c, offen.kontext) == (1, 1)
    assert gebucht == [bewegung.AGENT, bewegung.AGENT]
    lauf = NewsRepository(c).list_runs(limit=5)[0]
    assert lauf.skill_name == bewegung.LAUF and lauf.tickers == "RMS.PA"
    assert bewegung.grund(lauf.result, "RMS.PA") == "Prognose gesenkt"
    c.close()
