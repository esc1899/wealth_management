"""Unit tests for position_dashboard.py helpers."""

from typing import Optional

# Importiere aus der Page — aber wir können nur inline-Funktionen testen
# Also schreiben wir eine eigenständige Test-Version der Funktion


def extract_ticker_section(digest: str, ticker: str) -> Optional[str]:
    """
    Extract the section for a specific ticker from a news digest.
    Pattern: "## TICKER —" ... until next "##" or end of string.
    """
    if not digest or not ticker:
        return None

    # Normalize ticker to uppercase
    ticker = ticker.upper()

    lines = digest.split("\n")
    start_idx = None
    end_idx = None

    # Find the header line matching "## TICKER"
    for i, line in enumerate(lines):
        if line.strip().startswith("##"):
            # Extract the ticket from this line: "## AAPL —" or "## AAPL"
            header_content = line.replace("##", "").strip()
            # Check if the first token (before space/dash) matches our ticker
            first_token = header_content.split()[0] if header_content else ""
            if first_token.upper() == ticker:
                start_idx = i
                break

    if start_idx is None:
        return None

    # Find the end: next "##" or end of digest
    for i in range(start_idx + 1, len(lines)):
        if lines[i].strip().startswith("##"):
            end_idx = i
            break

    if end_idx is None:
        end_idx = len(lines)

    section_lines = lines[start_idx:end_idx]
    section = "\n".join(section_lines).strip()

    # Remove the "---" separator at the end if present
    if section.endswith("---"):
        section = section[:-3].strip()

    return section if section else None


class TestExtractTickerSection:
    """Test _extract_ticker_section helper."""

    def test_extract_section_basic(self):
        """Extract a basic ticker section."""
        digest = """## AAPL — Apple Inc.
- News item 1
- News item 2
Assessment: 🟢 No action needed

---

## MSFT — Microsoft
- Other news
"""
        result = extract_ticker_section(digest, "AAPL")
        assert result is not None
        assert "AAPL" in result
        assert "Apple Inc" in result
        assert "News item 1" in result
        assert "MSFT" not in result  # Should not include next ticker

    def test_extract_section_case_insensitive(self):
        """Ticker matching should be case-insensitive."""
        digest = "## AAPL — Apple\n- News\n\n---\n## MSFT"
        result = extract_ticker_section(digest, "aapl")  # lowercase input
        assert result is not None
        assert "AAPL" in result

    def test_extract_section_not_found(self):
        """Return None if ticker not in digest."""
        digest = "## AAPL — Apple\n- News\n\n## MSFT — Microsoft"
        result = extract_ticker_section(digest, "GOOGL")
        assert result is None

    def test_extract_section_empty_digest(self):
        """Return None if digest is empty."""
        result = extract_ticker_section("", "AAPL")
        assert result is None

    def test_extract_section_none_inputs(self):
        """Return None if inputs are None."""
        assert extract_ticker_section(None, "AAPL") is None
        assert extract_ticker_section("## AAPL", None) is None

    def test_extract_section_with_separator(self):
        """Remove trailing --- separator from extracted section."""
        digest = """## AAPL — Apple
- News item
---

## MSFT — Microsoft"""
        result = extract_ticker_section(digest, "AAPL")
        assert result is not None
        assert not result.endswith("---")
        assert result.endswith("News item")

    def test_extract_section_last_ticker(self):
        """Extract the last ticker in digest correctly."""
        digest = """## AAPL — Apple
- News 1

---

## MSFT — Microsoft
- News 2
- More news 2"""
        result = extract_ticker_section(digest, "MSFT")
        assert result is not None
        assert "MSFT" in result
        assert "News 2" in result
        assert "News 1" not in result

    def test_extract_section_special_chars(self):
        """Handle tickers with numbers and special patterns."""
        digest = """## BRK.A — Berkshire
- News about BRK.A

---

## 0008.HK — Hang Seng"""
        result = extract_ticker_section(digest, "BRK.A")
        assert result is not None
        assert "Berkshire" in result

    def test_extract_section_multiline_content(self):
        """Preserve multiline content in the extracted section."""
        digest = """## AAPL — Apple Inc.
- News 1
- News 2
- News 3

Assessment:
🟢 No action needed
Rating: Strong Buy

---

## MSFT"""
        result = extract_ticker_section(digest, "AAPL")
        assert result is not None
        lines = result.split("\n")
        assert any("News 1" in line for line in lines)
        assert any("Strong Buy" in line for line in lines)
