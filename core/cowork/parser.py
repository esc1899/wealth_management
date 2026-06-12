"""
Parser for Cowork Research Markdown files.

Each file contains a YAML frontmatter block (between --- delimiters) followed
by a free-text Markdown body. The parser validates required fields and enums,
returning structured domain objects or raising ParseError on invalid input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

import yaml


# ---------------------------------------------------------------------------
# Allowed enum values
# ---------------------------------------------------------------------------

VALID_TYPES = {"stock_analysis", "sector_scan", "watchlist_scan"}
VALID_STATUSES = {"draft", "ready_for_import", "imported", "failed"}
VALID_SENTIMENTS = {"positive", "neutral", "negative"}
VALID_CONFIDENCES = {"low", "medium", "high"}
VALID_CONVICTIONS = {"low", "medium", "high"}
VALID_ACTIONS = {"add", "watch", "skip"}


class ParseError(Exception):
    """Raised when a research file cannot be parsed or fails validation."""


# ---------------------------------------------------------------------------
# Domain objects (plain dataclasses — no DB concerns here)
# ---------------------------------------------------------------------------

@dataclass
class CandidatePrimary:
    ticker: str
    name: str
    exchange: str
    sentiment: Optional[str] = None
    confidence: Optional[str] = None


@dataclass
class WatchlistCandidate:
    ticker: str
    name: str
    exchange: str
    rationale: str
    conviction: str
    suggested_action: str
    isin: Optional[str] = None
    category: Optional[str] = None
    price_at_research: Optional[float] = None
    currency: Optional[str] = None
    target_price: Optional[float] = None
    triggers: List[str] = field(default_factory=list)


@dataclass
class ParsedResearch:
    research_id: str
    type: str
    date: date
    ai_generated: bool
    model: str
    status: str
    primary: Optional[CandidatePrimary]
    watchlist_candidates: List[WatchlistCandidate]
    sources: List[str]
    disclaimer: str
    body_markdown: str
    request_id: Optional[int] = None  # auslösende Anfrage aus research_requests


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_research_file(path: str) -> ParsedResearch:
    """Read and parse a .md research file. Raises ParseError on any problem."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError as exc:
        raise ParseError(f"Cannot read file {path}: {exc}") from exc

    return parse_research_string(raw, source_path=path)


def parse_research_string(text: str, source_path: str = "<string>") -> ParsedResearch:
    """Parse raw markdown text. `source_path` is used only for error messages."""
    frontmatter_raw, body = _split_frontmatter(text, source_path)
    data = _load_yaml(frontmatter_raw, source_path)
    return _validate_and_build(data, body, source_path)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)", re.DOTALL)


def _split_frontmatter(text: str, path: str):
    m = _FM_PATTERN.match(text)
    if not m:
        raise ParseError(
            f"{path}: No valid YAML frontmatter found. "
            "File must start with --- and contain a closing ---."
        )
    return m.group(1), m.group(2).strip()


def _load_yaml(raw: str, path: str) -> dict:
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ParseError(f"{path}: YAML parse error — {exc}") from exc
    if not isinstance(data, dict):
        raise ParseError(f"{path}: Frontmatter must be a YAML mapping, got {type(data).__name__}")
    return data


def _require(data: dict, field_name: str, path: str):
    val = data.get(field_name)
    if val is None or (isinstance(val, str) and not val.strip()):
        raise ParseError(f"{path}: Missing required field '{field_name}'")
    return val


def _validate_enum(value: str, valid: set, field_name: str, path: str) -> str:
    if value not in valid:
        raise ParseError(
            f"{path}: Invalid value '{value}' for '{field_name}'. "
            f"Allowed: {sorted(valid)}"
        )
    return value


def _parse_primary(data: dict, path: str) -> Optional[CandidatePrimary]:
    raw = data.get("primary")
    if not raw:
        return None
    if not isinstance(raw, dict):
        raise ParseError(f"{path}: 'primary' must be a mapping")
    ticker = _require(raw, "ticker", path)
    name = _require(raw, "name", path)
    exchange = _require(raw, "exchange", path)
    sentiment = raw.get("sentiment")
    if sentiment:
        _validate_enum(sentiment, VALID_SENTIMENTS, "primary.sentiment", path)
    confidence = raw.get("confidence")
    if confidence:
        _validate_enum(confidence, VALID_CONFIDENCES, "primary.confidence", path)
    return CandidatePrimary(
        ticker=str(ticker).strip().upper(),
        name=str(name).strip(),
        exchange=str(exchange).strip().upper(),
        sentiment=sentiment,
        confidence=confidence,
    )


