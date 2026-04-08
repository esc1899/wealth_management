"""
Unit tests for ConsensusGapAgent._parse_verdicts.

This parser required multiple fix commits (and debug /tmp writes) because
Claude returns markdown-formatted output with bold labels, brackets, and
varied spacing that naive regex parsing couldn't handle.
"""
from unittest.mock import MagicMock

from agents.consensus_gap_agent import ConsensusGapAgent


def _make_agent() -> ConsensusGapAgent:
    return ConsensusGapAgent(llm=MagicMock())


class TestParseVerdicts:

    def test_standard_clean_format(self):
        text = (
            "POSITION: 3\n"
            "VERDICT: wächst\n"
            "SUMMARY: Market still underestimates the thesis.\n"
            "ANALYSIS:\nConsensus target is €100, actual is €140.\n"
            "---\n"
        )
        results = _make_agent()._parse_verdicts(text)
        assert len(results) == 1
        pos_id, verdict, summary, analysis = results[0]
        assert pos_id == "3"
        assert verdict == "wächst"
        assert "Market" in summary
        assert "100" in analysis

    def test_bold_markdown_labels(self):
        """Claude often wraps labels in **bold** — must still parse correctly."""
        text = (
            "**POSITION:** 7\n"
            "**VERDICT:** stabil\n"
            "**SUMMARY:** Thesis intact, no shift in consensus.\n"
            "**ANALYSIS:**\nStable rating across 12 analysts.\n"
            "---\n"
        )
        results = _make_agent()._parse_verdicts(text)
        assert len(results) == 1
        assert results[0][0] == "7"
        assert results[0][1] == "stabil"

    def test_verdict_in_brackets(self):
        """Claude sometimes returns [verdict] with surrounding brackets."""
        text = (
            "POSITION: 12\n"
            "VERDICT: [eingeholt]\n"
            "SUMMARY: Gap has closed, thesis fully priced in.\n"
            "ANALYSIS:\nAnalyst consensus now matches user thesis.\n"
            "---\n"
        )
        results = _make_agent()._parse_verdicts(text)
        assert len(results) == 1
        assert results[0][1] == "eingeholt"

    def test_verdict_case_insensitive(self):
        """Verdict label and value should survive mixed casing."""
        text = (
            "POSITION: 5\n"
            "verdict: Schließt\n"
            "SUMMARY: Market catching up to thesis.\n"
            "ANALYSIS:\nCoverage expanding, target converging.\n"
            "---\n"
        )
        results = _make_agent()._parse_verdicts(text)
        assert len(results) == 1
        assert results[0][1] == "schließt"

    def test_position_id_with_extra_text(self):
        """Claude often annotates IDs with ticker/name like '42 (AAPL - Apple Inc.)' — extract leading digits only."""
        text = (
            "POSITION: 42 (AAPL - Apple Inc.)\n"
            "VERDICT: wächst\n"
            "SUMMARY: Strong upside still ahead.\n"
            "ANALYSIS:\nWall St target lags fundamentals.\n"
            "---\n"
        )
        results = _make_agent()._parse_verdicts(text)
        assert len(results) == 1
        assert results[0][0] == "42"

    def test_multiple_blocks_parsed(self):
        """Two positions in one response, separated by ---."""
        text = (
            "POSITION: 1\n"
            "VERDICT: wächst\n"
            "SUMMARY: First position looks strong.\n"
            "ANALYSIS:\nGrowth thesis intact.\n"
            "---\n"
            "POSITION: 2\n"
            "VERDICT: eingeholt\n"
            "SUMMARY: Second position fully priced in.\n"
            "ANALYSIS:\nConsensus caught up.\n"
            "---\n"
        )
        results = _make_agent()._parse_verdicts(text)
        assert len(results) == 2
        assert {r[0] for r in results} == {"1", "2"}
        assert {r[1] for r in results} == {"wächst", "eingeholt"}

    def test_invalid_verdict_block_skipped(self):
        """Blocks with unrecognized verdict values are excluded."""
        text = (
            "POSITION: 9\n"
            "VERDICT: bullish\n"
            "SUMMARY: Something.\n"
            "ANALYSIS:\nN/A\n"
            "---\n"
        )
        assert _make_agent()._parse_verdicts(text) == []

    def test_missing_summary_block_skipped(self):
        """Blocks without SUMMARY are excluded — incomplete LLM output."""
        text = (
            "POSITION: 9\n"
            "VERDICT: stabil\n"
            "ANALYSIS:\nSome analysis.\n"
            "---\n"
        )
        assert _make_agent()._parse_verdicts(text) == []

    def test_empty_response_returns_empty_list(self):
        agent = _make_agent()
        assert agent._parse_verdicts("") == []
        assert agent._parse_verdicts("   \n  \n") == []

    def test_multiline_analysis_collected(self):
        """ANALYSIS can span multiple lines — all should be captured."""
        text = (
            "POSITION: 3\n"
            "VERDICT: stabil\n"
            "SUMMARY: Thesis holds.\n"
            "ANALYSIS:\n"
            "Line one of analysis.\n"
            "Line two of analysis.\n"
            "---\n"
        )
        results = _make_agent()._parse_verdicts(text)
        assert len(results) == 1
        _, _, _, analysis = results[0]
        assert "Line one" in analysis
        assert "Line two" in analysis

    def test_all_four_valid_verdicts_accepted(self):
        """Smoke-test: every valid verdict parses correctly."""
        verdicts = ["wächst", "stabil", "schließt", "eingeholt"]
        agent = _make_agent()
        for v in verdicts:
            text = (
                f"POSITION: 1\n"
                f"VERDICT: {v}\n"
                f"SUMMARY: Summary for {v}.\n"
                f"ANALYSIS:\nSome analysis.\n"
                f"---\n"
            )
            results = agent._parse_verdicts(text)
            assert len(results) == 1, f"Failed for verdict: {v}"
            assert results[0][1] == v

    def test_mixed_valid_and_invalid_blocks(self):
        """Only valid blocks are returned; invalid ones are silently dropped."""
        text = (
            "POSITION: 1\n"
            "VERDICT: wächst\n"
            "SUMMARY: Valid.\n"
            "ANALYSIS:\nOK.\n"
            "---\n"
            "POSITION: 2\n"
            "VERDICT: invalid_value\n"
            "SUMMARY: Invalid verdict.\n"
            "ANALYSIS:\nWill be dropped.\n"
            "---\n"
        )
        results = _make_agent()._parse_verdicts(text)
        assert len(results) == 1
        assert results[0][0] == "1"
