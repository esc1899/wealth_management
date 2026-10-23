"""
Research answers — storage layer.

Table research_answers: answers submitted via MCP (Claude → App), shown on the title page
of their ticker. The table research_requests (App → Claude) stays in existing databases but
has no reader or writer since 2026-10-23 (CHANGELOG).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

# SEC-5 (e): Limits müssen mit mcp_server/_helpers.py synchron bleiben
# (zweiter Schreibpfad via MCP-Server, Raw-SQL — Test erzwingt Gleichstand).
MAX_TICKER_LEN = 20
MAX_ANSWER_BYTES = 100_000


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

    def submit_answer(
        self,
        answer_md: str,
        *,
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
            (None, ticker, answer_md, now),
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

    @staticmethod
    def _base_symbol(ticker: str) -> str:
        """Ticker ohne Börsensuffix: 'SAP.DE' → 'SAP', 'NOVO-B.CO' → 'NOVO-B'."""
        return ticker.split(".")[0].upper()

    def list_answers_for_ticker(self, ticker: str) -> List[ResearchAnswer]:
        """Antworten zum Ticker — matcht auch Suffix-Varianten (SAP ↔ SAP.DE).

        Der Co-Pilot kennt die yfinance-Notation mit Börsensuffix nicht und
        liefert meist das nackte Symbol; exakter Vergleich würde diese
        Antworten verlieren.
        """
        base = self._base_symbol(ticker)
        return [
            a for a in self.list_answers()
            if a.ticker and self._base_symbol(a.ticker) == base
        ]

    def delete_answer(self, answer_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM research_answers WHERE id = ?", (answer_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _row_to_answer(row) -> ResearchAnswer:
    return ResearchAnswer(
        id=row[0],
        request_id=row[1],
        ticker=row[2],
        answer_md=row[3],
        created_at=row[4],
    )