def _parse_candidates(data: dict, path: str) -> List[WatchlistCandidate]:
    raw_list = data.get("watchlist_candidates")
    if raw_list is None:
        raise ParseError(f"{path}: Missing required field 'watchlist_candidates' (use [] for empty)")
    if not isinstance(raw_list, list):
        raise ParseError(f"{path}: 'watchlist_candidates' must be a list")
    result = []
    for i, raw in enumerate(raw_list):
        prefix = f"{path}: watchlist_candidates[{i}]"
        if not isinstance(raw, dict):
            raise ParseError(f"{prefix}: each candidate must be a mapping")
        ticker = _require(raw, "ticker", prefix)
        name = _require(raw, "name", prefix)
        exchange = _require(raw, "exchange", prefix)
        rationale = _require(raw, "rationale", prefix)
        conviction = _validate_enum(
            _require(raw, "conviction", prefix), VALID_CONVICTIONS, "conviction", prefix
        )
        suggested_action = _validate_enum(
            _require(raw, "suggested_action", prefix), VALID_ACTIONS, "suggested_action", prefix
        )
        price = raw.get("price_at_research")
        if price is not None:
            try:
                price = float(price)
            except (TypeError, ValueError):
                raise ParseError(f"{prefix}: 'price_at_research' must be a number")
        target = raw.get("target_price")
        if target is not None:
            try:
                target = float(target)
            except (TypeError, ValueError):
                raise ParseError(f"{prefix}: 'target_price' must be a number")
        triggers = raw.get("triggers") or []
        if not isinstance(triggers, list):
            raise ParseError(f"{prefix}: 'triggers' must be a list")
        result.append(WatchlistCandidate(
            ticker=str(ticker).strip().upper(),
            name=str(name).strip(),
            exchange=str(exchange).strip().upper(),
            rationale=str(rationale).strip(),
            conviction=conviction,
            suggested_action=suggested_action,
            isin=raw.get("isin"),
            category=raw.get("category"),
            price_at_research=price,
            currency=raw.get("currency"),
            target_price=target,
            triggers=[str(t) for t in triggers],
        ))
    return result


def _validate_and_build(data: dict, body: str, path: str) -> ParsedResearch:
    research_id = _require(data, "research_id", path)
    rtype = _validate_enum(
        str(_require(data, "type", path)), VALID_TYPES, "type", path
    )
    raw_date = _require(data, "date", path)
    if isinstance(raw_date, date):
        parsed_date = raw_date
    else:
        try:
            parsed_date = date.fromisoformat(str(raw_date))
        except ValueError:
            raise ParseError(f"{path}: 'date' must be YYYY-MM-DD, got '{raw_date}'")
    status = _validate_enum(
        str(_require(data, "status", path)), VALID_STATUSES, "status", path
    )
    model = _require(data, "model", path)
    disclaimer = _require(data, "disclaimer", path)
    sources = data.get("sources") or []
    if not isinstance(sources, list):
        raise ParseError(f"{path}: 'sources' must be a list")
    ai_generated = bool(data.get("ai_generated", True))

    request_id = data.get("request_id")
    if request_id is not None:
        try:
            request_id = int(request_id)
        except (TypeError, ValueError):
            raise ParseError(f"{path}: 'request_id' must be an integer, got '{request_id}'")
        if request_id < 1:
            raise ParseError(f"{path}: 'request_id' must be a positive integer")

    primary = _parse_primary(data, path)
    candidates = _parse_candidates(data, path)

    return ParsedResearch(
        research_id=str(research_id).strip(),
        type=rtype,
        date=parsed_date,
        ai_generated=ai_generated,
        model=str(model).strip(),
        status=status,
        primary=primary,
        watchlist_candidates=candidates,
        sources=[str(s) for s in sources],
        disclaimer=str(disclaimer).strip(),
        body_markdown=body,
        request_id=request_id,
    )
