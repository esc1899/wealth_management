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

def test_bewegungen_nachrichten_sucht_die_staerksten_einmal(tmp_path, monkeypatch):
    from agents.news_agent import NewsAgent
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

    gesucht = []

    async def start_run(self, tickers, ticker_names, skill_name, skill_prompt, user_context, repo,
                        websuche_pflicht=False):
        assert websuche_pflicht and skill_name == bewegung.LAUF
        assert set(ticker_names) == set(tickers)          # nur Ticker und Name
        gesucht.append(tickers[0])
        return repo.save_run(skill_name, tickers, f"## {tickers[0]} — x\n- Grund\n"), ""
    monkeypatch.setattr(NewsAgent, "start_run", start_run)

    zeilen = []
    assert d.bewegungen_nachrichten(aus=zeilen.append) == 3
    assert gesucht == ["SND.DE", "RMS.PA", "SAP.DE"]
    assert d.bewegungen_nachrichten(aus=zeilen.append) == 0      # Deckel erreicht, nichts doppelt
    assert "keine neue" in zeilen[-1]
