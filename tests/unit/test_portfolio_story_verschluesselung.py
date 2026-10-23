"""Der Liquiditaetsbedarf der Portfolio-Story wird verschluesselt (Erik, 23.10.2026).

Er ist privat ("2028: Immobilienkauf ~150k") und lag bis dahin im Klartext, nur die Erzaehlung
war verschluesselt -- aufgefallen in der Ontologie (`ontologie/wealth.ttl`). Alte Zeilen bleiben
lesbar und werden beim Start der App einmal umgeschluesselt.
"""

import sqlite3
from datetime import datetime, timezone

import pytest

from core.encryption import EncryptionService, PassthroughEncryptionService
from core.storage.base import init_db, migrate_db
from core.storage.models import PortfolioStory
from core.storage.portfolio_story import PortfolioStoryRepository

JETZT = datetime(2026, 10, 23, tzinfo=timezone.utc)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_db(c)
    migrate_db(c)
    yield c
    c.close()


@pytest.fixture
def enc():
    return EncryptionService("nur-im-test", b"0123456789abcdef")


def _story(bedarf="2028: Wohnung ~150k"):
    return PortfolioStory(story="Ruhestand mit 60", target_year=2040, liquidity_need=bedarf,
                          priority="Sicherheit", created_at=JETZT, updated_at=JETZT)


def _roh(conn):
    return conn.execute("SELECT liquidity_need FROM portfolio_story").fetchone()[0]


def test_neu_gespeichert_ist_er_verschluesselt(conn, enc):
    repo = PortfolioStoryRepository(conn, enc)
    gespeichert = repo.save(_story())
    assert _roh(conn).startswith("gAAAAA")
    assert repo.get_current().liquidity_need == "2028: Wohnung ~150k"
    gespeichert.liquidity_need = "2030: Auto"
    repo.save(gespeichert)
    assert _roh(conn).startswith("gAAAAA")
    assert repo.get_current().liquidity_need == "2030: Auto"


def test_ohne_bedarf_bleibt_die_spalte_leer(conn, enc):
    PortfolioStoryRepository(conn, enc).save(_story(bedarf=None))
    assert _roh(conn) is None


def test_alte_klartext_zeile_bleibt_lesbar_und_wird_umgeschluesselt(conn, enc):
    conn.execute(
        "INSERT INTO portfolio_story (story, target_year, liquidity_need, priority, created_at,"
        " updated_at) VALUES (?, 2040, '2028: alt', 'Gemischt', ?, ?)",
        (enc.encrypt("alt"), JETZT.isoformat(), JETZT.isoformat()))
    repo = PortfolioStoryRepository(conn, enc)
    assert repo.get_current().liquidity_need == "2028: alt"

    assert repo.verschluessele_altbestand() == 1
    assert _roh(conn).startswith("gAAAAA")
    assert repo.get_current().liquidity_need == "2028: alt"
    assert repo.verschluessele_altbestand() == 0  # idempotent


def test_im_demo_modus_schreibt_der_umbau_nichts(conn):
    repo = PortfolioStoryRepository(conn, PassthroughEncryptionService())
    repo.save(_story())
    assert repo.verschluessele_altbestand() == 0
    assert _roh(conn) == "2028: Wohnung ~150k"
