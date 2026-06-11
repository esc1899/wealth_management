"""
Pure helper functions for the MCP server — no mcp SDK dependency.
Importable from the main project venv (Python 3.9) for testing.
"""

from __future__ import annotations

import hmac
import os
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

# SEC-5 (e): Limits müssen mit core/storage/research_queue.py synchron bleiben
# (der MCP-Server schreibt per Raw-SQL am Repository vorbei — beide Pfade
# validieren identisch; ein Test in test_research_queue.py erzwingt das).
MAX_TICKER_LEN = 20
MAX_ANSWER_BYTES = 100_000


def validate_answer_input(answer_markdown: str, ticker: Optional[str]) -> Optional[str]:
    """Validate submit_research_answer input. Returns an error string or None."""
    if not answer_markdown.strip():
        return "Error: answer_markdown must not be empty"
    if len(answer_markdown.encode()) > MAX_ANSWER_BYTES:
        return "Error: answer_markdown exceeds 100 KB limit"
    if ticker and len(ticker) > MAX_TICKER_LEN:
        return f"Error: ticker exceeds {MAX_TICKER_LEN} characters"
    return None


class BearerTokenMiddleware:
    """ASGI middleware — rejects HTTP requests without the correct Bearer token.

    SEC-5: constant-time token comparison; websocket scopes are rejected
    outright (Streamable HTTP uses none — defense in depth).
    """

    def __init__(self, app, token: str) -> None:
        self._app = app
        self._token = token

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "websocket":
            await receive()
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] == "http":
            headers = {k.lower(): v for k, v in scope.get("headers", [])}
            auth = headers.get(b"authorization", b"").decode()
            token_ok = auth.lower().startswith("bearer ") and hmac.compare_digest(
                auth[7:], self._token
            )
            if not token_ok:
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"www-authenticate", b'Bearer realm="wealth-research"'),
                    ],
                })
                await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
                return
        await self._app(scope, receive, send)


def build_research_md(
    research_id: str,
    candidates: list,
    primary_ticker: Optional[str] = None,
    primary_name: Optional[str] = None,
    primary_exchange: Optional[str] = None,
    body: str = "",
    sources: Optional[list] = None,
) -> str:
    """Build a valid cowork research .md file string."""
    frontmatter: dict = {
        "research_id": research_id,
        "type": "watchlist_scan",
        "date": date.today().isoformat(),
        "ai_generated": True,
        "model": "claude-code",
        "status": "ready_for_import",
        "disclaimer": "AI-generated research via Claude Code MCP tool. Not financial advice.",
        "sources": sources or [],
        "watchlist_candidates": candidates,
    }
    if primary_ticker and primary_name and primary_exchange:
        frontmatter["primary"] = {
            "ticker": primary_ticker.upper(),
            "name": primary_name,
            "exchange": primary_exchange.upper(),
        }
    fm_yaml = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False)
    body_section = body.strip() if body.strip() else "*(no additional notes)*"
    return f"---\n{fm_yaml}---\n\n{body_section}\n"


def write_md_to_outbox(content: str, filename: str, outbox_path: Path) -> Path:
    """Atomically write content to the outbox. Returns the final path."""
    outbox_path.mkdir(parents=True, exist_ok=True)
    tmp_dir = outbox_path / ".tmp"
    tmp_dir.mkdir(exist_ok=True)
    tmp_path = tmp_dir / filename
    final_path = outbox_path / filename
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.rename(final_path)
    return final_path
