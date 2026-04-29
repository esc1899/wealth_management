"""
Database and encryption initialization — cached singletons.
"""

import logging
from pathlib import Path
import streamlit as st

from config import config
from core.encryption import PassthroughEncryptionService
from core.storage.base import build_encryption_service, get_connection, init_db, migrate_db

_PROJECT_ROOT = Path(__file__).parent
logger = logging.getLogger(__name__)


@st.cache_resource
def get_db_connection():
    """Get or create database connection. Runs init and migrations once per process."""
    logger.info(f"Initializing DB connection at {config.DB_PATH}")
    conn = get_connection(config.DB_PATH)
    logger.info(f"Running init_db...")
    init_db(conn)
    logger.info(f"Running migrate_db...")
    migrate_db(conn)
    logger.info(f"DB schema initialization complete")
    return conn


@st.cache_resource
def get_encryption_service():
    """Get encryption service — passthrough in demo mode, Fernet in prod."""
    if config.DEMO_MODE:
        return PassthroughEncryptionService()
    return build_encryption_service(config.ENCRYPTION_KEY, str(_PROJECT_ROOT / "data" / "salt.bin"))
