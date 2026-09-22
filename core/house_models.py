"""The household default model per provider — read, never written here.

Four side projects on this machine talk to the same three providers, and
each used to carry its own model name in its own config. They drifted
apart without anyone noticing, which costs real time on the shared Ollama
instance: only one model fits in memory, so two projects asking for
different ones evict each other (measured by the Home-Ops agent, M15).

Since 2026-09-22 the household default lives in one file, written by the
Home-Ops page and defined by ops-core (step 14):

    ~/.ops-core/modelle.toml

    [claude]
    modell = "claude-sonnet-5"
    budget_usd = 20          # per calendar month, optional

    [ollama]
    modell = "qwen3.5:9b"

A model setting of ``home`` means: take the entry for that provider, **at
call time** — so a change on the page takes effect on the next call, with
no restart. Anything else is used as it stands.

The reader is a deliberate copy of ``ops_core.modelle`` rather than an
import, for the same reason the keychain reader is a copy: no call in this
app may depend on ops-core being installed. Without the file there is no
household default, and a setting of ``home`` falls back to what the app
would have used anyway — a missing file must never take the app offline.
The budget is read too, but only the Home-Ops page uses it; nothing here
stops a call.
"""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: The sentinel a model setting carries to follow the household.
HOME = "home"

CLAUDE = "claude"
OLLAMA = "ollama"
OPENROUTER = "openrouter"
PROVIDERS = (CLAUDE, OLLAMA, OPENROUTER)


def models_file() -> Path:
    base = Path(os.environ.get("OPS_CORE_HOME") or Path.home() / ".ops-core")
    return base / "modelle.toml"


def load(path: Optional[Path] = None) -> dict:
    """``{provider: {"modell": str, "budget_usd": float | None}}``.

    Never raises: a missing, unreadable or malformed file means "no
    household default", which every caller can handle.
    """
    path = path or models_file()
    try:
        if not path.is_file():
            return {}
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.warning("household model file unreadable (%s): %s", path, exc)
        return {}
    out = {}
    for name, entry in raw.items():
        if name not in PROVIDERS or not isinstance(entry, dict):
            continue
        model = entry.get("modell")
        if not isinstance(model, str) or not model.strip():
            continue
        budget = entry.get("budget_usd")
        out[name] = {
            "modell": model.strip(),
            "budget_usd": float(budget) if isinstance(budget, (int, float))
            and not isinstance(budget, bool) else None,
        }
    return out


def house_model(provider: str, path: Optional[Path] = None) -> Optional[str]:
    """The household default for one provider, or None if there is none."""
    return (load(path).get(provider) or {}).get("modell")


def resolve(model: str, provider: str, fallback: str = "",
            path: Optional[Path] = None) -> str:
    """Turn a ``home`` setting into the household default for *provider*.

    Called wherever a provider is built, not once at startup: that is what
    makes a change on the Home-Ops page take effect without a restart.
    Without an entry the caller's ``fallback`` stands — the app keeps
    running on what it used before, it does not stop.
    """
    if (model or "").strip() != HOME:
        return model
    return house_model(provider, path) or fallback


def is_home(model: str) -> bool:
    return (model or "").strip() == HOME
