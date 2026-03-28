"""
Pure-Python helpers for the Agentmonitor page.
Extracted so they can be unit-tested without importing Streamlit.
"""

from __future__ import annotations

from typing import Any, Optional


def build_generation_rows(generations: list) -> list[dict]:
    """Convert a list of Langfuse generation objects into plain dicts for the DataFrame."""
    rows = []
    for g in generations:
        start = g.start_time
        end = g.end_time

        if start and end:
            duration_ms = (end - start).total_seconds() * 1000
        else:
            duration_ms = None

        input_tokens = None
        output_tokens = None
        if g.usage:
            input_tokens = getattr(g.usage, "input", None)
            output_tokens = getattr(g.usage, "output", None)

        rows.append({
            "Zeit": start.astimezone().strftime("%d.%m %H:%M:%S") if start else "—",
            "Name": g.name or "—",
            "Modell": g.model or "—",
            "Dauer (ms)": round(duration_ms) if duration_ms is not None else None,
            "Status": g.level or "DEFAULT",
            "In-Tokens": input_tokens,
            "Out-Tokens": output_tokens,
            "_output": g.output,
            "_input": g.input,
        })
    return rows


def highlight_status(val: str) -> str:
    if val == "ERROR":
        return "background-color: #ffcccc"
    if val == "WARNING":
        return "background-color: #fff3cc"
    return ""
