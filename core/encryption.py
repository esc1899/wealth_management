"""
Encryption utilities using Fernet symmetric encryption.
All sensitive data is encrypted before storage and decrypted on retrieval.
"""

import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 32-byte Fernet key from a password and salt using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def load_or_create_salt(salt_path: str) -> bytes:
    """Load existing salt or create and persist a new one."""
    if os.path.exists(salt_path):
        with open(salt_path, "rb") as f:
            return f.read()
    salt = os.urandom(16)
    os.makedirs(os.path.dirname(salt_path), exist_ok=True)
    with open(salt_path, "wb") as f:
        f.write(salt)
    return salt


class EncryptionService:
    """Encrypts and decrypts string values using a password-derived key."""

    def __init__(self, password: str, salt: bytes):
        key = derive_key(password, salt)
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
