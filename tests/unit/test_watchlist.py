import pytest
from datetime import date
from core.encryption import EncryptionService
from core.storage.base import get_connection, init_db
from core.storage.models import AssetType, WatchlistEntry, WatchlistSource
from core.storage.watchlist import WatchlistRepository


@pytest.fixture
def repo():
    conn = get_connection(":memory:")
    init_db(conn)
    enc = EncryptionService("test_password", b"0123456789abcdef")
    return WatchlistRepository(conn, enc)


@pytest.fixture
def user_entry():
    return WatchlistEntry(
        symbol="MSFT",
        name="Microsoft Corp.",
        notes="Watching for dip",
        target_price=350.0,
        added_date=date(2024, 3, 1),
        source=WatchlistSource.USER,
        asset_type=AssetType.STOCK,
    )


@pytest.fixture
def agent_entry():
    return WatchlistEntry(
        symbol="NVDA",
        name="NVIDIA Corp.",
        notes="Suggested by market agent",
        target_price=None,
        added_date=date(2024, 3, 2),
        source=WatchlistSource.AGENT,
        asset_type=AssetType.STOCK,
    )


def test_add_and_retrieve(repo, user_entry):
    added = repo.add(user_entry)
    assert added.id is not None

    results = repo.get_all()
    assert len(results) == 1
    assert results[0].symbol == "MSFT"
    assert results[0].target_price == 350.0
    assert results[0].notes == "Watching for dip"


def test_get_by_source(repo, user_entry, agent_entry):
    repo.add(user_entry)
    repo.add(agent_entry)

    user_items = repo.get_by_source(WatchlistSource.USER)
    agent_items = repo.get_by_source(WatchlistSource.AGENT)

    assert len(user_items) == 1
    assert user_items[0].symbol == "MSFT"
    assert len(agent_items) == 1
    assert agent_items[0].symbol == "NVDA"


def test_get_by_symbol(repo, user_entry):
    repo.add(user_entry)
    results = repo.get_by_symbol("msft")
    assert len(results) == 1


def test_optional_target_price_none(repo, agent_entry):
    repo.add(agent_entry)
    result = repo.get_all()[0]
    assert result.target_price is None


def test_delete(repo, user_entry):
    added = repo.add(user_entry)
    assert repo.delete(added.id) is True
    assert repo.get_all() == []


def test_delete_nonexistent_returns_false(repo):
    assert repo.delete(9999) is False


def test_data_is_encrypted_at_rest(repo, user_entry):
    repo.add(user_entry)
    raw = repo._conn.execute(
        "SELECT notes, target_price FROM watchlist"
    ).fetchone()
    assert raw["notes"] != "Watching for dip"
    assert raw["target_price"] != "350.0"


def test_invalid_target_price_raises():
    with pytest.raises(ValueError):
        WatchlistEntry(
            symbol="X",
            name="Test",
            target_price=-10.0,
            added_date=date.today(),
            source=WatchlistSource.USER,
            asset_type=AssetType.STOCK,
        )
