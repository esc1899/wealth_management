"""
Central registry for constant values across the application.

Includes model identifiers, feature flags, and other magic strings.
Purpose: Prevent hardcoded model strings scattered across codebase (DEBT-3).
"""

# =========================================================================
# Claude API Model Identifiers
# =========================================================================

CLAUDE_HAIKU = "claude-haiku-4-5-20251001"
CLAUDE_SONNET = "claude-sonnet-4-6"
CLAUDE_OPUS = "claude-opus-4-6"

# Per-agent default models (based on cost/capability trade-offs)
CLAUDE_MODEL_DEFAULTS = {
    "haiku": CLAUDE_HAIKU,          # research, news, storychecker (lower cost)
    "sonnet": CLAUDE_SONNET,        # structural_scan, fundamental, consensus_gap (web search requires sonnet+)
    "opus": CLAUDE_OPUS,
}

# Comma-separated list for config.py environment default
CLAUDE_MODELS_DEFAULT_LIST = f"{CLAUDE_HAIKU},{CLAUDE_SONNET},{CLAUDE_OPUS}"

# =========================================================================
# Agent Skill Defaults
# =========================================================================

# Default skills for background agents when no scheduled job is defined
AGENT_SKILL_DEFAULTS = {
    "storychecker": "Standard",
    "fundamental": "Standard",
    "consensus_gap": "Standard",
    "structural_scan": "Standard",
    "news": "Standard",
}
