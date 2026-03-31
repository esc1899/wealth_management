"""
PositionsRepository — unified CRUD for the positions table.
Replaces PortfolioRepository + WatchlistRepository.

Encrypted fields: quantity, purchase_price, notes, extra_data.
All encryption/decryption is handled internally.
"""

import json
import sqlite3
from datetime import date
from typing import List, Optional

from core.encryption import EncryptionService
from core.storage.models import Position


class PositionsRepository:
    def __init__(self, conn: sqlite3.Connection, enc: EncryptionService):
        self._conn = conn
        self._enc = enc

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def add(self, position: Position) -> Position:
        cursor = self._conn.execute(
            """
            INSERT INTO positions (
                asset_class, investment_type,
                name, isin, wkn, ticker,
                quantity, unit, purchase_price, purchase_date,
                notes, extra_data,
                recommendation_source, strategy,
                added_date, in_portfolio,
                empfehlung, story
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._serialize(position),
        )
        self._conn.commit()
        return position.model_copy(update={"id": cursor.lastrowid})

    def get(self, position_id: int) -> Optional[Position]:
        row = self._conn.execute(
            "SELECT * FROM positions WHERE id = ?", (position_id,)
        ).fetchone()
        return self._deserialize(row) if row else None

    def get_all(self) -> List[Position]:
        rows = self._conn.execute("SELECT * FROM positions").fetchall()
        return [self._deserialize(r) for r in rows]

    def get_portfolio(self) -> List[Position]:
        rows = self._conn.execute(
            "SELECT * FROM positions WHERE in_portfolio = 1"
        ).fetchall()
        return [self._deserialize(r) for r in rows]

    def get_watchlist(self) -> List[Position]:
        rows = self._conn.execute(
            "SELECT * FROM positions WHERE in_portfolio = 0"
        ).fetchall()
        return [self._deserialize(r) for r in rows]

    def update(self, position: Position) -> bool:
        if position.id is None:
            raise ValueError("Position must have an id to update")
        cursor = self._conn.execute(
            """
            UPDATE positions SET
                asset_class=?, investment_type=?,
                name=?, isin=?, wkn=?, ticker=?,
                quantity=?, unit=?, purchase_price=?, purchase_date=?,
                notes=?, extra_data=?,
                recommendation_source=?, strategy=?,
                added_date=?, in_portfolio=?,
                empfehlung=?, story=?
            WHERE id=?
            """,
            self._serialize(position) + (position.id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def delete(self, position_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM positions WHERE id = ?", (position_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Domain operations
    # ------------------------------------------------------------------

    def promote_to_portfolio(
        self,
        position_id: int,
        quantity: float,
        purchase_price: Optional[float] = None,
        purchase_date: Optional[date] = None,
    ) -> Optional[Position]:
        """Move a watchlist entry into the portfolio."""
        position = self.get(position_id)
        if position is None:
            return None
        if position.in_portfolio:
            raise ValueError(f"Position {position_id} is already in the portfolio")
        updated = position.model_copy(update={
            "in_portfolio": True,
            "quantity": quantity,
            "purchase_price": purchase_price,
            "purchase_date": purchase_date or date.today(),
        })
        self.update(updated)
        return updated

    def get_by_ticker(self, ticker: str) -> List[Position]:
        rows = self._conn.execute(
            "SELECT * FROM positions WHERE UPPER(ticker) = ?", (ticker.upper(),)
        ).fetchall()
        return [self._deserialize(r) for r in rows]

    def get_tickers_for_price_fetch(self) -> List[str]:
        """Deduplicated non-null tickers from all positions."""
        rows = self._conn.execute(
            "SELECT DISTINCT UPPER(ticker) FROM positions WHERE ticker IS NOT NULL"
        ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def _serialize(self, p: Position) -> tuple:
        return (
            p.asset_class,
            p.investment_type,
            p.name,
            p.isin,
            p.wkn,
            p.ticker,
            self._enc.encrypt(str(p.quantity)) if p.quantity is not None else None,
            p.unit,
            self._enc.encrypt(str(p.purchase_price)) if p.purchase_price is not None else None,
            p.purchase_date.isoformat() if p.purchase_date else None,
            self._enc.encrypt(p.notes) if p.notes else None,
            self._enc.encrypt(json.dumps(p.extra_data)) if p.extra_data is not None else None,
            p.recommendation_source,
            p.strategy,
            p.added_date.isoformat(),
            1 if p.in_portfolio else 0,
            p.empfehlung,
            self._enc.encrypt(p.story) if p.story else None,
        )

    def _deserialize(self, row: sqlite3.Row) -> Position:
        keys = row.keys()
        return Position(
            id=row["id"],
            asset_class=row["asset_class"],
            investment_type=row["investment_type"],
            name=row["name"],
            isin=row["isin"],
            wkn=row["wkn"],
            ticker=row["ticker"],
            quantity=float(self._enc.decrypt(row["quantity"])) if row["quantity"] else None,
            unit=row["unit"],
            purchase_price=float(self._enc.decrypt(row["purchase_price"])) if row["purchase_price"] else None,
            purchase_date=date.fromisoformat(row["purchase_date"]) if row["purchase_date"] else None,
            notes=self._enc.decrypt(row["notes"]) if row["notes"] else None,
            extra_data=json.loads(self._enc.decrypt(row["extra_data"])) if row["extra_data"] else None,
            recommendation_source=row["recommendation_source"],
            strategy=row["strategy"],
            added_date=date.fromisoformat(row["added_date"]),
            in_portfolio=bool(row["in_portfolio"]),
            empfehlung=row["empfehlung"] if "empfehlung" in keys else None,
            story=self._enc.decrypt(row["story"]) if ("story" in keys and row["story"]) else None,
        )
