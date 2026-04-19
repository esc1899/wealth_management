# Database Migrations Guide

This document explains how the database schema evolution works and which migrations are idempotent.

## Overview

The schema is managed via two functions in `core/storage/base.py`:

1. **`init_db(conn)`** — Creates all tables from scratch (used for fresh databases)
2. **`migrate_db(conn)`** — Applies incremental schema changes (used for existing databases)

Both functions use `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` to be idempotent. Running either multiple times is safe and produces no errors.

---

## Migration Strategy

### Core Principle

- **Fresh start:** Call `init_db()` once, then `migrate_db()` once
- **Existing database:** Call `migrate_db()` on app startup — it applies only missing changes
- **Idempotent:** Both functions check for existence before creating (no duplicates, no failures)

### Special Cases

Some tables appear in **both** `init_db()` AND `migrate_db()` because they have ALTER TABLE migrations:

| Table | Reason |
|---|---|
| **portfolio_story_position_fits** | Migration: renamed `fit_verdict` → `fit_role` |
| **agent_runs** | Latest table; created in both for completeness |

Why both? If we only checked in `migrate_db()`, fresh databases from `init_db()` would miss the ALTER TABLE changes. Instead:
- `init_db()` creates the table with the **final schema** (including future columns)
- `migrate_db()` applies the same CREATE (no-op) but also runs ALTER TABLE if needed

---

## Key Migrations

### Column Additions (ALTER TABLE)

All ALTER TABLE operations check if the column exists before adding:

```python
existing_pos = {row[1] for row in conn.execute("PRAGMA table_info(positions)")}
if "in_watchlist" not in existing_pos:
    conn.execute("ALTER TABLE positions ADD COLUMN in_watchlist INTEGER...")
```

This pattern is idempotent and safe for concurrent readers (WAL mode).

### Renames (ALTER TABLE ... RENAME COLUMN)

```python
# portfolio_story_position_fits: fit_verdict → fit_role
if "fit_verdict" in existing_fits and "fit_role" not in existing_fits:
    conn.execute("ALTER TABLE portfolio_story_position_fits RENAME COLUMN fit_verdict TO fit_role")
```

---

## Tables Only in `init_db()`

These tables have no migrations; they're created once and never modified:

- `app_config` — Application settings
- `usage_resets` — LLM usage reset history
- `dividend_data` — Dividend information
- `scheduled_jobs` — Scheduled agent runs
- (most other tables)

---

## Adding a New Column

To add a column to an existing table:

1. **Add to `init_db()`** in the CREATE TABLE statement (final schema)
2. **Add to `migrate_db()`** with ALTER TABLE guard:

```python
# In migrate_db():
existing_xxx = {row[1] for row in conn.execute("PRAGMA table_info(xxx_table)")}
if "new_column" not in existing_xxx:
    conn.execute("ALTER TABLE xxx_table ADD COLUMN new_column TYPE NOT NULL DEFAULT value")
```

3. **Test:** Run on a fresh `:memory:` database to ensure init path works, then on an existing database to ensure migration path works.

---

## Adding a New Table

1. **Add to `init_db()`** in the CREATE TABLE statements
2. **Usually NOT needed in `migrate_db()`** (unless there are future ALTER TABLE operations on that table)
3. If the table will be modified later, add the CREATE TABLE to `migrate_db()` too (see `portfolio_story_position_fits` as example)

---

## Gotchas

### ❌ Running `init_db()` on an Existing Database
If you call `init_db()` on a database that already exists:
- CREATE TABLE IF NOT EXISTS will skip existing tables
- Columns added via migrate_db() will be missing
- **Result:** Schema mismatch

**Fix:** Always call `migrate_db()` after `init_db()` to apply missing changes:
```python
db = get_connection(DB_PATH)
init_db(db)
migrate_db(db)  # Applies any missing columns/indexes
```

### ⚠️ Concurrent Writes During Migration
ALTER TABLE is expensive and locks writers (even with WAL). The app should:
- Call migrations on startup (before serving requests)
- Migrations typically run in <100ms for small additions

### ❌ Modifying Without Both Functions
If you add a column to `migrate_db()` but forget `init_db()`:
- Fresh databases miss the column → bugs
- Existing databases get the column → inconsistency

**Always touch both functions when changing schema.**

---

## Testing Migrations

### Fresh Database Test
```python
conn = get_connection(":memory:")
init_db(conn)
migrate_db(conn)
# Verify all tables and columns exist
```

### Existing Database Test (Simulate Upgrade)
```python
# Create old schema
conn = get_connection(":memory:")
init_db(conn)
# (don't call migrate_db yet)

# Add a row, then migrate
conn.execute("INSERT INTO positions (...) VALUES (...)")
conn.commit()

migrate_db(conn)
# Verify new columns exist and old rows are intact
```

---

## Entry Point: `get_db()` in `state.py`

The migration is always applied via the single `get_connection()` + `init_db()` + `migrate_db()` pattern in app startup or test fixtures.

**See:** `tests/conftest.py` for fixtures that correctly call both.

