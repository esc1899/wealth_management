"""Preise der Sprachmodelle -- nur gelesen, nie in der App gepflegt (12.10.2026).

Bis zum 12.10.2026 stand hier eine Registry, die man in den Einstellungen von Hand
pflegte: Preis, Anbieter und Ollama-Parameter je Modell. Keine dieser Angaben braucht
eine Eingabe:

* **Claude** -- aus dem Modellkatalog des Hauses (``~/.ops-core/katalog.toml``, gepflegt
  vom Maschinenraum; ``core.house_models.load_catalog``). Der Katalog vergisst keinen
  Preis, auch alte Aufrufe behalten ihren.
* **OpenRouter** -- abgerechnet wird ohnehin, was OpenRouter je Aufruf meldet (Job
  ``kosten``). Bis dahin gilt der Listenpreis, den derselbe Job einmal am Tag aus
  ``/models`` holt und unter ``preise_openrouter`` ablegt (``openrouter_ablegen``); auch er
  vergisst keinen Preis.
* **Ollama** -- kostet nichts.

Ein Modell ohne Preis kostet "offen" (``preis`` gibt ``None``), nie 0 -- eine eigene
Preistabelle baute das Loch nach, das Opus 5.5 im Haus aufgedeckt hat.

Der Anbieter folgt aus der ID: ``claude-...`` ist Anthropic, ``hersteller/modell`` ist
OpenRouter, alles andere laeuft lokal. DeepSeek direkt gibt es seit dem 12.10.2026 nicht
mehr; DeepSeek-Modelle kommen ueber OpenRouter (``deepseek/...``), alte Aufrufe
(``deepseek-...``) behalten ihren Anbieter und haben keinen Preis.

Fuer Lotsee gilt das so nicht: Eine App auf dem Geraet hat keinen Katalog des Hauses und
braucht eine eigene Preisquelle (lotsee ``docs/plan.md``).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

CLAUDE = "claude"
OPENROUTER = "openrouter"
OLLAMA = "ollama"
#: Nur noch in alten Aufrufen: DeepSeek direkt (bis 12.10.2026). Ohne Preis, also "offen" --
#: nicht still kostenlos, wie es die Regel fuer lokale Modelle saehe.
DEEPSEEK = "deepseek"
ANBIETER = (CLAUDE, OPENROUTER, OLLAMA)

#: Schluessel in app_config: {modell: {"input", "output"}} und das Datum des letzten Abrufs.
OPENROUTER_SCHLUESSEL = "preise_openrouter"
OPENROUTER_STAND = "preise_openrouter_stand"

_KOSTENLOS = {"input": 0.0, "output": 0.0}


def anbieter(modell: str) -> str:
    """Wer das Modell rechnet -- allein aus der ID."""
    if modell.startswith("claude-"):
        return CLAUDE
    if "/" in modell:
        return OPENROUTER
    if modell.startswith("deepseek-"):
        return DEEPSEEK
    return OLLAMA


def preisliste(app_cfg=None, katalog: Optional[dict] = None) -> dict:
    """``{modell: {"input", "output", ["cache_read", "cache_write"], "quelle"}}``,
    US-Dollar je Million Token. Lokale Modelle stehen nicht darin -- sie kosten nichts
    (``preis``)."""
    from core import house_models

    if katalog is None:
        katalog = house_models.load_catalog(house_models.CLAUDE)
    liste = {m: {**p, "quelle": "katalog"} for m, p in (katalog.get("prices") or {}).items()}
    if app_cfg is not None:
        for m, p in (app_cfg.get_json(OPENROUTER_SCHLUESSEL, {}) or {}).items():
            liste.setdefault(m, {**p, "quelle": "openrouter"})
    return liste


def preis(modell: str, liste: dict) -> Optional[dict]:
    """Der Preis eines Modells oder ``None`` ("offen"). Datierte ID und datumsloser Alias
    sind dasselbe Modell (``claude-haiku-4-5-20251001`` = ``claude-haiku-4-5``)."""
    if anbieter(modell) == OLLAMA:
        return dict(_KOSTENLOS)
    if modell in liste:
        return liste[modell]
    from core.llm.router import _base_model_id

    basis = _base_model_id(modell)
    return next((p for m, p in liste.items() if _base_model_id(m) == basis), None)


def openrouter_faellig(app_cfg, heute: Optional[date] = None) -> bool:
    """Einmal am Tag reicht: Listenpreise aendern sich selten, abgerechnet wird ohnehin echt."""
    return app_cfg.get(OPENROUTER_STAND) != (heute or date.today()).isoformat()


def openrouter_ablegen(app_cfg, neu: dict, heute: Optional[date] = None) -> int:
    """Neue Listenpreise zu den alten legen -- ein alter Preis bleibt, ein neuer ersetzt ihn.
    Gibt die Zahl der Modelle zurueck, deren Preis gekommen ist."""
    alt = app_cfg.get_json(OPENROUTER_SCHLUESSEL, {}) or {}
    app_cfg.set_json(OPENROUTER_SCHLUESSEL, {**alt, **neu})
    app_cfg.set(OPENROUTER_STAND, (heute or date.today()).isoformat())
    return len(neu)
