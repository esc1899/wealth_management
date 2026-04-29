"""Integration test for DB schema migration — verify critical tables exist."""

import pytest
from core.storage.base import get_connection, init_db, migrate_db


@pytest.fixture
def fresh_db():
    """Create a fresh in-memory SQLite DB and run migrations."""
    conn = get_connection(":memory:")
    init_db(conn)
    migrate_db(conn)
    yield conn
    conn.close()


class TestDBSchemaMigration:
    """Verify all critical tables are created by migrate_db()."""

    def test_critical_tables_exist(self, fresh_db):
        """Verify all critical tables exist after migration."""
        cursor = fresh_db.cursor()
        result = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {t[0] for t in result}

        # Core tables that must always exist for app to function
        critical_tables = {
            # Position management
            "positions",
            "current_prices",
            "historical_prices",
            # Analysis & verdicts
            "position_analyses",
            # Sessions (multi-turn chat)
            "research_sessions",
            "research_messages",
            "search_sessions",
            "search_messages",
            "storychecker_sessions",
            "storychecker_messages",
            "fundamental_analyzer_sessions",
            "fundamental_analyzer_messages",
            # Structural & snapshot
            "structural_scan_runs",
            "structural_scan_messages",
            # Portfolio & wealth
            "wealth_snapshots",
            "dividend_snapshots",
            "portfolio_story",
            "agent_runs",
            # Config
            "skills",
            "app_config",
            "scheduled_jobs",
            # Logging
            "llm_usage",
        }

        missing = critical_tables - table_names
        assert not missing, f"Missing critical tables after migration: {sorted(missing)}"

    def test_fundamental_analyzer_tables_have_correct_schema(self, fresh_db):
        """Verify fundamental_analyzer tables have expected columns."""
        cursor = fresh_db.cursor()

        # Check fundamental_analyzer_sessions table
        sessions_cols = cursor.execute(
            "PRAGMA table_info(fundamental_analyzer_sessions)"
        ).fetchall()
        sessions_col_names = {col[1] for col in sessions_cols}

        expected_session_cols = {"id", "position_id", "ticker", "position_name", "skill_name", "created_at"}
        missing_session_cols = expected_session_cols - sessions_col_names
        assert not missing_session_cols, f"Missing columns in fundamental_analyzer_sessions: {missing_session_cols}"

        # Check fundamental_analyzer_messages table
        messages_cols = cursor.execute(
            "PRAGMA table_info(fundamental_analyzer_messages)"
        ).fetchall()
        messages_col_names = {col[1] for col in messages_cols}

        expected_message_cols = {"id", "session_id", "role", "content", "created_at"}
        missing_message_cols = expected_message_cols - messages_col_names
        assert not missing_message_cols, f"Missing columns in fundamental_analyzer_messages: {missing_message_cols}"

    def test_storychecker_tables_have_correct_schema(self, fresh_db):
        """Verify storychecker tables have expected columns."""
        cursor = fresh_db.cursor()

        # Check storychecker_sessions table
        sessions_cols = cursor.execute(
            "PRAGMA table_info(storychecker_sessions)"
        ).fetchall()
        sessions_col_names = {col[1] for col in sessions_cols}

        expected_session_cols = {"id", "position_id", "ticker", "position_name", "skill_name", "skill_prompt", "created_at"}
        missing_session_cols = expected_session_cols - sessions_col_names
        assert not missing_session_cols, f"Missing columns in storychecker_sessions: {missing_session_cols}"

        # Check storychecker_messages table
        messages_cols = cursor.execute(
            "PRAGMA table_info(storychecker_messages)"
        ).fetchall()
        messages_col_names = {col[1] for col in messages_cols}

        expected_message_cols = {"id", "session_id", "role", "content", "created_at"}
        missing_message_cols = expected_message_cols - messages_col_names
        assert not missing_message_cols, f"Missing columns in storychecker_messages: {missing_message_cols}"

    def test_position_analyses_table_exists(self, fresh_db):
        """Verify position_analyses table for verdict storage."""
        cursor = fresh_db.cursor()
        result = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='position_analyses'"
        ).fetchone()
        assert result, "position_analyses table not found"

    def test_foreign_key_constraints_exist(self, fresh_db):
        """Verify foreign key relationships are defined."""
        cursor = fresh_db.cursor()

        # Verify fundamental_analyzer_messages → fundamental_analyzer_sessions
        fk_info = cursor.execute(
            "PRAGMA foreign_key_list(fundamental_analyzer_messages)"
        ).fetchall()
        fk_tables = {fk[2] for fk in fk_info}
        assert "fundamental_analyzer_sessions" in fk_tables, "Foreign key to fundamental_analyzer_sessions not found"

        # Verify storychecker_messages → storychecker_sessions
        fk_info = cursor.execute(
            "PRAGMA foreign_key_list(storychecker_messages)"
        ).fetchall()
        fk_tables = {fk[2] for fk in fk_info}
        assert "storychecker_sessions" in fk_tables, "Foreign key to storychecker_sessions not found"
