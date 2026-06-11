"""
Wealth Management MCP Server.

Exposes research tooling to Claude Code:

  FEAT-49 — Cowork Ingest (write-only, no portfolio access)
    propose_position(...)      — propose one watchlist candidate → .md in outbox
    propose_multiple(...)      — propose several candidates at once

  FEAT-50 — Research Queue (App → Claude)
    get_research_queue()       — list open research requests from the app
    complete_research_request(...) — mark a request as done
    submit_research_answer(...)    — write an answer back to the app

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
import re
import sqlite3
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp_server._helpers import build_research_md as _build_research_md
from mcp_server._helpers import write_md_to_outbox as _write_md_to_outbox_helper

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

_OUTBOX_PATH = Path(
    os.environ.get("COWORK_OUTBOX_PATH", "~/wealth-research/outbox")
).expanduser()

_DB_PATH = Path(
    os.environ.get("DB_PATH", str(_PROJECT_ROOT / "data" / "portfolio.db"))
).expanduser()
if not _DB_PATH.is_absolute():
    _DB_PATH = _PROJECT_ROOT / _DB_PATH

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("wealth-research")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _write_md_to_outbox(content: str, filename: str) -> Path:
    return _write_md_to_outbox_helper(content, filename, _OUTBOX_PATH)


# ---------------------------------------------------------------------------
# FEAT-49: Cowork Ingest tools
# ---------------------------------------------------------------------------

@mcp.tool()
def propose_position(
    ticker: str,
    name: str,
    exchange: str,
    rationale: str,
    conviction: str,
    suggested_action: str,
    isin: Optional[str] = None,
    category: Optional[str] = None,
    story: Optional[str] = None,
    price: Optional[float] = None,
    sources: Optional[list[str]] = None,
) -> str:
    """Propose a single position for the watchlist.

    Creates a research .md file in the outbox — the app's file watcher
    picks it up automatically within seconds.

    Args:
        ticker: Stock ticker symbol (e.g. "AAPL")
        name: Full company name (e.g. "Apple Inc.")
        exchange: Exchange code (e.g. "NASDAQ", "XETRA", "NYSE")
        rationale: Investment thesis — why this position?
        conviction: "low", "medium", or "high"
        suggested_action: "add", "watch", or "skip"
        isin: Optional ISIN (e.g. "US0378331005")
        category: Asset class (e.g. "Aktie", "ETF", "Anleihe"). Defaults to "Aktie".
        story: Optional full investment story / long-form thesis
        price: Optional current price at time of research
        sources: Optional list of source URLs used in research
    """
    if conviction not in {"low", "medium", "high"}:
        return f"Error: conviction must be 'low', 'medium', or 'high', got '{conviction}'"
    if suggested_action not in {"add", "watch", "skip"}:
        return f"Error: suggested_action must be 'add', 'watch', or 'skip', got '{suggested_action}'"

    _slug = re.sub(r"[^A-Za-z0-9._-]", "_", ticker.lower())
    research_id = f"{date.today().isoformat()}-{_slug}-{uuid.uuid4().hex[:6]}"
    candidate: dict = {
        "ticker": ticker.upper(),
        "name": name,
        "exchange": exchange.upper(),
        "rationale": rationale,
        "conviction": conviction,
        "suggested_action": suggested_action,
    }
    if isin:
        candidate["isin"] = isin
    if category:
        candidate["category"] = category
    if price is not None:
        candidate["price_at_research"] = price

    body = story or ""
    content = _build_research_md(
        research_id=research_id,
        candidates=[candidate],
        primary_ticker=ticker,
        primary_name=name,
        primary_exchange=exchange,
        body=body,
        sources=sources,
    )

    filename = f"{research_id}.md"
    path = _write_md_to_outbox(content, filename)
    return (
        f"✅ Position '{name}' ({ticker.upper()}) proposed.\n"
        f"File written to outbox: {path.name}\n"
        f"The app's file watcher will import it automatically."
    )


@mcp.tool()
def propose_multiple(
    candidates: list[dict],
    body: Optional[str] = None,
    sources: Optional[list[str]] = None,
) -> str:
    """Propose multiple watchlist candidates at once.

    Each candidate dict must have:
        ticker, name, exchange, rationale, conviction, suggested_action
    Optional per-candidate fields:
        isin, category, price_at_research

    Args:
        candidates: List of candidate dicts (see field list above)
        body: Optional research summary / markdown body text
        sources: Optional list of source URLs
    """
    if not candidates:
        return "Error: candidates list is empty"

    validated: list[dict] = []
    for i, c in enumerate(candidates):
        for req in ("ticker", "name", "exchange", "rationale", "conviction", "suggested_action"):
            if not c.get(req):
                return f"Error: candidates[{i}] missing required field '{req}'"
        if c["conviction"] not in {"low", "medium", "high"}:
            return f"Error: candidates[{i}].conviction must be 'low'/'medium'/'high'"
        if c["suggested_action"] not in {"add", "watch", "skip"}:
            return f"Error: candidates[{i}].suggested_action must be 'add'/'watch'/'skip'"
        entry: dict = {
            "ticker": c["ticker"].upper(),
            "name": c["name"],
            "exchange": c["exchange"].upper(),
            "rationale": c["rationale"],
            "conviction": c["conviction"],
            "suggested_action": c["suggested_action"],
        }
        for opt in ("isin", "category", "price_at_research"):
            if c.get(opt) is not None:
                entry[opt] = c[opt]
        validated.append(entry)

    first = validated[0]
    _slug = re.sub(r"[^A-Za-z0-9._-]", "_", first["ticker"].lower())
    research_id = f"{date.today().isoformat()}-batch-{_slug}-{uuid.uuid4().hex[:8]}"
    content = _build_research_md(
        research_id=research_id,
        candidates=validated,
        primary_ticker=first["ticker"],
        primary_name=first["name"],
        primary_exchange=first["exchange"],
        body=body or "",
        sources=sources,
    )

    filename = f"{research_id}.md"
    path = _write_md_to_outbox(content, filename)
    tickers = ", ".join(c["ticker"] for c in validated)
    return (
        f"✅ {len(validated)} candidates proposed: {tickers}\n"
        f"File written to outbox: {path.name}\n"
        f"The app's file watcher will import them automatically."
    )


# ---------------------------------------------------------------------------
# FEAT-50: Research Queue tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_research_queue() -> str:
    """List all open research requests from the app.

    Returns a formatted list of pending tasks — research questions,
    watchlist candidates to investigate, or analysis deep-dives
    requested by the app or user.
    """
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT id, request_type, ticker, focus, context, source, created_at "
            "FROM research_requests WHERE status = 'open' ORDER BY created_at ASC"
        ).fetchall()
        conn.close()
    except Exception as exc:
        return f"Error reading research queue: {exc}"

    if not rows:
        return "✅ Research queue is empty — no open requests."

    lines = [f"📋 {len(rows)} open research request(s):\n"]
    for row in rows:
        ticker_part = f" [{row['ticker']}]" if row['ticker'] else ""
        ctx_part = f"\n   Context: {row['context']}" if row['context'] else ""
        ts = row['created_at'][:10]
        lines.append(
            f"  #{row['id']} [{row['request_type']}]{ticker_part} — {row['focus']}"
            f"\n   Source: {row['source']} | Created: {ts}{ctx_part}"
        )
    return "\n".join(lines)


@mcp.tool()
def complete_research_request(request_id: int) -> str:
    """Mark a research request as done.

    Call this after you've answered a request (e.g. via propose_position or
    submit_research_answer) so it disappears from the queue.

    Args:
        request_id: The numeric ID from get_research_queue()
    """
    try:
        conn = _get_conn()
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "UPDATE research_requests SET status = 'done', updated_at = ? "
            "WHERE id = ? AND status != 'done'",
            (now, request_id),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        return f"Error updating request #{request_id}: {exc}"

    if cur.rowcount == 0:
        return f"Request #{request_id} not found or already done."
    return f"✅ Request #{request_id} marked as done."


@mcp.tool()
def submit_research_answer(
    answer_markdown: str,
    request_id: Optional[int] = None,
    ticker: Optional[str] = None,
) -> str:
    """Submit a research answer back to the app.

    Use this for non-watchlist results: factual answers, deep-dive analyses,
    general findings. The answer will appear in the Research Answers section
    of the app.

    For watchlist candidates use propose_position() or propose_multiple() instead.

    Args:
        answer_markdown: The full answer in Markdown format
        request_id: Optional — link to a specific request from get_research_queue()
        ticker: Optional ticker this answer relates to
    """
    if not answer_markdown.strip():
        return "Error: answer_markdown must not be empty"
    if len(answer_markdown.encode()) > 100_000:
        return "Error: answer_markdown exceeds 100 KB limit"

    try:
        conn = _get_conn()
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            "INSERT INTO research_answers (request_id, ticker, answer_md, created_at) VALUES (?, ?, ?, ?)",
            (request_id, ticker.upper() if ticker else None, answer_markdown.strip(), now),
        )
        answer_id = cur.lastrowid

        if request_id:
            conn.execute(
                "UPDATE research_requests SET status = 'done', updated_at = ? WHERE id = ?",
                (now, request_id),
            )
        conn.commit()
        conn.close()
    except Exception as exc:
        return f"Error submitting answer: {exc}"

    ref = f" (answer #{answer_id})"
    req_note = f", request #{request_id} marked done" if request_id else ""
    return f"✅ Answer saved{ref}{req_note}. It will appear in the app under Research Answers."


# ---------------------------------------------------------------------------
# FEAT-53: HTTP Bearer-Token Auth Middleware
# ---------------------------------------------------------------------------

class _BearerTokenMiddleware:
    """ASGI middleware — rejects HTTP requests without the correct Bearer token."""

    def __init__(self, app, token: str) -> None:
        self._app = app
        self._token = token

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            headers = {k.lower(): v for k, v in scope.get("headers", [])}
            auth = headers.get(b"authorization", b"").decode()
            if not (auth.lower().startswith("bearer ") and auth[7:] == self._token):
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


# ---------------------------------------------------------------------------
# Entry point
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
        bearer_token = os.environ.get("MCP_BEARER_TOKEN", "")
        if not bearer_token:
            print(
                "ERROR: MCP_BEARER_TOKEN not set in .env — refusing to start HTTP server",
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
