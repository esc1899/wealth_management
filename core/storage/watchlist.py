"""
Watchlist storage: encrypted CRUD operations.
"""

import sqlite3
from datetime import date
from typing import Optional
from core.encryption import EncryptionService
from core.storage.models import AssetType, WatchlistEntry, WatchlistSource


class WatchlistRepository:
    def __init__(self, conn: sqlite3.Connection, enc: EncryptionService):
        self._conn = conn
        self._enc = enc

    def add(self, entry: WatchlistEntry) -> WatchlistEntry:
        cursor = self._conn.execute(
            """
            INSERT INTO watchlist
                (symbol, name, notes, target_price, added_date, source, asset_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.symbol,
                entry.name,
                self._enc.encrypt(entry.notes) if entry.notes else None,
                self._enc.encrypt(str(entry.target_price)) if entry.target_price else None,
                entry.added_date.isoformat(),
                entry.source.value,
                entry.asset_type.value,
            ),
        )
        self._conn.commit()
        return entry.model_copy(update={"id": cursor.lastrowid})

    def get_all(self) -> list[WatchlistEntry]:
        rows = self._conn.execute("SELECT * FROM watchlist").fetchall()
        return [self._deserialize(row) for row in rows]

    def get_by_source(self, source: WatchlistSource) -> list[WatchlistEntry]:
        rows = self._conn.execute(
            "SELECT * FROM watchlist WHERE source = ?", (source.value,)
        ).fetchall()
        return [self._deserialize(row) for row in rows]

    def get_by_symbol(self, symbol: str) -> list[WatchlistEntry]:
        rows = self._conn.execute(
            "SELECT * FROM watchlist WHERE symbol = ?", (symbol.upper(),)
        ).fetchall()
        return [self._deserialize(row) for row in rows]

    def delete(self, entry_id: int) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM watchlist WHERE id = ?", (entry_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def _deserialize(self, row: sqlite3.Row) -> WatchlistEntry:
        return WatchlistEntry(
            id=row["id"],
            symbol=row["symbol"],
            name=row["name"],
            notes=self._enc.decrypt(row["notes"]) if row["notes"] else None,
            target_price=float(self._enc.decrypt(row["target_price"])) if row["target_price"] else None,
            added_date=date.fromisoformat(row["added_date"]),
            source=WatchlistSource(row["source"]),
            asset_type=AssetType(row["asset_type"]),
        )
