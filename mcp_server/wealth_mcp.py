"""
Wealth Management MCP Server.

Exposes one tool to Claude Code:

    submit_research_answer(...) — write a research answer for a ticker; the app shows it on
                                  the title page of that position

Proposals for the watchlist (propose_*) and the research queue (get_research_queue,
complete_research_request, the UserPromptSubmit hook) were removed on 2026-10-23 together
with the pages that read them (CHANGELOG).

Usage (from project root):
  stdio (Claude Code CLI/Desktop):
    mcp_venv/bin/python -m mcp_server.wealth_mcp

  HTTP (claude.ai Web / sandboxed environments):
    mcp_venv/bin/python -m mcp_server.wealth_mcp --transport streamable-http [--port 7890]
    Requires MCP_BEARER_TOKEN in .env.  Connect via: http://localhost:7890/mcp

Claude Code registration (stdio):
    claude mcp add wealth-research mcp_venv/bin/python -- -m mcp_server.wealth_mcp

Claude.ai Web registration:
    Settings → Connectors → Add → URL: http://localhost:7890/mcp
    Bearer token: value of MCP_BEARER_TOKEN in your .env
"""

from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp_server._helpers import BearerTokenMiddleware as _BearerTokenMiddleware
from mcp_server._helpers import validate_answer_input as _validate_answer_input

# ---------------------------------------------------------------------------
# Config — read .env from the project root (one level up from this file)
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent

# Load .env manually so this server works without python-dotenv in the venv
_env_path = _PROJECT_ROOT / ".env"
if _env_path.exists():
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

_DB_PATH = Path(
    os.environ.get("DB_PATH", str(_PROJECT_ROOT / "data" / "portfolio.db"))
).expanduser()
if not _DB_PATH.is_absolute():
    _DB_PATH = _PROJECT_ROOT / _DB_PATH

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("wealth-research")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Research answers (FEAT-50)
# ---------------------------------------------------------------------------

@mcp.tool()
def submit_research_answer(
    answer_markdown: str,
    ticker: Optional[str] = None,
) -> str:
    """Submit a research answer back to the app.

    The answer appears on the title page of the position with this ticker.

    Args:
        answer_markdown: The full answer in Markdown format (max 100 KB)
        ticker: Ticker this answer relates to (max 20 chars), in the app's notation
            (e.g. "SAP.DE"); the app also matches the base symbol ("SAP").
    """
    error = _validate_answer_input(answer_markdown, ticker)
    if error:
        return error

    try:
        conn = _get_conn()
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO research_answers (request_id, ticker, answer_md, created_at) VALUES (?, ?, ?, ?)",
            (None, ticker.upper() if ticker else None, answer_markdown.strip(), now),
        )
        answer_id = cur.lastrowid
        conn.commit()
        conn.close()
    except Exception as exc:
        return f"Error submitting answer: {exc}"

    return f"✅ Answer saved (answer #{answer_id}). It will appear on the title page of its ticker."


# ---------------------------------------------------------------------------
# Entry point — HTTP auth (FEAT-53) via _helpers.BearerTokenMiddleware
# ---------------------------------------------------------------------------

def _main() -> None:
    import argparse
    import anyio
    import uvicorn

    parser = argparse.ArgumentParser(prog="wealth_mcp", add_help=False)
    parser.add_argument("--transport", default="stdio", choices=["stdio", "streamable-http"])
    parser.add_argument("--port", type=int, default=7890)
    args, _ = parser.parse_known_args()

    if args.transport == "streamable-http":
        from core.secrets import get_secret

        bearer_token = get_secret("MCP_BEARER_TOKEN", "")
        if not bearer_token:
            print(
                "ERROR: MCP_BEARER_TOKEN not set (.env or keychain item wm-MCP_BEARER_TOKEN)"
                " — refusing to start HTTP server",
                file=sys.stderr,
            )
            sys.exit(1)

        asgi_app = _BearerTokenMiddleware(mcp.streamable_http_app(), bearer_token)
        config = uvicorn.Config(asgi_app, host="127.0.0.1", port=args.port, log_level="info")
        server = uvicorn.Server(config)
        anyio.run(server.serve)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    _main()
