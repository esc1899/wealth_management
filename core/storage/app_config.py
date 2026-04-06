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

    # ------------------------------------------------------------------
    # Model prices
    # ------------------------------------------------------------------

    # Anthropic list prices (USD per million tokens), April 2025
    _DEFAULT_MODEL_PRICES: dict = {
        "claude-haiku-4-5-20251001":  {"input": 0.80,  "output": 4.00},
        "claude-sonnet-4-6":          {"input": 3.00,  "output": 15.00},
        "claude-opus-4-6":            {"input": 15.00, "output": 75.00},
        # Local models are free
        "qwen3:8b":                   {"input": 0.0,   "output": 0.0},
        "llama3.2":                   {"input": 0.0,   "output": 0.0},
    }

    def get_model_prices(self) -> dict:
        """Return prices dict, seeding defaults on first call."""
        stored = self.get_json("model_prices")
        if stored is None:
            self.set_json("model_prices", self._DEFAULT_MODEL_PRICES)
            return dict(self._DEFAULT_MODEL_PRICES)
        # Merge: stored overrides defaults, new models added from defaults
        merged = dict(self._DEFAULT_MODEL_PRICES)
        merged.update(stored)
        return merged

    def set_model_prices(self, prices: dict) -> None:
        self.set_json("model_prices", prices)

    # ------------------------------------------------------------------
    # Cost alert limits
    # ------------------------------------------------------------------

    def get_cost_alert(self) -> dict:
        """Return {'daily': float, 'monthly': float}. 0 = disabled."""
        return self.get_json("cost_alert", {"daily": 0.0, "monthly": 0.0})

    def set_cost_alert(self, daily: float, monthly: float) -> None:
        self.set_json("cost_alert", {"daily": daily, "monthly": monthly})
