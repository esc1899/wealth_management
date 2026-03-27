"""
SQLite database connection and schema initialization.
"""

import sqlite3
import os
from core.encryption import EncryptionService, load_or_create_salt


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a SQLite connection, creating the database directory if needed."""
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they do not exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            name            TEXT NOT NULL,
            quantity        TEXT NOT NULL,
            purchase_price  TEXT NOT NULL,
            purchase_date   TEXT NOT NULL,
            asset_type      TEXT NOT NULL,
            notes           TEXT
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol       TEXT NOT NULL,
            name         TEXT NOT NULL,
            notes        TEXT,
            target_price TEXT,
            added_date   TEXT NOT NULL,
            source       TEXT NOT NULL,
            asset_type   TEXT NOT NULL
        );
    """)
    conn.commit()


def build_encryption_service(password: str, salt_path: str) -> EncryptionService:
    salt = load_or_create_salt(salt_path)
    return EncryptionService(password, salt)
