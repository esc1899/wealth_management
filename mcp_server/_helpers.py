"""
Pure helper functions for the MCP server — no mcp SDK dependency.
Importable from the main project venv for testing.
"""

from __future__ import annotations

import hmac
from typing import Optional

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
