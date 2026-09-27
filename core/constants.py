"""
Central registry for constant values across the application.

Includes model identifiers, feature flags, and other magic strings.
Purpose: Prevent hardcoded model strings scattered across codebase (DEBT-3).
"""

# =========================================================================
# Claude API Model Identifiers
# =========================================================================

# Jeweils das aktuelle Modell der Klasse (Stand 2026-08-30). Beim Wechsel auch die
# Preise in core/storage/app_config.py mitziehen und die gespeicherten Auswahlen
# (app_config `model_claude_*` / `model_public_*`, scheduled_jobs.model) migrieren —
# sonst rufen bestehende Jobs weiter das alte Modell.
CLAUDE_HAIKU = "claude-haiku-4-5-20251001"
CLAUDE_SONNET = "claude-sonnet-5"
CLAUDE_OPUS = "claude-opus-5"


def supports_effort(model: str) -> bool:
    """Nimmt dieses Modell ``effort`` und adaptives Denken? (2026-09-27)

    Bis dahin stand hier eine feste Menge {Sonnet 5, Opus 5} — jedes neuere Modell
    (Opus 5.5) fiel still heraus, der Thinking-Schalter war grau und die Denktiefe
    stand auf dem Modell-Default. Alle aktuellen Claude-Modelle können es; nur Haiku
    4.5 kennt ``effort`` nicht.
    """
    return model.startswith("claude-") and "haiku" not in model


# Per-agent default models (based on cost/capability trade-offs)
CLAUDE_MODEL_DEFAULTS = {
    "haiku": CLAUDE_HAIKU,          # research, news, storychecker (lower cost)
    "sonnet": CLAUDE_SONNET,        # structural_scan, fundamental, consensus_gap (web search requires sonnet+)
    "opus": CLAUDE_OPUS,
}

# Comma-separated list for config.py environment default
CLAUDE_MODELS_DEFAULT_LIST = f"{CLAUDE_HAIKU},{CLAUDE_SONNET},{CLAUDE_OPUS}"

# =========================================================================
# Benchmark (Verdict Hindsight + Vermögenshistorie TWR)
# =========================================================================

# app_config key + default for the comparison index. Shared so the daily market
# refresh keeps the benchmark history current (FEAT-73).
BENCHMARK_SYMBOL_KEY = "hindsight_benchmark_symbol"
DEFAULT_BENCHMARK_SYMBOL = "EUNL.DE"  # iShares Core MSCI World (acc, EUR)

# =========================================================================
# Agent Skill Defaults
# =========================================================================

# Default skills for background agents when no scheduled job is defined
AGENT_SKILL_DEFAULTS = {
    "storychecker": "Standard",
    "fundamental_analyzer": "Standard",
    "consensus_gap": "Standard",
    "structural_scan": "Standard",
    "news": "Standard",
}
