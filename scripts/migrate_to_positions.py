"""
Migration: portfolio + watchlist → positions table.

Usage:
    python scripts/migrate_to_positions.py [--confirm]

Without --confirm the script runs in dry-run mode (no DB changes).
With --confirm the migration is executed and validated.

The old tables are NOT dropped — they remain as backup until manually removed.
"""

import argparse
import json
import shutil
import sqlite3
import sys
import os
from datetime import date, datetime

# Make sure project root is in path when running as a script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from core.encryption import EncryptionService, load_or_create_salt
from core.storage.base import init_db

# ---------------------------------------------------------------------------
# Asset type mapping: old enum value → new asset_class + investment_type
# ---------------------------------------------------------------------------
ASSET_TYPE_MAP = {
    "stock":  ("Aktie",          "Wertpapiere"),
    "etf":    ("Aktienfonds",    "Wertpapiere"),
    "crypto": ("Aktie",          "Wertpapiere"),   # no crypto class yet — manual fix needed
    "bond":   ("Aktie",          "Wertpapiere"),   # no bond class yet — manual fix needed
    "other":  ("Aktie",          "Wertpapiere"),   # review manually
}

def map_asset_type(asset_type: str, symbol: str, warnings: list) -> tuple:
    if asset_type not in ASSET_TYPE_MAP:
        warnings.append(
            f"  ! Unknown asset_type '{asset_type}' for '{symbol}' — defaulting to Aktie/Wertpapiere"
        )
        return ("Aktie", "Wertpapiere")
    if asset_type in ("crypto", "bond", "other"):
        warnings.append(
            f"  ! '{symbol}' has asset_type='{asset_type}' → mapped to Aktie. "
            f"Review and update manually if needed."
        )
    return ASSET_TYPE_MAP[asset_type]


def migrate(conn: sqlite3.Connection, enc: EncryptionService, dry_run: bool) -> dict:
    conn.row_factory = sqlite3.Row
    today = date.today().isoformat()
    warnings: list = []
    portfolio_rows = conn.execute("SELECT * FROM portfolio").fetchall()
    watchlist_rows = conn.execute("SELECT * FROM watchlist").fetchall()

    positions_to_insert = []

    # ------------------------------------------------------------------
    # Portfolio → positions (in_portfolio = 1)
    # ------------------------------------------------------------------
    for row in portfolio_rows:
        asset_class, investment_type = map_asset_type(row["asset_type"], row["symbol"], warnings)

        quantity_raw = row["quantity"]
        quantity = float(enc.decrypt(quantity_raw)) if quantity_raw else None

        price_raw = row["purchase_price"]
        purchase_price = float(enc.decrypt(price_raw)) if price_raw else None

        notes_raw = row["notes"]
        notes_enc = notes_raw  # already encrypted, carry as-is

        positions_to_insert.append({
            "asset_class":            asset_class,
            "investment_type":        investment_type,
            "name":                   row["name"],
            "isin":                   None,
            "wkn":                    None,
            "ticker":                 row["symbol"],
            "quantity":               enc.encrypt(str(quantity)) if quantity is not None else None,
            "unit":                   "Stück",
            "purchase_price":         enc.encrypt(str(purchase_price)) if purchase_price is not None else None,
            "purchase_date":          row["purchase_date"],
            "notes":                  notes_enc,
            "extra_data":             None,
            "recommendation_source":  None,
            "strategy":               None,
            "added_date":             row["purchase_date"] or today,
            "in_portfolio":           1,
        })

    # ------------------------------------------------------------------
    # Watchlist → positions (in_portfolio = 0)
    # ------------------------------------------------------------------
    for row in watchlist_rows:
        asset_class, investment_type = map_asset_type(row["asset_type"], row["symbol"], warnings)

        notes_raw = row["notes"]
        notes_enc = notes_raw  # already encrypted, carry as-is

        # target_price → extra_data
        target_price_raw = row["target_price"]
        extra_data_enc = None
        if target_price_raw:
            target_price = float(enc.decrypt(target_price_raw))
            extra_data_enc = enc.encrypt(json.dumps({"target_price": target_price}))

        positions_to_insert.append({
            "asset_class":            asset_class,
            "investment_type":        investment_type,
            "name":                   row["name"],
            "isin":                   None,
            "wkn":                    None,
            "ticker":                 row["symbol"],
            "quantity":               None,
            "unit":                   "Stück",
            "purchase_price":         None,
            "purchase_date":          None,
            "notes":                  notes_enc,
            "extra_data":             extra_data_enc,
            "recommendation_source":  row["source"],  # user / agent
            "strategy":               None,
            "added_date":             row["added_date"],
            "in_portfolio":           0,
        })

    result = {
        "portfolio_rows": len(portfolio_rows),
        "watchlist_rows": len(watchlist_rows),
        "positions_to_insert": len(positions_to_insert),
        "warnings": warnings,
        "dry_run": dry_run,
    }

    if dry_run:
        return result

    # ------------------------------------------------------------------
    # Execute inside a transaction
    # ------------------------------------------------------------------
    with conn:
        for p in positions_to_insert:
            conn.execute(
                """
                INSERT INTO positions (
                    asset_class, investment_type,
                    name, isin, wkn, ticker,
                    quantity, unit, purchase_price, purchase_date,
                    notes, extra_data,
                    recommendation_source, strategy,
                    added_date, in_portfolio
                ) VALUES (
                    :asset_class, :investment_type,
                    :name, :isin, :wkn, :ticker,
                    :quantity, :unit, :purchase_price, :purchase_date,
                    :notes, :extra_data,
                    :recommendation_source, :strategy,
                    :added_date, :in_portfolio
                )
                """,
                p,
            )

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------
    count_portfolio = conn.execute(
        "SELECT COUNT(*) FROM positions WHERE in_portfolio = 1"
    ).fetchone()[0]
    count_watchlist = conn.execute(
        "SELECT COUNT(*) FROM positions WHERE in_portfolio = 0"
    ).fetchone()[0]

    assert count_portfolio == len(portfolio_rows), (
        f"Portfolio count mismatch: expected {len(portfolio_rows)}, got {count_portfolio}"
    )
    assert count_watchlist == len(watchlist_rows), (
        f"Watchlist count mismatch: expected {len(watchlist_rows)}, got {count_watchlist}"
    )

    result["inserted_portfolio"] = count_portfolio
    result["inserted_watchlist"] = count_watchlist
    return result


