"""
AppConfigRepository — key-value store for runtime application configuration.
Values are stored as plain text (no encryption); keys are application settings,
not personal financial data.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional


class AppConfigRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # String operations
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[str]:
        """Return the value for *key*, or None if not set."""
        row = self._conn.execute(
            "SELECT value FROM app_config WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set(self, key: str, value: str) -> None:
        """Upsert a string value for *key*."""
        self._conn.execute(
            "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # JSON helpers
    # ------------------------------------------------------------------

    def get_json(self, key: str, default: Any = None) -> Any:
        """Return the JSON-decoded value for *key*, or *default* if not set."""
        raw = self.get(key)
        if raw is None:
            return default
        return json.loads(raw)

    def set_json(self, key: str, value: Any) -> None:
        """Serialize *value* to JSON and store it under *key*."""
        self.set(key, json.dumps(value, ensure_ascii=False))

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, key: str) -> None:
        """Remove a key from the config store."""
        self._conn.execute("DELETE FROM app_config WHERE key = ?", (key,))
        self._conn.commit()
