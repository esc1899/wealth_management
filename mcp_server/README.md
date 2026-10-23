# Wealth Management MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server that lets Claude Code write a research answer into the Wealth Management app. The answer appears on the title page of its ticker — without touching the app UI.

Until 2026-10-23 the server also proposed watchlist candidates (`propose_*`, via a file outbox) and read a research queue (`get_research_queue`, `complete_research_request`, a UserPromptSubmit hook). Those went with the pages that read them (CHANGELOG).

## What is MCP?

MCP (Model Context Protocol) is an open protocol that lets LLM clients (Claude Code, Claude Desktop, etc.) call tools defined in external server processes. The transport is **JSON-RPC 2.0 over stdio** — no HTTP server, no ports, no auth setup. The server process is started on demand when the client connects.

```
Claude Code  ──(spawn)──►  python -m mcp_server.wealth_mcp
             ◄──stdio────  FastMCP SDK dispatches tool calls
```

Tool functions are plain Python with a `@mcp.tool()` decorator. The function docstring becomes the description Claude uses to decide when to call it.

## Project Layout

```
mcp_server/
├── wealth_mcp.py     # MCP server (mcp_venv)
├── _helpers.py       # Pure helpers — no mcp import, testable from .venv
├── requirements.txt  # mcp[cli]>=1.0.0, pyyaml>=6.0
└── README.md
```

The MCP SDK lives in its own venv (`mcp_venv/`), so it stays out of the app's dependencies. `_helpers.py` holds what needs testing (input validation, the Bearer token middleware) with zero SDK imports, so the test suite imports it from `.venv`.

## Setup

### 1. Create the venv

```bash
/opt/homebrew/bin/python3.11 -m venv mcp_venv
mcp_venv/bin/pip install -r mcp_server/requirements.txt
```

### 2. Verify the MCP server starts

```bash
# Should print the MCP server banner and wait for input
mcp_venv/bin/python -m mcp_server.wealth_mcp
# Ctrl+C to stop
```

### 3. Register with Claude Code

`.mcp.json` in the project root handles registration:

```json
{
  "mcpServers": {
    "wealth-research": {
      "command": "/Users/erik/Projects/wealth_management/mcp_venv/bin/python",
      "args": ["-m", "mcp_server.wealth_mcp"],
      "cwd": "/Users/erik/Projects/wealth_management"
    }
  }
}
```

`.claude/settings.json` auto-approves it with `"enabledMcpjsonServers": ["wealth-research"]`; without it, Claude Code prompts for approval on every new session.

### 4. Verify in Claude Code

Start a new Claude Code session in this project. Type `/mcp` — you should see `wealth-research` listed as connected with 1 tool.

## The tool

#### `submit_research_answer(answer_markdown, ticker?)`

Writes a research answer to `research_answers`. The title page of the position with this ticker shows it; the app also matches the base symbol (`SAP` ↔ `SAP.DE`).

```
submit_research_answer(
    answer_markdown="## AAPL Q3 Analysis\n\nRevenue grew 8% YoY...",
    ticker="AAPL",
)
```

Limits: `answer_markdown` ≤ 100 KB, `ticker` ≤ 20 characters — the same as in `core/storage/research_queue.py`; a test keeps both in sync.

## Configuration (`.env`)

```env
# DB path (defaults to data/portfolio.db)
DB_PATH=data/portfolio.db
```

The server reads `.env` manually at startup (no python-dotenv dependency). The HTTP transport (`--transport streamable-http`) needs `MCP_BEARER_TOKEN`.

## Running Tests

```bash
pytest tests/unit/test_mcp_tools.py -v       # Bearer middleware + input validation
pytest tests/unit/test_research_queue.py -v  # ResearchQueueRepository (answers)
```

## Privacy boundary

The MCP server has access to the full DB file. The tool only writes to `research_answers` and reads nothing. The same privacy rules from `CLAUDE.md` apply: no portfolio names, quantities, or stories leave the local machine.