def main():
    parser = argparse.ArgumentParser(description="Migrate portfolio+watchlist to positions table.")
    parser.add_argument("--confirm", action="store_true", help="Execute the migration (default: dry-run)")
    parser.add_argument("--db", default="data/portfolio.db", help="Path to the SQLite database")
    args = parser.parse_args()

    dry_run = not args.confirm
    db_path = args.db

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at '{db_path}'")
        sys.exit(1)

    # Backup before writing
    if not dry_run:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{db_path}.pre_migration_{ts}"
        shutil.copy2(db_path, backup_path)
        print(f"Backup created: {backup_path}")

    encryption_key = os.environ.get("ENCRYPTION_KEY")
    if not encryption_key:
        print("ERROR: ENCRYPTION_KEY not set in environment / .env")
        sys.exit(1)

    salt = load_or_create_salt("data/salt.bin")
    enc = EncryptionService(encryption_key, salt)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    init_db(conn)  # ensures positions table exists

    print(f"\n{'DRY RUN — no changes will be made' if dry_run else 'EXECUTING MIGRATION'}")
    print("-" * 50)

    result = migrate(conn, enc, dry_run=dry_run)
    conn.close()

    print(f"Portfolio rows found:  {result['portfolio_rows']}")
    print(f"Watchlist rows found:  {result['watchlist_rows']}")
    print(f"Positions to insert:   {result['positions_to_insert']}")

    if result["warnings"]:
        print("\nWarnings (review manually after migration):")
        for w in result["warnings"]:
            print(w)

    if not dry_run:
        print(f"\nInserted portfolio:    {result['inserted_portfolio']}")
        print(f"Inserted watchlist:    {result['inserted_watchlist']}")
        print("\nMigration complete. Old tables (portfolio, watchlist) are untouched.")
        print("Run 'DROP TABLE portfolio; DROP TABLE watchlist;' only after verifying the app works correctly.")
    else:
        print("\nRe-run with --confirm to execute.")


if __name__ == "__main__":
    main()
