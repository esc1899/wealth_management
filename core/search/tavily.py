"""
Tavily search client — drop-in replacement for Anthropic's server-side web_search.
Used by ClaudeProvider when TAVILY_API_KEY is set in the environment.
"""

from __future__ import annotations

from typing import Optional

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
        content = r.get("content", "")
        lines.append(f"**{title}**\n{url}\n{content}")

    return "\n\n---\n\n".join(lines)
