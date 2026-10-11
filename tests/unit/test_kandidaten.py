"""Kandidaten der Suche: ein Lauf legt Vorschläge in die stehende Liste, ein zweiter Fund zählt
hoch, ein Nein bleibt gemerkt, nach 60 Tagen ohne Berührung "Ignoriert" -- und die Strategien
erfahren nie, was im Depot liegt (core/kandidaten.py, core/storage/kandidaten.py)."""

from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from core import kandidaten
from core.encryption import EncryptionService
from core.pruefung import MOEGLICH, modell, modell_setzen
from core.storage.app_config import AppConfigRepository
from core.storage.base import init_db, migrate_db
from core.storage.kandidaten import IGNORIERT_NACH_TAGEN, KandidatenRepository
from core.storage.models import Position
from core.storage.positions import PositionsRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    migrate_db(c)
    yield c
    c.close()


@pytest.fixture
def positionen(conn):
    return PositionsRepository(conn, EncryptionService(os.urandom(16).hex(), os.urandom(16)))


@pytest.fixture
def repo(conn):
    return KandidatenRepository(conn)


def _vorschlag(ticker, name=None, story="These"):
    return {"ticker": ticker, "name": name or ticker, "asset_class": "Aktie", "notes": "", "story": story}


def _titel(positionen, ticker, depot=False, watchlist=False):
    return positionen.add(Position(asset_class="Aktie", investment_type="Wertpapiere", name=ticker,
                                   ticker=ticker, unit="Stück", added_date=date(2026, 1, 1),
                                   in_portfolio=depot, in_watchlist=watchlist,
                                   quantity=1 if depot else None))


class TestAufnehmen:
    def test_ein_vorschlag_wird_kandidat_auf_keiner_liste(self, positionen, repo):
        a = kandidaten.aufnehmen(positionen, repo, [_vorschlag("NESN.SW", "Nestlé")], "frei", "Dividende", 7)
        assert (a.neu, a.wieder, a.verworfen, a.bekannt) == (1, 0, 0, 0)
        p = positionen.get_by_ticker("NESN.SW")[0]
        assert not p.in_portfolio and not p.in_watchlist
        assert p.story == "These" and p.recommendation_source == "search_agent" and p.strategy == "Dividende"
        k = repo.get(p.id)
        assert (k.zustand, k.strategie, k.lauf_id, k.funde) == ("offen", "frei", 7, 1)

    def test_zweiter_fund_zaehlt_hoch_statt_zweitem_kandidaten(self, positionen, repo):
        kandidaten.aufnehmen(positionen, repo, [_vorschlag("NESN.SW")], "frei", None, 1)
        a = kandidaten.aufnehmen(positionen, repo, [_vorschlag("nesn.sw")], "strukturwandel", "Scan", 2)
        assert (a.neu, a.wieder) == (0, 1)
        assert len(positionen.get_by_ticker("NESN.SW")) == 1
        k = repo.alle()[0]
        assert (k.funde, k.strategie, k.lauf_id) == (2, "strukturwandel", 2)

    def test_doppelt_im_selben_lauf_ein_kandidat(self, positionen, repo):
        a = kandidaten.aufnehmen(positionen, repo, [_vorschlag("SAP.DE"), _vorschlag("SAP.DE")], "frei", None, 1)
        assert (a.neu, a.wieder) == (1, 1)
        assert len(repo.alle()) == 1

    def test_verworfen_bleibt_verworfen(self, positionen, repo):
        kandidaten.aufnehmen(positionen, repo, [_vorschlag("SAP.DE")], "frei", None, 1)
        pid = repo.alle()[0].position_id
        kandidaten.verwerfen(repo, pid)
        a = kandidaten.aufnehmen(positionen, repo, [_vorschlag("SAP.DE")], "frei", None, 2)
        assert (a.neu, a.wieder, a.verworfen) == (0, 0, 1)
        assert repo.get(pid).zustand == "verworfen" and repo.get(pid).funde == 2

    def test_depot_und_watchlist_werden_kein_kandidat(self, positionen, repo):
        _titel(positionen, "AAPL", depot=True)
        _titel(positionen, "MSFT", watchlist=True)
        a = kandidaten.aufnehmen(positionen, repo, [_vorschlag("AAPL"), _vorschlag("MSFT")], "frei", None, 1)
        assert (a.neu, a.bekannt) == (0, 2)
        assert repo.alle() == []

    def test_position_ohne_liste_und_ohne_zeile_ist_kein_kandidat(self, positionen, repo):
        """Eine verwaiste Position (auf keiner Liste, nie Kandidat) blockiert keinen Vorschlag."""
        _titel(positionen, "OLD")
        a = kandidaten.aufnehmen(positionen, repo, [_vorschlag("OLD")], "frei", None, 1)
        assert a.neu == 1

    def test_ohne_ticker_gilt_der_name(self, positionen, repo):
        kandidaten.aufnehmen(positionen, repo, [_vorschlag("", "Kupfer-Fonds")], "frei", None, 1)
        a = kandidaten.aufnehmen(positionen, repo, [_vorschlag("", "kupfer-fonds")], "frei", None, 2)
        assert (a.neu, a.wieder) == (0, 1)

    def test_unbekannte_anlageklasse_wird_aktie(self, positionen, repo):
        v = dict(_vorschlag("X"), asset_class="Quatsch")
        kandidaten.aufnehmen(positionen, repo, [v], "frei", None, 1)
        assert positionen.get_by_ticker("X")[0].asset_class == "Aktie"

    def test_strukturwandel_nimmt_die_volle_these(self, positionen, repo):
        v = dict(_vorschlag("ASML"), story="kurz", full_story="lang und ausfuehrlich")
        kandidaten.aufnehmen(positionen, repo, [v], "strukturwandel", "Scan", 1)
        assert positionen.get_by_ticker("ASML")[0].story == "lang und ausfuehrlich"


