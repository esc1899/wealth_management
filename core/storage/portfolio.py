"""
Portfolio storage: encrypted CRUD operations.
Sensitive fields (quantity, purchase_price) are encrypted at rest.
"""

import sqlite3
from datetime import date
from typing import Optional
from core.encryption import EncryptionService
from core.storage.models import AssetType, PortfolioEntry


class PortfolioRepository:
    def __init__(self, conn: sqlite3.Connection, enc: EncryptionService):
        self._conn = conn
        self._enc = enc

    def add(self, entry: PortfolioEntry) -> PortfolioEntry:
        cursor = self._conn.execute(
            """
            INSERT INTO portfolio
                (symbol, name, quantity, purchase_price, purchase_date, asset_type, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.symbol,
                entry.name,
                self._enc.encrypt(str(entry.quantity)),
                self._enc.encrypt(str(entry.purchase_price)) if entry.purchase_price is not None else None,
                entry.purchase_date.isoformat(),
                entry.asset_type.value,
                self._enc.encrypt(entry.notes) if entry.notes else None,
            ),
        )
        self._conn.commit()
        return entry.model_copy(update={"id": cursor.lastrowid})

    def get_all(self) -> list[PortfolioEntry]:
        rows = self._conn.execute("SELECT * FROM portfolio").fetchall()
        return [self._deserialize(row) for row in rows]

    def get_by_symbol(self, symbol: str) -> list[PortfolioEntry]:
        rows = self._conn.execute(
            "SELECT * FROM portfolio WHERE symbol = ?", (symbol.upper(),)
        ).fetchall()
        return [self._deserialize(row) for row in rows]

    def delete(self, entry_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM portfolio WHERE id = ?", (entry_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def update(self, entry: PortfolioEntry) -> bool:
        if entry.id is None:
            raise ValueError("Entry must have an id to update")
        cursor = self._conn.execute(
            """
            UPDATE portfolio
            SET symbol=?, name=?, quantity=?, purchase_price=?,
                purchase_date=?, asset_type=?, notes=?
            WHERE id=?
            """,
            (
                entry.symbol,
                entry.name,
                self._enc.encrypt(str(entry.quantity)),
                self._enc.encrypt(str(entry.purchase_price)) if entry.purchase_price is not None else None,
                entry.purchase_date.isoformat(),
                entry.asset_type.value,
                self._enc.encrypt(entry.notes) if entry.notes else None,
                entry.id,
            ),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def _deserialize(self, row: sqlite3.Row) -> PortfolioEntry:
        return PortfolioEntry(
            id=row["id"],
            symbol=row["symbol"],
            name=row["name"],
            quantity=float(self._enc.decrypt(row["quantity"])),
            purchase_price=float(self._enc.decrypt(row["purchase_price"])) if row["purchase_price"] else None,
            purchase_date=date.fromisoformat(row["purchase_date"]),
            asset_type=AssetType(row["asset_type"]),
            notes=self._enc.decrypt(row["notes"]) if row["notes"] else None,
        )
