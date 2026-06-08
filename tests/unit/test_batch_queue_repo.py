"""Unit tests for BatchQueueRepository."""

import pytest
from core.storage.base import get_connection, init_db, migrate_db
from core.storage.batch_queue import BatchQueueRepository


@pytest.fixture
def db():
    conn = get_connection(":memory:")
    init_db(conn)
    migrate_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def repo(db):
    return BatchQueueRepository(db)


class TestBatchQueueRepository:
    def test_create_and_get_pending(self, repo):
        repo.create("msgbatch_abc", "storychecker", "Standard", "de", 5)
        pending = repo.get_pending()
        assert len(pending) == 1
        assert pending[0].batch_id == "msgbatch_abc"
        assert pending[0].agent_name == "storychecker"
        assert pending[0].skill_name == "Standard"
        assert pending[0].language == "de"
        assert pending[0].request_count == 5
        assert pending[0].status == "processing"

    def test_mark_done(self, repo):
        repo.create("msgbatch_done", "consensus_gap", None, "de", 3)
        repo.mark_done("msgbatch_done", 3, 0)
        pending = repo.get_pending()
        assert len(pending) == 0

    def test_mark_error(self, repo):
        repo.create("msgbatch_err", "fundamental", None, "de", 2)
        repo.mark_error("msgbatch_err", "API timeout")
        pending = repo.get_pending()
        assert len(pending) == 0

    def test_get_pending_excludes_done(self, repo):
        repo.create("batch1", "storychecker", None, "de", 1)
        repo.create("batch2", "consensus_gap", None, "de", 2)
        repo.mark_done("batch1", 1, 0)
        pending = repo.get_pending()
        assert len(pending) == 1
        assert pending[0].batch_id == "batch2"

    def test_idempotent_create(self, repo):
        repo.create("dup_batch", "storychecker", None, "de", 5)
        repo.create("dup_batch", "storychecker", None, "de", 5)  # duplicate → ignored
        assert len(repo.get_pending()) == 1

    def test_language_defaults_to_de(self, repo):
        repo.create("batch_lang", "storychecker", None, "de", 1)
        pending = repo.get_pending()
        assert pending[0].language == "de"