class TestBekannteTicker:
    def test_nie_das_depot(self, positionen, repo):
        """Die Strategien rechnen in der Cloud: Depot-Ticker verlassen das Haus nicht, auch
        nicht, wenn der Titel zugleich auf der Watchlist steht."""
        _titel(positionen, "AAPL", depot=True)
        _titel(positionen, "NVDA", depot=True, watchlist=True)
        _titel(positionen, "MSFT", watchlist=True)
        kandidaten.aufnehmen(positionen, repo, [_vorschlag("SAP.DE"), _vorschlag("ASML")], "frei", None, 1)
        kandidaten.verwerfen(repo, positionen.get_by_ticker("ASML")[0].id)
        assert kandidaten.bekannte_ticker(positionen, repo) == ["ASML", "MSFT", "SAP.DE"]

    def test_ausschluss_im_prompt(self):
        assert kandidaten.ausschluss([]) == ""
        text = kandidaten.ausschluss(["MSFT", "SAP.DE"])
        assert "MSFT, SAP.DE" in text and "do not propose" in text.lower()

    @pytest.mark.asyncio
    async def test_freie_suche_gibt_sie_ins_system(self):
        from agents.search_agent import SearchAgent
        from core.llm.claude import ClaudeResponse

        search_repo = MagicMock()
        search_repo.get_session.return_value = MagicMock(skill_prompt="Strategie")
        search_repo.get_messages.return_value = []
        llm = MagicMock()
        llm.chat_with_tools = AsyncMock(return_value=ClaudeResponse(content="ok", tool_calls=[], raw_blocks=[]))
        agent = SearchAgent(positions_repo=MagicMock(), search_repo=search_repo, llm=llm)
        await agent.chat(1, "Suche", bekannte_ticker=["MSFT"])
        assert "MSFT" in llm.chat_with_tools.call_args.kwargs["system"]


