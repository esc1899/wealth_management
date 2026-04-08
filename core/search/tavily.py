"""
Tavily search client — drop-in replacement for Anthropic's server-side web_search.
Used by ClaudeProvider when TAVILY_API_KEY is set in the environment.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

_logger = logging.getLogger(__name__)

# Patterns to detect potential prompt injection attempts in search results
_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|prior)\s+instructions?",
    r"disregard\s+(your|all|the)\s+(system\s+)?(prompt|instructions?)",
    r"new\s+instructions?",
    r"forget\s+(everything|all\s+previous)",
    r"you\s+are\s+now\s+a",
    r"system\s+prompt",
]
_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]

# Tool definition passed to Claude (client-side tool, not server-side)
TAVILY_TOOL_DEFINITION = {
    "name": "web_search",
    "description": (
        "Search the web for current information. Use this to find recent news, "
        "financial data, analyst opinions, or any information that may have changed "
        "since your training cutoff."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            }
        },
        "required": ["query"],
    },
}


def sanitize_search_result(text: str) -> str:
    """
    Scan a search result for prompt injection patterns.
    Logs a warning if found, replaces suspicious content with [REDACTED].

    Args:
        text: The search result content to sanitize

    Returns:
        Sanitized text with injection patterns replaced
    """
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(text):
            _logger.warning(
                "Prompt injection pattern detected in search result: %s",
                pattern.pattern,
            )
            text = pattern.sub("[REDACTED]", text)
    return text


def search(query: str, api_key: str, max_results: int = 5) -> str:
    """
    Execute a Tavily search and return results as a formatted string
    suitable for injection as a tool_result into Claude's context.
    """
    from tavily import TavilyClient  # type: ignore

    client = TavilyClient(api_key=api_key)
    response = client.search(query=query, max_results=max_results)

    results = response.get("results", [])
    if not results:
        return "No results found."

    lines = []
    for r in results:
        title = r.get("title", "")
        url = r.get("url", "")
        content = sanitize_search_result(r.get("content", ""))
        lines.append(f"**{title}**\n{url}\n{content}")

    return "\n\n---\n\n".join(lines)
