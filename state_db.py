"""
Database and encryption initialization — cached singletons.
"""

from pathlib import Path
import streamlit as st

from config import config
from core.encryption import PassthroughEncryptionService
from core.storage.base import build_encryption_service, get_connection, init_db, migrate_db

_PROJECT_ROOT = Path(__file__).parent


@st.cache_resource
def get_db_connection():
    """Get or create database connection. Runs init and migrations."""
    conn = get_connection(config.DB_PATH)
    init_db(conn)
    migrate_db(conn)
    return conn


@st.cache_resource
def get_encryption_service():
    """Get encryption service — passthrough in demo mode, Fernet in prod."""
    if config.DEMO_MODE:
        return PassthroughEncryptionService()
    return build_encryption_service(config.ENCRYPTION_KEY, str(_PROJECT_ROOT / "data" / "salt.bin"))