class TestEntscheiden:
    def test_auf_die_watchlist_nimmt_die_id_mit(self, positionen, repo):
        kandidaten.aufnehmen(positionen, repo, [_vorschlag("SAP.DE")], "frei", None, 1)
        pid = repo.alle()[0].position_id
        kandidaten.auf_die_watchlist(positionen, repo, pid)
        p = positionen.get(pid)
        assert p.in_watchlist and not p.in_portfolio and p.added_date == date.today()
        assert repo.get(pid).zustand == "uebernommen"
        assert kandidaten.listen(positionen, repo).offen == []

    def test_von_der_watchlist_genommen_und_wieder_gefunden_ist_wieder_offen(self, positionen, repo):
        kandidaten.aufnehmen(positionen, repo, [_vorschlag("SAP.DE")], "frei", None, 1)
        pid = repo.alle()[0].position_id
        kandidaten.auf_die_watchlist(positionen, repo, pid)
        p = positionen.get(pid)
        positionen.update(p.model_copy(update={"in_watchlist": False}))
        kandidaten.aufnehmen(positionen, repo, [_vorschlag("SAP.DE")], "frei", None, 2)
        assert repo.get(pid).zustand == "offen"

    def test_ignoriert_nach_60_tagen_und_wieder_aufnehmen(self, positionen, repo):
        frueher = datetime.now(timezone.utc) - timedelta(days=IGNORIERT_NACH_TAGEN)
        kandidaten.aufnehmen(positionen, repo, [_vorschlag("ALT")], "frei", None, 1, jetzt=frueher)
        kandidaten.aufnehmen(positionen, repo, [_vorschlag("NEU")], "frei", None, 2)
        teile = kandidaten.listen(positionen, repo)
        assert [p.ticker for p, _ in teile.offen] == ["NEU"]
        assert [p.ticker for p, _ in teile.ignoriert] == ["ALT"]
        kandidaten.wieder_aufnehmen(repo, teile.ignoriert[0][0].id)
        assert {p.ticker for p, _ in kandidaten.listen(positionen, repo).offen} == {"ALT", "NEU"}

    def test_genauer_pruefen_beruehrt(self, positionen, repo):
        frueher = datetime.now(timezone.utc) - timedelta(days=IGNORIERT_NACH_TAGEN + 5)
        kandidaten.aufnehmen(positionen, repo, [_vorschlag("ALT")], "frei", None, 1, jetzt=frueher)
        repo.beruehren(repo.alle()[0].position_id)
        assert len(kandidaten.listen(positionen, repo).offen) == 1

    def test_verwerfen_merkt_datum(self, positionen, repo):
        kandidaten.aufnehmen(positionen, repo, [_vorschlag("SAP.DE")], "frei", None, 1)
        pid = repo.alle()[0].position_id
        kandidaten.verwerfen(repo, pid)
        teile = kandidaten.listen(positionen, repo)
        assert teile.offen == [] and teile.verworfen[0][1].entschieden is not None
        assert positionen.get(pid) is not None, "ein Nein loescht nie"

    def test_unbekannter_zustand(self, repo):
        with pytest.raises(ValueError):
            repo.setzen(1, "vielleicht")


class TestPruefung:
    def test_kandidaten_pruefen_wie_die_watchlist(self):
        assert MOEGLICH["kandidaten"] == MOEGLICH["watchlist"]

    def test_modell_der_watchlist(self, conn):
        cfg = AppConfigRepository(conn)
        modell_setzen(cfg, "watchlist", "claude-sonnet-x")
        assert modell(cfg, "kandidaten") == "claude-sonnet-x"


class TestEingeplanterScan:
    def test_vorschlaege_werden_kandidaten_ohne_depot_ticker(self, tmp_path, monkeypatch):
        """Der Strukturwandel-Scan aus dem Scheduler legt Kandidaten an wie der von Hand; die
        Strategie bekommt die bekannten Ticker, aber keinen aus dem Depot. Alles in tmp_path."""
        import asyncio
        from types import SimpleNamespace

        from agents.structural_change_agent import StructuralChangeAgent
        from core.scheduler import AgentSchedulerService
        from core.storage.base import build_encryption_service, get_connection

        dienst = AgentSchedulerService(db_path=str(tmp_path / "t.db"), encryption_key="k" * 32,
                                       anthropic_api_key="x", default_claude_model="claude-sonnet-5-5")
        conn = get_connection(dienst._db_path)
        init_db(conn)
        migrate_db(conn)
        positionen = PositionsRepository(conn, build_encryption_service(dienst._enc_key, dienst._salt_path))
        _titel(positionen, "AAPL", depot=True)
        _titel(positionen, "MSFT", watchlist=True)

        gesehen = {}

        async def scan(self, **kw):
            gesehen.update(kw)
            return SimpleNamespace(id=55), "Bericht", [_vorschlag("ASML"), _vorschlag("AAPL")]

        monkeypatch.setattr(StructuralChangeAgent, "start_scan", scan)
        monkeypatch.setattr(dienst, "_resolve_model", lambda *a: "claude-sonnet-5-5")
        monkeypatch.setattr(dienst, "_make_scheduled_llm", lambda *a: MagicMock())
        monkeypatch.setattr(dienst, "_can_use_batch_api", lambda m: False)
        job = SimpleNamespace(skill_name="Scan", skill_prompt="", model="")
        asyncio.run(dienst._run_structural_scan_job(job, conn))

        assert gesehen["bekannte_ticker"] == ["MSFT"]
        k = KandidatenRepository(conn).alle()
        assert len(k) == 1 and (k[0].strategie, k[0].lauf_id, k[0].skill) == ("strukturwandel", 55, "Scan")
        conn.close()
