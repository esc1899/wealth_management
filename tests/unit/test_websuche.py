"""Gescheiterte Websuche: gezaehlt, geloggt, und ein Check ohne einen einzigen Treffer bekommt
kein Urteil (11.10.2026, Schneider Electric: "Gemischt (vorlaeufig)" stand auf der Kachel)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.constants import CLAUDE_SONNET
from core.llm.claude import ClaudeProvider, WebsucheGescheitert, websuche_bilanz


def _treffer():
    return SimpleNamespace(type="web_search_tool_result", content=[SimpleNamespace(url="https://x")])


def _fehler(code="unavailable"):
    return SimpleNamespace(type="web_search_tool_result",
                           content=SimpleNamespace(type="web_search_tool_result_error", error_code=code))


def _text(t):
    return SimpleNamespace(type="text", text=t)


def _antwort(blocks):
    r = MagicMock()
    r.content = blocks
    r.stop_reason = "end_turn"
    r.usage = MagicMock(input_tokens=1, output_tokens=1, cache_read_input_tokens=0,
                        cache_creation_input_tokens=0, server_tool_use=None)
    return r


def test_bilanz():
    assert websuche_bilanz([_text("a"), _treffer(), _fehler("too_many_requests"), _fehler()]) == \
        (1, ["too_many_requests", "unavailable"])
    assert websuche_bilanz([_text("a")]) == (0, [])
    dict_fehler = SimpleNamespace(type="web_search_tool_result", content={"error_code": "max_uses_exceeded"})
    assert websuche_bilanz([dict_fehler]) == (0, ["max_uses_exceeded"])


async def _frage(blocks, pflicht):
    p = ClaudeProvider(api_key="k", model=CLAUDE_SONNET)
    gebucht = []
    p.on_usage = lambda *a: gebucht.append(a)

    async def create(**kwargs):
        return _antwort(blocks)
    p._client.messages.create = create
    try:
        return await p.chat_with_tools(
            messages=[{"role": "user", "content": "Pruefe"}],
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 3}],
            websuche_pflicht=pflicht), gebucht
    except WebsucheGescheitert as exc:
        return exc, gebucht


@pytest.mark.asyncio
async def test_alle_suchen_gescheitert_kein_urteil_aber_gebucht():
    ergebnis, gebucht = await _frage([_fehler("unavailable"), _text("Urteil: 🟡 vorläufig")], pflicht=True)
    assert isinstance(ergebnis, WebsucheGescheitert)
    assert "unavailable" in str(ergebnis)
    assert len(gebucht) == 1          # bezahlt ist bezahlt


@pytest.mark.asyncio
async def test_ein_treffer_genuegt():
    ergebnis, _ = await _frage([_fehler(), _treffer(), _text("Urteil: 🟢")], pflicht=True)
    assert not isinstance(ergebnis, Exception)


@pytest.mark.asyncio
async def test_ohne_pflicht_nur_geloggt(caplog):
    ergebnis, _ = await _frage([_fehler(), _text("Antwort")], pflicht=False)
    assert ergebnis.content == "Antwort"
    assert "Websuche" in caplog.text and "unavailable" in caplog.text


@pytest.mark.asyncio
async def test_ohne_suche_ist_kein_fehler():
    ergebnis, _ = await _frage([_text("Urteil: 🟢")], pflicht=True)
    assert not isinstance(ergebnis, Exception)


def test_storychecker_speichert_ohne_beleg_kein_urteil():
    """Der Storychecker reicht die Pflicht weiter; scheitert die Suche, steht kein Urteil da."""
    import asyncio
    import sqlite3
    from datetime import date

    from agents.storychecker_agent import StorycheckerAgent
    from core.storage.analyses import PositionAnalysesRepository
    from core.storage.base import init_db, migrate_db
    from core.storage.models import Position
    from core.storage.storychecker import StorycheckerRepository

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    migrate_db(conn)
    gesehen = {}

    class Llm:
        skill_context = position_count = None

        async def chat_with_tools(self, **kw):
            gesehen.update(kw)
            raise WebsucheGescheitert("Websuche fehlgeschlagen (unavailable) — kein Urteil gespeichert")

    pos = Position(id=7, name="Schneider Electric SE", ticker="SND.DE", asset_class="Aktie",
                   investment_type="Wertpapiere", unit="Stück", added_date=date(2026, 1, 1),
                   in_portfolio=True, story="Elektrifizierung")
    positions = MagicMock()
    positions.get.return_value = pos
    agent = StorycheckerAgent(positions_repo=positions, storychecker_repo=StorycheckerRepository(conn),
                              analyses_repo=PositionAnalysesRepository(conn), llm=Llm())
    [(name, fehler)] = asyncio.run(agent.batch_check_all([pos]))
    assert gesehen["websuche_pflicht"] is True
    assert "unavailable" in fehler
    assert PositionAnalysesRepository(conn).get_for_position(7) == []
