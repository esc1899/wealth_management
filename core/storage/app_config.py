"""
AppConfigRepository — key-value store for runtime application configuration.
Values are stored as plain text (no encryption); keys are application settings,
not personal financial data.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional
from core.constants import CLAUDE_HAIKU, CLAUDE_SONNET, CLAUDE_OPUS


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

    # Model registry: prices (USD per million tokens) + provider + optional Ollama
    # runtime params (think / num_ctx for local models). ``provider`` ∈
    # {claude, openrouter, deepseek, ollama}.
    # NOTE: ``deepseek/…`` (slash form) is served *via OpenRouter* — the router only
    # matches the ``deepseek-`` prefix (direct API), so these are tagged openrouter.
    # Claude-Preise: seit 2026-09-27 aus dem Modellkatalog des Hauses (_overlay_catalog),
    # die Werte hier gelten nur ohne Katalog. Preise zuletzt geprüft 2026-08-30:
    # Anthropic gegen die Listenpreis-Tabelle
    # (platform.claude.com/docs/en/about-claude/pricing), OpenRouter gegen
    # https://openrouter.ai/api/v1/models (Feld ``pricing``, $/Token → ×1e6).
    _DEFAULT_MODEL_PRICES: dict = {
        CLAUDE_HAIKU:   {"input": 1.00,  "output": 5.00,  "provider": "claude"},
        CLAUDE_SONNET:  {"input": 2.00,  "output": 10.00, "provider": "claude"},
        CLAUDE_OPUS:    {"input": 5.00,  "output": 25.00, "provider": "claude"},
        "claude-opus-5-5": {"input": 4.00, "output": 20.00, "provider": "claude"},
        # DeepSeek + Mistral via OpenRouter — DeepSeek hat seit Juni deutlich gesenkt
        "deepseek/deepseek-v4-flash":   {"input": 0.0804, "output": 0.1607, "provider": "openrouter"},
        "deepseek/deepseek-v4-pro":     {"input": 0.4475, "output": 0.8951, "provider": "openrouter"},
        "deepseek/deepseek-chat":       {"input": 0.2574, "output": 1.0287, "provider": "openrouter"},
        "deepseek/deepseek-r1":         {"input": 0.70,   "output": 2.50,   "provider": "openrouter"},
        "mistralai/mistral-large-2512": {"input": 0.50,   "output": 1.50,   "provider": "openrouter"},
        # Mistral Medium 3.5 (04/2026) — aktuellstes Mistral-Modell. Schreibt Prosa UND
        # ruft das Submit-Tool; mistral-large-2512 kollabiert die Antwort in den Tool-Call
        # (kein Prosa-Body), wie DeepSeek es beim FA tat — für Agents mit Prosa+Verdict
        # also Medium 3.5 nehmen, nicht Large. Preise identisch mit Mistral direkt.
        "mistralai/mistral-medium-3-5": {"input": 1.50,   "output": 7.50,   "provider": "openrouter"},
        # Local models are free (Ollama)
        "qwen3.5:9b":   {"input": 0.0,   "output": 0.0, "provider": "ollama"},
        "llama3.2":     {"input": 0.0,   "output": 0.0, "provider": "ollama"},
        "mistral-nemo:latest": {"input": 0.0, "output": 0.0, "provider": "ollama"},
        "mistral-nemo:12b":    {"input": 0.0, "output": 0.0, "provider": "ollama"},
    }

    # Providers that serve the agent "Cloud"/public model dropdown.
    PUBLIC_PROVIDERS = ("claude", "openrouter", "deepseek")
    # Abgelöste Modelle: bleiben mit ihrem damaligen Preis in der Registry, damit die
    # Kosten alter llm_usage-Zeilen weiter berechenbar sind (compute_cost schlägt nur
    # dort nach). Kein Public-Provider → sie tauchen nicht mehr in der Modellauswahl
    # auf. Ein hier fehlendes Alt-Modell erscheint in der Statistik lautlos mit 0 $.
    LEGACY_PROVIDER = "claude_legacy"
    # Local provider (privacy 🔒). Legacy value "local" is normalised to this.
    OLLAMA_PROVIDER = "ollama"
    _DELETED_KEY = "model_prices_deleted"

    @staticmethod
    def _infer_provider(model_id: str) -> str:
        """Best-effort provider for a registry entry without an explicit ``provider``.

        Mirrors the runtime routing rule (core.llm.router): only the ``deepseek-``
        prefix is the direct DeepSeek API; ``deepseek/…`` (slash) goes via OpenRouter.
        Used for legacy entries or user-added rows that omit the field.
        """
        if model_id.startswith("claude-"):
            return "claude"
        if model_id.startswith("deepseek-"):
            return "deepseek"
        if ":" in model_id:  # Ollama tag form, e.g. "qwen3.5:9b"
            return "ollama"
        return "openrouter"

    def get_deleted_models(self) -> list:
        """Model ids the user explicitly removed (so seeded defaults stay removed)."""
        return self.get_json(self._DELETED_KEY, []) or []

    def set_deleted_models(self, ids: list) -> None:
        self.set_json(self._DELETED_KEY, list(dict.fromkeys(ids)))

    def get_model_prices(self) -> dict:
        """Return prices dict, seeding defaults on first call.

        Entries on the deleted list are removed even if they are seeded defaults,
        so a model the user deleted does not reappear on the next merge.
        """
        stored = self.get_json("model_prices")
        if stored is None:
            self.set_json("model_prices", self._DEFAULT_MODEL_PRICES)
            merged = dict(self._DEFAULT_MODEL_PRICES)
        else:
            # Merge: stored overrides defaults, new models added from defaults
            merged = dict(self._DEFAULT_MODEL_PRICES)
            merged.update(stored)
        self._overlay_catalog(merged)
        for deleted_id in self.get_deleted_models():
            merged.pop(deleted_id, None)
        return merged

    @staticmethod
    def _overlay_catalog(merged: dict) -> None:
        """Claude prices from the household model catalog (2026-09-27).

        The catalog (``~/.ops-core/katalog.toml``, refreshed on the Home-Ops
        page) is the one place a Claude price is kept for every app in the
        house; it wins over defaults *and* over a price edited here. Two rules
        keep the registry tidy:

        * a model the registry already has gets the catalog's price, matched
          on the dateless id as well (``claude-haiku-4-5-20251001``), and keeps
          its provider;
        * a model the catalog calls current is added as ``claude`` — that is
          what makes a new model selectable without editing anything here.

        Retired models are *not* added: they would clutter the picker and the
        price table. Without a catalog nothing changes.
        """
        from core import house_models
        from core.llm.router import _base_model_id

        catalog = house_models.load_catalog(house_models.CLAUDE)
        if not catalog:
            return
        by_base = {_base_model_id(m): m for m in merged}
        for model_id, price in catalog["prices"].items():
            key = model_id if model_id in merged else by_base.get(_base_model_id(model_id))
            if key is not None:
                merged[key] = {**merged[key], **price}
            elif model_id in catalog["current"]:
                merged[model_id] = {**price, "provider": "claude"}

    def set_model_prices(self, prices: dict) -> None:
        self.set_json("model_prices", prices)

    def get_model_registry(self) -> dict:
        """Like get_model_prices(), but every entry has a guaranteed ``provider``.

        Legacy entries missing the field get one inferred from the model id, so
        the registry is always complete for the settings UI and cost grouping.
        """
        registry = self.get_model_prices()
        for model_id, entry in registry.items():
            if not entry.get("provider"):
                entry["provider"] = self._infer_provider(model_id)
            elif entry["provider"] == "local":  # normalise legacy value
                entry["provider"] = self.OLLAMA_PROVIDER
        return registry

    def get_registry_with_configured(self, configured: list, provider: str = "openrouter") -> dict:
        """Registry plus any configured (e.g. env OPENAI_MODELS) models not yet present.

        Honours the deleted list: a model the user removed in the UI does NOT reappear
        just because it is still listed in config/.env (FEAT-57 bug — a deleted model in
        OPENAI_MODELS was re-added on every settings reload).
        """
        registry = self.get_model_registry()
        deleted = set(self.get_deleted_models())
        for model_id in configured:
            if model_id and model_id not in registry and model_id not in deleted:
                registry[model_id] = {"input": 0.0, "output": 0.0, "provider": provider}
        return registry

    def provider_for(self, model: str) -> str:
        """Provider for a model id: registry entry if present, else inferred."""
        entry = self.get_model_registry().get(model)
        if entry and entry.get("provider"):
            return entry["provider"]
        return self._infer_provider(model)

    def get_ollama_params(self, model: str) -> dict:
        """Per-model Ollama runtime params from the registry.

        Returns ``think`` (bool) and ``num_ctx`` (int or None — None means the
        caller should fall back to the global ``config.OLLAMA_NUM_CTX`` default).
        """
        entry = self.get_model_registry().get(model, {})
        raw_ctx = entry.get("num_ctx")
        return {
            "think": bool(entry.get("think", False)),
            "num_ctx": int(raw_ctx) if raw_ctx else None,
        }

