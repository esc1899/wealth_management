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
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # concurrent reads while writing
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they do not exist."""
    statements = [
        """CREATE TABLE IF NOT EXISTS portfolio (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT NOT NULL,
            name            TEXT NOT NULL,
            quantity        TEXT NOT NULL,
            purchase_price  TEXT,
            purchase_date   TEXT NOT NULL,
            asset_type      TEXT NOT NULL,
            notes           TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS watchlist (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol       TEXT NOT NULL,
            name         TEXT NOT NULL,
            notes        TEXT,
            target_price TEXT,
            added_date   TEXT NOT NULL,
            source       TEXT NOT NULL,
            asset_type   TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS positions (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_class           TEXT NOT NULL,
            investment_type       TEXT NOT NULL,
            name                  TEXT NOT NULL,
            isin                  TEXT,
            wkn                   TEXT,
            ticker                TEXT,
            quantity              TEXT,
            unit                  TEXT NOT NULL,
            purchase_price        TEXT,
            purchase_date         TEXT,
            notes                 TEXT,
            extra_data            TEXT,
            recommendation_source TEXT,
            strategy              TEXT,
            added_date            TEXT NOT NULL,
            in_portfolio          INTEGER NOT NULL DEFAULT 0
        )""",
        "CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker)",
        "CREATE INDEX IF NOT EXISTS idx_positions_in_portfolio ON positions(in_portfolio)",
        """CREATE TABLE IF NOT EXISTS current_prices (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol            TEXT NOT NULL UNIQUE,
            price_eur         REAL NOT NULL,
            currency_original TEXT NOT NULL,
            price_original    REAL NOT NULL,
            exchange_rate     REAL NOT NULL,
            fetched_at        TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS historical_prices (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol    TEXT NOT NULL,
            date      TEXT NOT NULL,
            close_eur REAL NOT NULL,
            volume    INTEGER,
            UNIQUE(symbol, date)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_hist_prices_symbol_date ON historical_prices(symbol, date)",
        """CREATE TABLE IF NOT EXISTS research_sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT NOT NULL,
            company_name    TEXT,
            strategy_name   TEXT NOT NULL,
            strategy_prompt TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            summary         TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS research_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES research_sessions(id),
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_research_messages_session ON research_messages(session_id)",
    ]
    for stmt in statements:
        conn.execute(stmt)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS skills (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            area        TEXT NOT NULL,
            description TEXT,
            prompt      TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(name, area)
        )"""
    )
    conn.commit()


def build_encryption_service(password: str, salt_path: str) -> EncryptionService:
    salt = load_or_create_salt(salt_path)
    return EncryptionService(password, salt)
