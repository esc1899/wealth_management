"""Single source of truth for LLM provider routing.

The model→provider decision and the Tavily agent flags live here so the call sites
(interactive factories in state_llm, background jobs, scheduler) cannot drift apart.
Each call site passes the credentials it actually has via the ``has_*`` flags; the
routing rule itself is defined exactly once.
"""

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


def resolve_provider_kind(
    model: str,
    *,
    has_anthropic: bool,
    has_deepseek: bool,
    has_openai_base: bool,
) -> str:
    """Decide which provider to use for a model. Returns 'claude' | 'deepseek' | 'openai'.

    This is THE routing rule — every call site delegates here so it cannot drift.
    A call site that lacks credentials for a kind passes the matching ``has_*=False``
    (e.g. the scheduler has no DeepSeek-direct keys), and the model falls through.
    """
    if model.startswith("claude-") and has_anthropic:
        return "claude"
    if model.startswith("deepseek-") and has_deepseek:
        return "deepseek"
    if has_openai_base:
        return "openai"
    return "claude"
