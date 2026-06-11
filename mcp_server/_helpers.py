"""
Pure helper functions for the MCP server — no mcp SDK dependency.
Importable from the main project venv (Python 3.9) for testing.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Optional

import yaml


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
