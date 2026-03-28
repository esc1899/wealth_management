"""
Unit tests for Agentmonitor data-processing helpers.
No Streamlit, no Langfuse connection required.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from monitoring.agentmonitor_helpers import build_generation_rows, highlight_status


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def make_generation(
    name="portfolio_agent",
    model="qwen3:8b",
    level="DEFAULT",
    start_offset_s=0,
    duration_s=5.0,
    input_tokens=100,
    output_tokens=50,
    gen_input=None,
    gen_output="result text",
    no_end_time=False,
    usage=True,
):
    start = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(seconds=start_offset_s)
    end = None if no_end_time else start + timedelta(seconds=duration_s)

    g = MagicMock()
    g.name = name
    g.model = model
    g.level = level
    g.start_time = start
    g.end_time = end
    g.input = gen_input or [{"role": "user", "content": "Hallo"}]
    g.output = gen_output

    if usage:
        g.usage = MagicMock()
        g.usage.input = input_tokens
        g.usage.output = output_tokens
    else:
        g.usage = None

    return g


# ------------------------------------------------------------------
# build_generation_rows
# ------------------------------------------------------------------

class TestBuildGenerationRows:
    def test_empty_list_returns_empty(self):
        assert build_generation_rows([]) == []

    def test_single_generation_fields(self):
        g = make_generation(name="test", model="qwen3:8b", level="DEFAULT", duration_s=3.0,
                            input_tokens=10, output_tokens=20, gen_output="ok")
        rows = build_generation_rows([g])
        assert len(rows) == 1
        row = rows[0]
        assert row["Name"] == "test"
        assert row["Modell"] == "qwen3:8b"
        assert row["Status"] == "DEFAULT"
        assert row["Dauer (ms)"] == 3000
        assert row["In-Tokens"] == 10
        assert row["Out-Tokens"] == 20
        assert row["_output"] == "ok"

    def test_duration_calculated_correctly(self):
        g = make_generation(duration_s=2.5)
        row = build_generation_rows([g])[0]
        assert row["Dauer (ms)"] == 2500

    def test_missing_end_time_gives_none_duration(self):
        g = make_generation(no_end_time=True)
        row = build_generation_rows([g])[0]
        assert row["Dauer (ms)"] is None

    def test_missing_start_time_gives_placeholder(self):
        g = make_generation()
        g.start_time = None
        g.end_time = None
        row = build_generation_rows([g])[0]
        assert row["Zeit"] == "—"
        assert row["Dauer (ms)"] is None

    def test_no_usage_gives_none_tokens(self):
        g = make_generation(usage=False)
        row = build_generation_rows([g])[0]
        assert row["In-Tokens"] is None
        assert row["Out-Tokens"] is None

    def test_none_name_uses_placeholder(self):
        g = make_generation(name=None)
        row = build_generation_rows([g])[0]
        assert row["Name"] == "—"

    def test_none_model_uses_placeholder(self):
        g = make_generation(model=None)
        row = build_generation_rows([g])[0]
        assert row["Modell"] == "—"

    def test_none_level_defaults_to_default(self):
        g = make_generation(level=None)
        row = build_generation_rows([g])[0]
        assert row["Status"] == "DEFAULT"

    def test_error_level_preserved(self):
        g = make_generation(level="ERROR")
        row = build_generation_rows([g])[0]
        assert row["Status"] == "ERROR"

    def test_multiple_generations_preserves_order(self):
        g1 = make_generation(name="first", start_offset_s=0)
        g2 = make_generation(name="second", start_offset_s=10)
        rows = build_generation_rows([g1, g2])
        assert rows[0]["Name"] == "first"
        assert rows[1]["Name"] == "second"

    def test_input_and_output_stored_raw(self):
        payload = [{"role": "user", "content": "Test"}]
        g = make_generation(gen_input=payload, gen_output="answer")
        row = build_generation_rows([g])[0]
        assert row["_input"] == payload
        assert row["_output"] == "answer"

    def test_zeit_format(self):
        g = make_generation()
        row = build_generation_rows([g])[0]
        # Should be DD.MM HH:MM:SS format
        import re
        assert re.match(r"\d{2}\.\d{2} \d{2}:\d{2}:\d{2}", row["Zeit"])

    def test_duration_rounded_to_int(self):
        g = make_generation(duration_s=1.5678)
        row = build_generation_rows([g])[0]
        assert isinstance(row["Dauer (ms)"], int)
        assert row["Dauer (ms)"] == 1568


# ------------------------------------------------------------------
# highlight_status
# ------------------------------------------------------------------

class TestHighlightStatus:
    def test_error_returns_red(self):
        assert highlight_status("ERROR") == "background-color: #ffcccc"

    def test_warning_returns_yellow(self):
        assert highlight_status("WARNING") == "background-color: #fff3cc"

    def test_default_returns_empty(self):
        assert highlight_status("DEFAULT") == ""

    def test_unknown_status_returns_empty(self):
        assert highlight_status("INFO") == ""
        assert highlight_status("") == ""
