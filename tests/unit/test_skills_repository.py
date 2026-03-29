"""
Unit tests for SkillsRepository.
Uses real SQLite in-memory DB — no mocking of storage.
"""

import sqlite3

import pytest

from core.storage.base import init_db
from core.storage.models import Skill
from core.storage.skills import SkillsRepository


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    init_db(c)
    return c


@pytest.fixture
def repo(conn):
    return SkillsRepository(conn)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_skill(**kwargs) -> Skill:
    defaults = dict(name="Value Investing", area="research", prompt="Analysiere den inneren Wert.")
    defaults.update(kwargs)
    return Skill(**defaults)


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

def test_add_and_get(repo):
    skill = _make_skill()
    saved = repo.add(skill)
    assert saved.id is not None

    fetched = repo.get(saved.id)
    assert fetched is not None
    assert fetched.name == "Value Investing"
    assert fetched.area == "research"
    assert fetched.prompt == "Analysiere den inneren Wert."


def test_get_by_area_filters_correctly(repo):
    repo.add(_make_skill(name="Value", area="research"))
    repo.add(_make_skill(name="Momentum", area="research"))
    repo.add(_make_skill(name="Risk", area="portfolio_analysis"))

    research_skills = repo.get_by_area("research")
    assert len(research_skills) == 2
    assert all(s.area == "research" for s in research_skills)

    portfolio_skills = repo.get_by_area("portfolio_analysis")
    assert len(portfolio_skills) == 1
    assert portfolio_skills[0].name == "Risk"


def test_update(repo):
    saved = repo.add(_make_skill())
    updated = saved.model_copy(update={"name": "Growth Investing", "prompt": "Neuer Prompt."})
    repo.update(updated)

    fetched = repo.get(saved.id)
    assert fetched.name == "Growth Investing"
    assert fetched.prompt == "Neuer Prompt."


def test_delete(repo):
    saved = repo.add(_make_skill())
    repo.delete(saved.id)

    fetched = repo.get(saved.id)
    assert fetched is None


def test_seed_if_empty_seeds_when_empty(repo):
    defaults = [
        {"name": "Value", "area": "research", "description": "Value strategy", "prompt": "Prompt A"},
        {"name": "Growth", "area": "research", "description": "Growth strategy", "prompt": "Prompt B"},
    ]
    repo.seed_if_empty("research", defaults)

    skills = repo.get_by_area("research")
    assert len(skills) == 2
    names = {s.name for s in skills}
    assert names == {"Value", "Growth"}


def test_seed_if_empty_skips_when_already_seeded(repo):
    # Seed once manually
    repo.add(_make_skill(name="Existing", area="research"))

    # seed_if_empty should not add anything because area is non-empty
    defaults = [
        {"name": "Value", "area": "research", "description": "x", "prompt": "p"},
    ]
    repo.seed_if_empty("research", defaults)

    skills = repo.get_by_area("research")
    assert len(skills) == 1
    assert skills[0].name == "Existing"


def test_unique_constraint_on_name_and_area(repo):
    repo.add(_make_skill(name="Value", area="research"))

    with pytest.raises(Exception):
        # Inserting the same (name, area) pair must raise an integrity error
        repo.add(_make_skill(name="Value", area="research"))
