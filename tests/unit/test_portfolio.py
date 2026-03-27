import pytest
from datetime import date
from core.encryption import EncryptionService
from core.storage.base import get_connection, init_db
from core.storage.models import AssetType, PortfolioEntry
from core.storage.portfolio import PortfolioRepository


@pytest.fixture
def repo():
    conn = get_connection(":memory:")
    init_db(conn)
    enc = EncryptionService("test_password", b"0123456789abcdef")
    return PortfolioRepository(conn, enc)


@pytest.fixture
def sample_entry():
    return PortfolioEntry(
        symbol="AAPL",
        name="Apple Inc.",
        quantity=10.0,
        purchase_price=150.0,
        purchase_date=date(2024, 1, 15),
        asset_type=AssetType.STOCK,
        notes="Long term hold",
    )


def test_add_and_retrieve(repo, sample_entry):
    added = repo.add(sample_entry)
    assert added.id is not None

    results = repo.get_all()
    assert len(results) == 1
    assert results[0].symbol == "AAPL"
    assert results[0].quantity == 10.0
    assert results[0].purchase_price == 150.0
    assert results[0].notes == "Long term hold"


def test_symbol_normalized_to_uppercase(repo):
    entry = PortfolioEntry(
        symbol="aapl",
        name="Apple Inc.",
        quantity=5.0,
        purchase_price=100.0,
        purchase_date=date(2024, 1, 1),
        asset_type=AssetType.STOCK,
    )
    added = repo.add(entry)
    assert added.symbol == "AAPL"


def test_get_by_symbol(repo, sample_entry):
    repo.add(sample_entry)
    results = repo.get_by_symbol("AAPL")
    assert len(results) == 1
    assert results[0].symbol == "AAPL"


def test_get_by_symbol_case_insensitive(repo, sample_entry):
    repo.add(sample_entry)
    assert len(repo.get_by_symbol("aapl")) == 1


def test_delete(repo, sample_entry):
    added = repo.add(sample_entry)
    assert repo.delete(added.id) is True
    assert repo.get_all() == []


def test_delete_nonexistent_returns_false(repo):
    assert repo.delete(9999) is False


def test_update(repo, sample_entry):
    added = repo.add(sample_entry)
    updated = added.model_copy(update={"quantity": 20.0, "notes": "Updated"})
    assert repo.update(updated) is True
    result = repo.get_all()[0]
    assert result.quantity == 20.0
    assert result.notes == "Updated"


def test_update_without_id_raises(repo, sample_entry):
    with pytest.raises(ValueError):
        repo.update(sample_entry)


def test_data_is_encrypted_at_rest(repo, sample_entry):
    repo.add(sample_entry)
    # Read raw SQLite row without decryption
    raw = repo._conn.execute(
        "SELECT quantity, purchase_price FROM portfolio"
    ).fetchone()
    # Raw values must not equal the plaintext numbers
    assert raw["quantity"] != "10.0"
    assert raw["purchase_price"] != "150.0"


def test_invalid_quantity_raises():
    with pytest.raises(ValueError):
        PortfolioEntry(
            symbol="X",
            name="Test",
            quantity=-1.0,
            purchase_price=10.0,
            purchase_date=date.today(),
            asset_type=AssetType.STOCK,
        )
