#!/usr/bin/env python3
"""
FEAT-51: Check open research requests at Claude Code session start.

Called by UserPromptSubmit hook. Outputs a reminder if there are open requests.
Outputs nothing (silent) when queue is empty.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path
from xml.sax.saxutils import escape


def _attr(value: str) -> str:
    """Escape a value for use inside a double-quoted XML attribute (SEC-5)."""
    return escape(value, {'"': "&quot;"})

_PROJECT_ROOT = Path(__file__).parent.parent

# Load .env
_env_path = _PROJECT_ROOT / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

_DB_PATH = Path(
    os.environ.get("DB_PATH", str(_PROJECT_ROOT / "data" / "portfolio.db"))
).expanduser()
if not _DB_PATH.is_absolute():
    _DB_PATH = _PROJECT_ROOT / _DB_PATH

if not _DB_PATH.exists():
    sys.exit(0)

try:
    conn = sqlite3.connect(str(_DB_PATH))
    rows = conn.execute(
        "SELECT id, request_type, ticker, focus, created_at "
        "FROM research_requests WHERE status = 'open' ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
except Exception:
    sys.exit(0)

if not rows:
    sys.exit(0)

lines = [f"\n<wealth_management_research_queue count=\"{len(rows)}\">\n"]
for row in rows:
    rid, rtype, ticker, focus, created_at = row
    ts = created_at[:10] if created_at else ""
    # Escaping verhindert Tag-Breakout aus der SEC-4-Rahmung (SEC-5 d)
    lines.append(
        f"  <research_request id=\"{rid}\" type=\"{_attr(rtype or '')}\" "
        f"ticker=\"{_attr(ticker or '')}\" date=\"{ts}\">"
        f"{escape(focus or '')}"
        f"</research_request>"
    )
lines.append("\n</wealth_management_research_queue>")
lines.append("\nNutze `get_research_queue()` für Details oder bearbeite sie direkt.\n")

# UserPromptSubmit hook: inject context before the user's message
output = {
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": "\n".join(lines),
    }
}
print(json.dumps(output))
