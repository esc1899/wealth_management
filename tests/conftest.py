import pytest
import os

# Set test environment variables before any imports
os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
os.environ.setdefault("LANGFUSE_SECRET_KEY", "test_secret")
os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "test_public")
os.environ.setdefault("ENCRYPTION_KEY", "test_encryption_key_32bytes_long!!")
os.environ.setdefault("DB_PATH", ":memory:")
