# Wealth Management MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io/) server that connects Claude Code directly to the Wealth Management app. Claude Code can propose watchlist candidates, read the research queue, and submit answers — without touching the app UI.

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
├── wealth_mcp.py     # MCP server (Python 3.11, mcp_venv)
├── _helpers.py       # Pure helpers — no mcp import (Python 3.9, testable)
├── check_queue.py    # UserPromptSubmit hook script (/usr/bin/python3)
├── requirements.txt  # mcp[cli]>=1.0.0, pyyaml>=6.0
└── README.md
```

### Why two virtual environments?

The MCP SDK requires Python ≥ 3.10. The main app runs Python 3.9.6. Solution: separate venvs.

| Venv | Python | Used for |
|---|---|---|
| `.venv/` | 3.9.6 | Main app, all tests, all imports |
| `mcp_venv/` | 3.11.15 | `wealth_mcp.py` only |

`_helpers.py` bridges the gap: it contains all logic that needs to be tested (YAML building, atomic file writes) with zero SDK imports, so it's importable from `.venv` in the test suite.

## Setup

### 1. Create the Python 3.11 venv

```bash
# Install Python 3.11 if needed
brew install python@3.11

# Create venv and install dependencies
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

`.claude/settings.json` auto-approves it:

```json
{
  "enabledMcpjsonServers": ["wealth-research"]
}
```

Without `enabledMcpjsonServers`, Claude Code prompts for approval on every new session.

### 4. Verify in Claude Code

Start a new Claude Code session in this project. Type `/mcp` — you should see `wealth-research` listed as connected with 5 tools.

## Available Tools

### Cowork Ingest (Claude → App)

#### `propose_position()`

Proposes a single watchlist candidate. Writes an atomic `.md` file to the Cowork outbox. The app's file watcher imports it automatically within seconds.

```
propose_position(
    ticker="AAPL",
    name="Apple Inc.",
    exchange="NASDAQ",
    rationale="Strong ecosystem lock-in, high recurring revenue from services.",
    conviction="high",          # low | medium | high
    suggested_action="add",     # add | watch | skip
    isin="US0378331005",        # optional
    category="Aktie",           # optional
    story="Long-term thesis...", # optional full write-up
    price=195.50,               # optional current price
    sources=["https://..."],    # optional URLs
)
```

#### `propose_multiple()`

Batch version — proposes several candidates in a single `.md` file.

```
propose_multiple(
    candidates=[
        {"ticker": "MSFT", "name": "Microsoft", "exchange": "NASDAQ",
         "rationale": "...", "conviction": "high", "suggested_action": "add"},
        {"ticker": "GOOGL", ...},
    ],
    body="## Summary\nAI infrastructure play...",
    sources=["https://..."],
)
```

### Research Queue (App ↔ Claude)

#### `get_research_queue()`

Lists all open research requests posted from the app.

```
get_research_queue()
# → "📋 2 open research request(s): ..."
```

#### `complete_research_request(request_id)`

Marks a request as done without submitting an answer (use after `propose_position()` for watchlist requests).

```
complete_research_request(request_id=3)
```

#### `submit_research_answer(answer_markdown, request_id?, ticker?)`

Writes a research answer back to the app. The answer appears in the **Research Answers** page. Automatically marks the linked request as done.

```
submit_research_answer(
    answer_markdown="## AAPL Q3 Analysis\n\nRevenue grew 8% YoY...",
    request_id=1,    # optional — link to a specific request
    ticker="AAPL",   # optional — for filtering in the UI
)
```

## UserPromptSubmit Hook (FEAT-51)

`check_queue.py` runs before every Claude Code message. It reads open requests from the DB and injects them as `additionalContext`:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "📋 2 offene Anfragen..."
  }
}
```

This means Claude sees open requests **automatically** at the start of every session — without the user having to ask. The hook is silent when the queue is empty (exits 0, no output).

Registered in `.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "/usr/bin/python3 /Users/erik/Projects/wealth_management/mcp_server/check_queue.py"
      }]
    }]
  }
}
```

Uses `/usr/bin/python3` (system Python, no venv needed — only uses `sqlite3` and `json` from stdlib).

## Configuration (`.env`)

```env
# Path to the Cowork outbox (propose_position writes here)
COWORK_OUTBOX_PATH=~/wealth-research/outbox

# DB path (defaults to data/portfolio.db)
DB_PATH=data/portfolio.db
```

The server reads `.env` manually at startup (no python-dotenv dependency).

## Running Tests

Tests live in `.venv` (Python 3.9) and import from `_helpers.py` only:

```bash
pytest tests/unit/test_mcp_tools.py -v       # 8 tests: build_research_md + write_md_to_outbox
pytest tests/unit/test_research_queue.py -v  # 23 tests: ResearchQueueRepository CRUD
```

## Architecture Notes

### Atomic file writes

`_helpers.write_md_to_outbox()` uses a tmp-then-rename pattern:

```python
tmp_path.write_text(content)
tmp_path.rename(final_path)  # atomic on same filesystem
```

This prevents the file watcher from reading a partially written file.

### Why not a REST API?

MCP over stdio has no network surface, no auth, no server to keep running. For a local tool that Claude Code calls on the same machine, stdio is simpler and safer than opening a port.

### Privacy boundary

The MCP server has access to the full DB (including encrypted position data — it reads the raw bytes). However, the tool implementations intentionally only read from `research_requests` / `research_answers` and only write to `research_answers` and the Cowork outbox. The same privacy rules from `CLAUDE.md` apply: no portfolio names, quantities, or stories leave the local machine.
