"""
Research Queue — storage layer.

Tables:
  research_requests  — open/done research tasks (App → Claude)
  research_answers   — answers submitted via MCP (Claude → App)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

VALID_REQUEST_TYPES = {"watchlist_candidate", "research_question", "analysis_deepdive", "general"}
VALID_SOURCES = {"manual", "agent", "batch"}
VALID_STATUSES = {"open", "in_progress", "done"}

# SEC-5 (e): Limits müssen mit mcp_server/_helpers.py synchron bleiben
# (zweiter Schreibpfad via MCP-Server, Raw-SQL — Test erzwingt Gleichstand).
MAX_TICKER_LEN = 20
MAX_ANSWER_BYTES = 100_000


@dataclass
class ResearchRequest:
    id: int
    request_type: str
    ticker: Optional[str]
    focus: str
    context: Optional[str]
    source: str
    status: str
    created_at: str
    updated_at: str


@dataclass
class ResearchAnswer:
    id: int
    request_id: Optional[int]
    ticker: Optional[str]
    answer_md: str
    created_at: str


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class ResearchQueueRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Requests
    # ------------------------------------------------------------------

    def create_request(
        self,
        focus: str,
        *,
        request_type: str = "research_question",
        ticker: Optional[str] = None,
        context: Optional[str] = None,
        source: str = "manual",
    ) -> ResearchRequest:
        if request_type not in VALID_REQUEST_TYPES:
            raise ValueError(f"Invalid request_type: {request_type}")
        if source not in VALID_SOURCES:
            raise ValueError(f"Invalid source: {source}")
        if len(focus) > 500:
            raise ValueError("focus exceeds 500 characters")
        if context and len(context) > 2000:
            raise ValueError("context exceeds 2000 characters")
        if ticker and len(ticker) > MAX_TICKER_LEN:
            raise ValueError(f"ticker exceeds {MAX_TICKER_LEN} characters")
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            """INSERT INTO research_requests
               (request_type, ticker, focus, context, source, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?, ?)""",
            (request_type, ticker, focus, context, source, now, now),
        )
        self._conn.commit()
        return self.get_request(cur.lastrowid)  # type: ignore[arg-type]

    def get_request(self, request_id: int) -> Optional[ResearchRequest]:
        row = self._conn.execute(
            "SELECT id, request_type, ticker, focus, context, source, status, created_at, updated_at "
            "FROM research_requests WHERE id = ?",
            (request_id,),
        ).fetchone()
        return _row_to_request(row) if row else None

    def list_open_requests(self) -> List[ResearchRequest]:
        rows = self._conn.execute(
            "SELECT id, request_type, ticker, focus, context, source, status, created_at, updated_at "
            "FROM research_requests WHERE status = 'open' ORDER BY created_at ASC"
        ).fetchall()
        return [_row_to_request(r) for r in rows]

    def list_all_requests(self) -> List[ResearchRequest]:
        rows = self._conn.execute(
            "SELECT id, request_type, ticker, focus, context, source, status, created_at, updated_at "
            "FROM research_requests ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_request(r) for r in rows]

    def complete_request(self, request_id: int) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "UPDATE research_requests SET status = 'done', updated_at = ? WHERE id = ? AND status != 'done'",
            (now, request_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete_request(self, request_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM research_requests WHERE id = ?", (request_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Answers
    # ------------------------------------------------------------------

    def submit_answer(
        self,
        answer_md: str,
        *,
        request_id: Optional[int] = None,
        ticker: Optional[str] = None,
    ) -> ResearchAnswer:
        if not answer_md.strip():
            raise ValueError("answer_md must not be empty")
        if len(answer_md.encode()) > MAX_ANSWER_BYTES:
            raise ValueError("answer_md exceeds 100 KB limit")
        if ticker and len(ticker) > MAX_TICKER_LEN:
            raise ValueError(f"ticker exceeds {MAX_TICKER_LEN} characters")
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "INSERT INTO research_answers (request_id, ticker, answer_md, created_at) VALUES (?, ?, ?, ?)",
            (request_id, ticker, answer_md, now),
        )
        self._conn.commit()
        return self.get_answer(cur.lastrowid)  # type: ignore[arg-type]

    def get_answer(self, answer_id: int) -> Optional[ResearchAnswer]:
        row = self._conn.execute(
            "SELECT id, request_id, ticker, answer_md, created_at FROM research_answers WHERE id = ?",
            (answer_id,),
        ).fetchone()
        return _row_to_answer(row) if row else None

    def list_answers(self, ticker: Optional[str] = None) -> List[ResearchAnswer]:
        if ticker:
            rows = self._conn.execute(
                "SELECT id, request_id, ticker, answer_md, created_at "
                "FROM research_answers WHERE ticker = ? ORDER BY created_at DESC",
                (ticker,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, request_id, ticker, answer_md, created_at "
                "FROM research_answers ORDER BY created_at DESC"
            ).fetchall()
        return [_row_to_answer(r) for r in rows]

    def delete_answer(self, answer_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM research_answers WHERE id = ?", (answer_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row_to_request(row) -> ResearchRequest:
    return ResearchRequest(
        id=row[0],
        request_type=row[1],
        ticker=row[2],
        focus=row[3],
        context=row[4],
        source=row[5],
        status=row[6],
        created_at=row[7],
        updated_at=row[8],
    )


def _row_to_answer(row) -> ResearchAnswer:
    return ResearchAnswer(
        id=row[0],
        request_id=row[1],
        ticker=row[2],
        answer_md=row[3],
        created_at=row[4],
    )
