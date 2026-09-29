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


# ---------------------------------------------------------------------------
# The model catalog (ops-core step 18, 2026-09-27)
# ---------------------------------------------------------------------------
#
# ``~/.ops-core/katalog.toml`` lists, per provider, the current choice (the
# newest model of each family) and the list prices of *all* models, retired
# ones included. It is refreshed by a button on the Home-Ops page, which
# asks Anthropic's Models API and reads the public pricing page. Before it,
# a new model (Opus 5.5) was missing from every price table in the house,
# and this app's per-agent picker only knew what ``constants.py`` listed.
#
# Same rules as the household default: a deliberate copy of
# ``ops_core.katalog``, read at call time, never raises; without the file
# the app works exactly as before.

def catalog_file() -> Path:
    env = os.environ.get("OPS_CORE_KATALOG")
    if env:
        return Path(env)
    return Path(os.environ.get("OPS_CORE_HOME") or Path.home() / ".ops-core") / "katalog.toml"


def _price(value) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value)


def load_catalog(provider: str = CLAUDE, path: Optional[Path] = None) -> dict:
    """``{"current": [ids], "prices": {id: {"input", "output", "cache_read"?,
    "cache_write"?}}, "names": {id: "Claude Sonnet 5.5"}, "stand": str | None}``
    for one provider — or ``{}`` without a catalog.

    Prices are US dollars per million tokens, the unit of the model registry.
    Names carry the family and version (``core/modell_meldung.py`` reads them).
    """
    path = path or catalog_file()
    try:
        if not path.is_file():
            return {}
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        logger.warning("model catalog unreadable (%s): %s", path, exc)
        return {}
    entry = raw.get(provider)
    if not isinstance(entry, dict):
        return {}
    current = [m.strip() for m in entry.get("aktuell") or []
               if isinstance(m, str) and m.strip()]
    prices, names = {}, {}
    for model_id, p in (entry.get("preise") or {}).items():
        if not isinstance(p, dict):
            continue
        if isinstance(p.get("name"), str) and p["name"].strip():
            names[model_id] = p["name"].strip()
        inp, out = _price(p.get("eingabe")), _price(p.get("ausgabe"))
        if inp is None or out is None:
            continue
        price = {"input": inp, "output": out}
        if _price(p.get("cache_lesen")) is not None:
            price["cache_read"] = _price(p.get("cache_lesen"))
        if _price(p.get("cache_schreiben")) is not None:
            price["cache_write"] = _price(p.get("cache_schreiben"))
        prices[model_id] = price
    stand = entry.get("stand")
    return {"current": current, "prices": prices, "names": names,
            "stand": str(stand) if stand else None}
