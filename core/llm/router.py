"""Single source of truth for LLM provider routing.

The model→provider decision and the Tavily agent flags live here so the call sites
(interactive factories in state_llm, background jobs, scheduler) cannot drift apart.
Each call site passes the credentials it actually has via the ``has_*`` flags; the
routing rule itself is defined exactly once.
"""

import re

# Datierte Modell-ID und datumsloser Alias sind dasselbe Modell
# (claude-haiku-4-5-20251001 ↔ claude-haiku-4-5).
_DATE_SUFFIX = re.compile(r"-\d{8}$")


def _base_model_id(model_id: str) -> str:
    return _DATE_SUFFIX.sub("", model_id)


def current_claude_models(configured: list[str], available: list[str]) -> list[str]:
    """Auswahlliste der Claude-Modelle: die konfigurierten — jeweils aktuellen — Modelle,
    gefiltert auf das, was der Account laut Models-API wirklich anbietet.

    ``client.models.list()`` liefert die komplette Claude-Historie inklusive abgelöster
    Versionen. Als Dropdown ist das Lärm, und ein versehentlich gewähltes Altmodell fällt
    erst Wochen später in der Kostenstatistik auf. Die API-Liste dient daher nur als
    Verfügbarkeitsfilter: was der Key nicht sehen kann (Firmenproxy, gesperrtes Modell),
    verschwindet. Liefert die Abfrage nichts, bleibt die konfigurierte Liste stehen —
    lieber eine ungefilterte Auswahl als gar keine.
    """
    if not available:
        return list(configured)
    bases = {_base_model_id(m) for m in available}
    filtered = [m for m in configured if _base_model_id(m) in bases]
    return filtered or list(configured)

# Agents whose Tavily web search should run in "news" topic mode (recent days).
TAVILY_NEWS_AGENTS = {"news", "structural_scan", "sector_rotation", "search_agent"}
# Agents that benefit from Tavily "advanced" search depth.
TAVILY_ADVANCED_AGENTS = {"fundamental_analyzer"}


def tavily_search_depth(agent_name: str) -> str:
    """Tavily search depth for an agent ('advanced' or 'basic')."""
    return "advanced" if agent_name in TAVILY_ADVANCED_AGENTS else "basic"


def tavily_news_mode(agent_name: str) -> bool:
    """Whether the agent's Tavily search should run in recent-news mode."""
    return agent_name in TAVILY_NEWS_AGENTS


def resolve_house_model(
    model: str,
    *,
    has_anthropic: bool = True,
    has_openai_base: bool = False,
    local: bool = False,
    fallback: str = "",
) -> str:
    """Turn the ``home`` setting into a real model id (2026-09-22).

    A model of ``home`` follows the household default from
    ``~/.ops-core/modelle.toml`` — one place where Erik changes every app
    that is set to follow. Which entry applies is decided the same way the
    call itself is routed: a local setting takes Ollama's, a cloud setting
    takes Claude's, unless this install has no Anthropic key and does have
    an OpenAI-compatible base (then it is OpenRouter's).

    Resolved per call, not once at startup, so a change takes effect
    without a restart; without an entry the caller's ``fallback`` stands.

    ``neuestes:<family>`` (2026-09-29) is resolved here too: the newest
    model of that Claude family in the household catalog.
    """
    from core import house_models

    if house_models.is_newest(model):
        # "neuestes:sonnet" (2026-09-29): das neueste Sonnet laut Katalog.
        # Ohne Katalog die Vorgabe der Klasse aus constants.py.
        from core.constants import CLAUDE_MODEL_DEFAULTS

        family = model.strip()[len(house_models.NEWEST):]
        return house_models.resolve_newest(
            model, fallback=CLAUDE_MODEL_DEFAULTS.get(family) or fallback)
    if not house_models.is_home(model):
        return model
    if local:
        provider = house_models.OLLAMA
    elif not has_anthropic and has_openai_base:
        provider = house_models.OPENROUTER
    else:
        provider = house_models.CLAUDE
    return house_models.resolve(model, provider, fallback=fallback)


def resolve_provider_kind(
    model: str,
    *,
    has_anthropic: bool,
    has_openai_base: bool,
) -> str:
    """Decide which provider to use for a model. Returns 'claude' | 'openai'.

    This is THE routing rule — every call site delegates here so it cannot drift.
    DeepSeek direkt gibt es seit 12.10.2026 nicht mehr: DeepSeek kommt ueber OpenRouter.
    """
    if model.startswith("claude-") and has_anthropic:
        return "claude"
    if has_openai_base:
        return "openai"
    return "claude"


def available_public_models(
    *,
    claude_models: list[str],
    openrouter_models: list[str],
    has_anthropic: bool,
    has_openrouter: bool,
) -> list[str]:
    """Ordered, deduplicated cloud-model list for the settings dropdown: OpenRouter, then
    Claude -- only providers that are actually configured, else a pick routes to the
    wrong endpoint and 404s."""
    ordered: list[str] = []
    if has_openrouter:
        ordered += openrouter_models
    if has_anthropic:
        ordered += claude_models
    return list(dict.fromkeys(ordered))
