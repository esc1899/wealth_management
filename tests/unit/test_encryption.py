import pytest
from core.encryption import EncryptionService, derive_key


@pytest.fixture
def enc():
    return EncryptionService(password="test_password", salt=b"0123456789abcdef")


def test_encrypt_decrypt_roundtrip(enc):
    plaintext = "sensitive data 123"
    assert enc.decrypt(enc.encrypt(plaintext)) == plaintext


def test_different_plaintexts_produce_different_ciphertexts(enc):
    a = enc.encrypt("value_a")
    b = enc.encrypt("value_b")
    assert a != b


def test_same_plaintext_produces_different_ciphertexts(enc):
    # Fernet uses a random IV, so encrypting the same value twice differs
    a = enc.encrypt("same")
    b = enc.encrypt("same")
    assert a != b


def test_wrong_key_cannot_decrypt():
    enc1 = EncryptionService("password_one", b"0123456789abcdef")
    enc2 = EncryptionService("password_two", b"0123456789abcdef")
    ciphertext = enc1.encrypt("secret")
    with pytest.raises(Exception):
        enc2.decrypt(ciphertext)


def test_derive_key_is_deterministic():
    salt = b"fixed_salt_bytes"
    key1 = derive_key("my_password", salt)
    key2 = derive_key("my_password", salt)
    assert key1 == key2


def test_derive_key_differs_with_different_salt():
    key1 = derive_key("password", b"salt_aaaaaaaaaa1")
    key2 = derive_key("password", b"salt_bbbbbbbbbb2")
    assert key1 != key2
