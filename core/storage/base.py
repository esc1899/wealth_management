"""
SQLite database connection and schema initialization.
"""

import sqlite3
import os
from core.encryption import EncryptionService, load_or_create_salt


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a SQLite connection, creating the database directory if needed."""
    if db_path != ":memory:":
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # concurrent reads while writing
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they do not exist."""
    statements = [
        """CREATE TABLE IF NOT EXISTS positions (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_class           TEXT NOT NULL,
            investment_type       TEXT NOT NULL,
            name                  TEXT NOT NULL,
            isin                  TEXT,
            wkn                   TEXT,
            ticker                TEXT,
            quantity              TEXT,
            unit                  TEXT NOT NULL,
            purchase_price        TEXT,
            purchase_date         TEXT,
            notes                 TEXT,
            extra_data            TEXT,
            recommendation_source TEXT,
            strategy              TEXT,
            added_date            TEXT NOT NULL,
            in_portfolio          INTEGER NOT NULL DEFAULT 0,
            in_watchlist          INTEGER NOT NULL DEFAULT 0,
            empfehlung            TEXT,
            story                 TEXT,
            story_skill           TEXT,
            rebalance_excluded    INTEGER NOT NULL DEFAULT 0,
            anlageart             TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker)",
        "CREATE INDEX IF NOT EXISTS idx_positions_in_portfolio ON positions(in_portfolio)",
        """CREATE TABLE IF NOT EXISTS current_prices (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol            TEXT NOT NULL UNIQUE,
            price_eur         REAL NOT NULL,
            currency_original TEXT NOT NULL,
            price_original    REAL NOT NULL,
            exchange_rate     REAL NOT NULL,
            fetched_at        TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS historical_prices (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol    TEXT NOT NULL,
            date      TEXT NOT NULL,
            close_eur REAL NOT NULL,
            volume    INTEGER,
            UNIQUE(symbol, date)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_hist_prices_symbol_date ON historical_prices(symbol, date)",
        """CREATE TABLE IF NOT EXISTS research_sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT NOT NULL,
            company_name    TEXT,
            strategy_name   TEXT NOT NULL,
            strategy_prompt TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            summary         TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS research_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES research_sessions(id),
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_research_messages_session ON research_messages(session_id)",
    ]
    for stmt in statements:
        conn.execute(stmt)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS skills (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            area        TEXT NOT NULL,
            description TEXT,
            prompt      TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            hidden      INTEGER NOT NULL DEFAULT 0,
            UNIQUE(name, area)
        )"""
    )
    for stmt in [
        """CREATE TABLE IF NOT EXISTS search_sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            query        TEXT NOT NULL,
            skill_name   TEXT NOT NULL,
            skill_prompt TEXT NOT NULL,
            created_at   TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS search_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES search_sessions(id),
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_search_messages_session ON search_messages(session_id)",
        """CREATE TABLE IF NOT EXISTS storychecker_sessions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id   INTEGER NOT NULL,
            ticker        TEXT,
            position_name TEXT NOT NULL,
            skill_name    TEXT NOT NULL,
            skill_prompt  TEXT NOT NULL,
            created_at    TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS storychecker_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES storychecker_sessions(id),
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_storychecker_messages_session ON storychecker_messages(session_id)",
        """CREATE TABLE IF NOT EXISTS news_runs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT NOT NULL,
            tickers    TEXT NOT NULL,
            result     TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS news_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id     INTEGER NOT NULL REFERENCES news_runs(id),
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_news_messages_run ON news_messages(run_id)",
        """CREATE TABLE IF NOT EXISTS position_analyses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL,
            agent       TEXT NOT NULL,
            skill_name  TEXT NOT NULL,
            verdict     TEXT,
            summary     TEXT,
            session_id  INTEGER,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )""",
        "CREATE INDEX IF NOT EXISTS idx_position_analyses_position ON position_analyses(position_id)",
        "CREATE INDEX IF NOT EXISTS idx_position_analyses_agent ON position_analyses(position_id, agent)",
        """CREATE TABLE IF NOT EXISTS rebalance_sessions (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name         TEXT NOT NULL,
            skill_prompt       TEXT NOT NULL,
            portfolio_snapshot TEXT NOT NULL,
            created_at         TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS rebalance_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES rebalance_sessions(id),
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_rebalance_messages_session ON rebalance_messages(session_id)",
        """CREATE TABLE IF NOT EXISTS llm_usage (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            agent         TEXT NOT NULL,
            model         TEXT NOT NULL,
            skill         TEXT,
            source        TEXT NOT NULL DEFAULT 'manual',
            input_tokens  INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            duration_ms   INTEGER,
            position_count INTEGER,
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        )""",
        "CREATE INDEX IF NOT EXISTS idx_llm_usage_agent ON llm_usage(agent)",
        "CREATE INDEX IF NOT EXISTS idx_llm_usage_created ON llm_usage(created_at)",
        """CREATE TABLE IF NOT EXISTS usage_resets (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            agent    TEXT,
            model    TEXT,
            skill    TEXT,
            reset_at TEXT NOT NULL DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS benchmark_runs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            scenario_name TEXT NOT NULL,
            agent         TEXT NOT NULL,
            model         TEXT NOT NULL,
            skill_name    TEXT NOT NULL,
            input_tokens  INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cost_eur      REAL NOT NULL DEFAULT 0,
            duration_ms   INTEGER,
            run_at        TEXT NOT NULL DEFAULT (datetime('now')),
            label         TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_benchmark_runs_scenario ON benchmark_runs(scenario_name)",
        """CREATE TABLE IF NOT EXISTS app_config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS structural_scan_runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name  TEXT NOT NULL,
            user_focus  TEXT,
            result      TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS structural_scan_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id     INTEGER NOT NULL REFERENCES structural_scan_runs(id),
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_structural_scan_messages_run ON structural_scan_messages(run_id)",
        """CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name  TEXT NOT NULL,
            skill_name  TEXT NOT NULL,
            skill_prompt TEXT NOT NULL,
            frequency   TEXT NOT NULL,
            run_hour    INTEGER NOT NULL DEFAULT 8,
            run_minute  INTEGER NOT NULL DEFAULT 0,
            run_weekday INTEGER,
            run_day     INTEGER,
            model       TEXT,
            enabled     INTEGER NOT NULL DEFAULT 1,
            last_run    TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )""",
        """CREATE TABLE IF NOT EXISTS dividend_data (
            symbol      TEXT NOT NULL PRIMARY KEY,
            rate_eur    REAL,
            yield_pct   REAL,
            currency    TEXT,
            fetched_at  TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS wealth_snapshots (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            date          TEXT NOT NULL UNIQUE,
            total_eur     REAL NOT NULL,
            breakdown     TEXT NOT NULL,
            coverage_pct  REAL NOT NULL DEFAULT 100.0,
            missing_pos   TEXT,
            is_manual     INTEGER NOT NULL DEFAULT 0,
            note          TEXT,
            created_at    TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_wealth_snapshots_date ON wealth_snapshots(date)",
        """CREATE TABLE IF NOT EXISTS portfolio_story (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            story         TEXT NOT NULL,
            target_year   INTEGER,
            liquidity_need TEXT,
            priority      TEXT NOT NULL DEFAULT 'Gemischt',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS portfolio_story_analyses (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            verdict            TEXT NOT NULL,
            summary            TEXT NOT NULL,
            perf_verdict       TEXT NOT NULL,
            perf_summary       TEXT NOT NULL,
            stability_verdict  TEXT NOT NULL,
            stability_summary  TEXT NOT NULL,
            full_text          TEXT NOT NULL,
            created_at         TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS portfolio_story_position_fits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id INTEGER NOT NULL,
            fit_verdict TEXT NOT NULL,
            fit_summary TEXT NOT NULL,
            created_at  TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_portfolio_story_position_fits_position ON portfolio_story_position_fits(position_id)",
    ]:
        conn.execute(stmt)
    conn.commit()


def migrate_db(conn: sqlite3.Connection) -> None:
    """Apply schema migrations for columns/tables added after initial release."""
    existing_pos = {row[1] for row in conn.execute("PRAGMA table_info(positions)")}
    if "in_watchlist" not in existing_pos:
        conn.execute("ALTER TABLE positions ADD COLUMN in_watchlist INTEGER NOT NULL DEFAULT 0")
        # Convert existing data: in_portfolio=0 was implicitly "watchlist" → set in_watchlist=1
        conn.execute("UPDATE positions SET in_watchlist = 1 WHERE in_portfolio = 0")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_in_watchlist ON positions(in_watchlist)")
    if "empfehlung" not in existing_pos:
        conn.execute("ALTER TABLE positions ADD COLUMN empfehlung TEXT")
    if "story" not in existing_pos:
        conn.execute("ALTER TABLE positions ADD COLUMN story TEXT")
    if "story_skill" not in existing_pos:
        conn.execute("ALTER TABLE positions ADD COLUMN story_skill TEXT")
    if "rebalance_excluded" not in existing_pos:
        conn.execute("ALTER TABLE positions ADD COLUMN rebalance_excluded INTEGER NOT NULL DEFAULT 0")
    if "anlageart" not in existing_pos:
        conn.execute("ALTER TABLE positions ADD COLUMN anlageart TEXT")

    existing_skills = {row[1] for row in conn.execute("PRAGMA table_info(skills)")}
    if "hidden" not in existing_skills:
        conn.execute(
            "ALTER TABLE skills ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0"
        )

    existing_usage = {row[1] for row in conn.execute("PRAGMA table_info(llm_usage)")}
    if "skill" not in existing_usage:
        conn.execute("ALTER TABLE llm_usage ADD COLUMN skill TEXT")
    if "source" not in existing_usage:
        conn.execute("ALTER TABLE llm_usage ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
    if "duration_ms" not in existing_usage:
        conn.execute("ALTER TABLE llm_usage ADD COLUMN duration_ms INTEGER")
    if "position_count" not in existing_usage:
        conn.execute("ALTER TABLE llm_usage ADD COLUMN position_count INTEGER")

    # NOTE: benchmark_runs and portfolio_story_position_fits are defined here (not just in init_db)
    # because they have ALTER TABLE migrations that must run when present.
    # Other tables (usage_resets, dividend_data) are defined only in init_db.
    conn.execute("""CREATE TABLE IF NOT EXISTS benchmark_runs (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        scenario_name TEXT NOT NULL,
        agent         TEXT NOT NULL,
        model         TEXT NOT NULL,
        skill_name    TEXT NOT NULL,
        input_tokens  INTEGER NOT NULL,
        output_tokens INTEGER NOT NULL,
        cost_eur      REAL NOT NULL DEFAULT 0,
        duration_ms   INTEGER,
        run_at        TEXT NOT NULL DEFAULT (datetime('now')),
        label         TEXT
    )""")
    existing_bm = {row[1] for row in conn.execute("PRAGMA table_info(benchmark_runs)")}
    if "duration_ms" not in existing_bm:
        conn.execute("ALTER TABLE benchmark_runs ADD COLUMN duration_ms INTEGER")

    # Create portfolio_story_position_fits table if it doesn't exist
    conn.execute("""CREATE TABLE IF NOT EXISTS portfolio_story_position_fits (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        position_id INTEGER NOT NULL,
        fit_verdict TEXT NOT NULL,
        fit_summary TEXT NOT NULL,
        created_at  TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_story_position_fits_position ON portfolio_story_position_fits(position_id)")

    # Migrate fit_verdict → fit_role
    existing_fits = {row[1] for row in conn.execute("PRAGMA table_info(portfolio_story_position_fits)")}
    if "fit_verdict" in existing_fits and "fit_role" not in existing_fits:
        conn.execute("ALTER TABLE portfolio_story_position_fits RENAME COLUMN fit_verdict TO fit_role")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_runs_scenario ON benchmark_runs(scenario_name)")
    conn.commit()


def build_encryption_service(password: str, salt_path: str) -> EncryptionService:
    salt = load_or_create_salt(salt_path)
    return EncryptionService(password, salt)
