"""
Cowork Research Ingest — storage layer.

Tables:
  cowork_research_entries   — one row per imported .md file
  cowork_watchlist_suggestions — candidates extracted from a research entry
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import List, Optional


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

@dataclass
class ResearchEntry:
    research_id: str
    type: str
    date: date
    model: str
    status: str
    body_markdown: str
    sources: List[str]
    disclaimer: str
    id: Optional[int] = None
    primary_ticker: Optional[str] = None
    primary_name: Optional[str] = None
    primary_exchange: Optional[str] = None
    primary_sentiment: Optional[str] = None
    primary_confidence: Optional[str] = None
    file_path: Optional[str] = None
    imported_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass
class WatchlistSuggestion:
    research_id: str
    ticker: str
    exchange: str
    name: str
    rationale: str
    conviction: str
    suggested_action: str
    status: str  # pending | accepted | rejected | imported
    id: Optional[int] = None
    isin: Optional[str] = None
    category: Optional[str] = None
    price_at_research: Optional[float] = None
    currency: Optional[str] = None
    target_price: Optional[float] = None
    triggers: List[str] = field(default_factory=list)
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class CoworkRepository:

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # ------------------------------------------------------------------
    # ResearchEntry
    # ------------------------------------------------------------------

    def create_entry(
        self,
        research_id: str,
        type: str,
        date: date,
        model: str,
        status: str,
        body_markdown: str,
        sources: List[str],
        disclaimer: str,
        primary_ticker: Optional[str] = None,
        primary_name: Optional[str] = None,
        primary_exchange: Optional[str] = None,
        primary_sentiment: Optional[str] = None,
        primary_confidence: Optional[str] = None,
        file_path: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> ResearchEntry:
        now = datetime.now(timezone.utc)
        imported_at = now if status == "imported" else None
        cur = self._conn.execute(
            """
            INSERT INTO cowork_research_entries (
                research_id, type, date, model, status,
                primary_ticker, primary_name, primary_exchange,
                primary_sentiment, primary_confidence,
                body_markdown, sources, disclaimer,
                file_path, imported_at, failure_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                research_id, type, date.isoformat(), model, status,
                primary_ticker, primary_name, primary_exchange,
                primary_sentiment, primary_confidence,
                body_markdown, json.dumps(sources), disclaimer,
                file_path,
                imported_at.isoformat() if imported_at else None,
                failure_reason,
                now.isoformat(),
            ),
        )
        self._conn.commit()
        return ResearchEntry(
            id=cur.lastrowid,
            research_id=research_id,
            type=type,
            date=date,
            model=model,
            status=status,
            primary_ticker=primary_ticker,
            primary_name=primary_name,
            primary_exchange=primary_exchange,
            primary_sentiment=primary_sentiment,
            primary_confidence=primary_confidence,
            body_markdown=body_markdown,
            sources=sources,
            disclaimer=disclaimer,
            file_path=file_path,
            imported_at=imported_at,
            failure_reason=failure_reason,
            created_at=now,
        )

    def get_by_research_id(self, research_id: str) -> Optional[ResearchEntry]:
        row = self._conn.execute(
            "SELECT * FROM cowork_research_entries WHERE research_id = ?",
            (research_id,),
        ).fetchone()
        return self._row_to_entry(row) if row else None

    def get_entry(self, entry_id: int) -> Optional[ResearchEntry]:
        row = self._conn.execute(
            "SELECT * FROM cowork_research_entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
        return self._row_to_entry(row) if row else None

    def list_entries(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[ResearchEntry]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM cowork_research_entries WHERE status = ? ORDER BY date DESC, created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM cowork_research_entries ORDER BY date DESC, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def update_status(self, entry_id: int, new_status: str) -> None:
        imported_at = None
        if new_status == "imported":
            imported_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE cowork_research_entries SET status = ?, imported_at = COALESCE(?, imported_at) WHERE id = ?",
            (new_status, imported_at, entry_id),
        )
        self._conn.commit()

    def update_status_by_research_id(self, research_id: str, new_status: str) -> None:
        entry = self.get_by_research_id(research_id)
        if entry and entry.id:
            self.update_status(entry.id, new_status)

    # ------------------------------------------------------------------
    # WatchlistSuggestion
    # ------------------------------------------------------------------

    def create_suggestion(
        self,
        research_id: str,
        ticker: str,
        exchange: str,
        name: str,
        rationale: str,
        conviction: str,
        suggested_action: str,
        isin: Optional[str] = None,
        category: Optional[str] = None,
        price_at_research: Optional[float] = None,
        currency: Optional[str] = None,
        target_price: Optional[float] = None,
        triggers: Optional[List[str]] = None,
        status: str = "pending",
    ) -> WatchlistSuggestion:
        now = datetime.now(timezone.utc)
        cur = self._conn.execute(
            """
            INSERT INTO cowork_watchlist_suggestions (
                research_id, ticker, exchange, name, isin, category,
                rationale, conviction, suggested_action,
                price_at_research, currency, target_price, triggers,
                status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                research_id, ticker.upper(), exchange.upper(), name,
                isin, category, rationale, conviction, suggested_action,
                price_at_research, currency, target_price,
                json.dumps(triggers or []),
                status, now.isoformat(),
            ),
        )
        self._conn.commit()
        return WatchlistSuggestion(
            id=cur.lastrowid,
            research_id=research_id,
            ticker=ticker.upper(),
            exchange=exchange.upper(),
            name=name,
            isin=isin,
            category=category,
            rationale=rationale,
            conviction=conviction,
            suggested_action=suggested_action,
            price_at_research=price_at_research,
            currency=currency,
            target_price=target_price,
            triggers=triggers or [],
            status=status,
            created_at=now,
        )

    def list_suggestions(
        self,
        research_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 200,
    ) -> List[WatchlistSuggestion]:
        clauses = []
        params = []
        if research_id:
            clauses.append("research_id = ?")
            params.append(research_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM cowork_watchlist_suggestions {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [self._row_to_suggestion(r) for r in rows]

    def get_suggestion(self, suggestion_id: int) -> Optional[WatchlistSuggestion]:
        row = self._conn.execute(
            "SELECT * FROM cowork_watchlist_suggestions WHERE id = ?",
            (suggestion_id,),
        ).fetchone()
        return self._row_to_suggestion(row) if row else None

    def update_suggestion_status(
        self,
        suggestion_id: int,
        new_status: str,
        reviewed_by: Optional[str] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE cowork_watchlist_suggestions
            SET status = ?, reviewed_at = ?, reviewed_by = ?
            WHERE id = ?
            """,
            (new_status, now, reviewed_by, suggestion_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _row_to_entry(self, row) -> ResearchEntry:
        d = dict(row)
        return ResearchEntry(
            id=d["id"],
            research_id=d["research_id"],
            type=d["type"],
            date=date.fromisoformat(d["date"]),
            model=d["model"],
            status=d["status"],
            primary_ticker=d.get("primary_ticker"),
            primary_name=d.get("primary_name"),
            primary_exchange=d.get("primary_exchange"),
            primary_sentiment=d.get("primary_sentiment"),
            primary_confidence=d.get("primary_confidence"),
            body_markdown=d.get("body_markdown") or "",
            sources=json.loads(d.get("sources") or "[]"),
            disclaimer=d.get("disclaimer") or "",
            file_path=d.get("file_path"),
            imported_at=datetime.fromisoformat(d["imported_at"]) if d.get("imported_at") else None,
            failure_reason=d.get("failure_reason"),
            created_at=datetime.fromisoformat(d["created_at"]) if d.get("created_at") else None,
        )

    def _row_to_suggestion(self, row) -> WatchlistSuggestion:
        d = dict(row)
        return WatchlistSuggestion(
            id=d["id"],
            research_id=d["research_id"],
            ticker=d["ticker"],
            exchange=d["exchange"],
            name=d["name"],
            isin=d.get("isin"),
            category=d.get("category"),
            rationale=d.get("rationale") or "",
            conviction=d.get("conviction") or "",
            suggested_action=d.get("suggested_action") or "",
            price_at_research=d.get("price_at_research"),
            currency=d.get("currency"),
            target_price=d.get("target_price"),
            triggers=json.loads(d.get("triggers") or "[]"),
            status=d.get("status") or "pending",
            reviewed_at=datetime.fromisoformat(d["reviewed_at"]) if d.get("reviewed_at") else None,
            reviewed_by=d.get("reviewed_by"),
            created_at=datetime.fromisoformat(d["created_at"]) if d.get("created_at") else None,
        )
