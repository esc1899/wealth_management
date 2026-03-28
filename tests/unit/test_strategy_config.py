"""
Unit tests for StrategyRegistry and strategies.yaml loading.
"""

import os
import tempfile

import pytest
import yaml

from core.strategy_config import (
    CUSTOM_STRATEGY_NAME,
    StrategyConfig,
    StrategyRegistry,
    load_strategies,
)


def _write_yaml(tmp_path, content: dict) -> str:
    path = os.path.join(tmp_path, "strategies.yaml")
    with open(path, "w") as f:
        yaml.dump(content, f)
    return path


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_yaml(tmp_path) -> str:
    return _write_yaml(tmp_path, {
        "strategies": {
            "Value Investing": {
                "description": "Graham / Buffett style",
                "system_prompt": "Focus on intrinsic value and margin of safety.",
            },
            "Wachstum 5-10 Jahre": {
                "description": "Growth over 5-10 years",
                "system_prompt": "Focus on revenue growth and TAM.",
            },
        }
    })


class TestLoadStrategies:
    def test_loads_all_strategies(self, sample_yaml):
        registry = load_strategies(sample_yaml)
        assert set(registry.all_names()) == {"Value Investing", "Wachstum 5-10 Jahre"}

    def test_strategy_fields_populated(self, sample_yaml):
        registry = load_strategies(sample_yaml)
        s = registry.require("Value Investing")
        assert s.name == "Value Investing"
        assert s.description == "Graham / Buffett style"
        assert "intrinsic value" in s.system_prompt

    def test_is_custom_false_for_yaml_strategies(self, sample_yaml):
        registry = load_strategies(sample_yaml)
        assert registry.require("Value Investing").is_custom is False

    def test_missing_top_level_key_raises(self, tmp_path):
        path = _write_yaml(tmp_path, {"wrong_key": {}})
        with pytest.raises(ValueError, match="top-level 'strategies' key"):
            load_strategies(path)

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            load_strategies("/nonexistent/path/strategies.yaml")


class TestStrategyRegistry:
    @pytest.fixture
    def registry(self):
        return StrategyRegistry({
            "Value Investing": StrategyConfig(
                name="Value Investing",
                description="Graham style",
                system_prompt="Focus on value.",
            ),
            "Growth": StrategyConfig(
                name="Growth",
                description="Growth style",
                system_prompt="Focus on growth.",
            ),
        })

    def test_get_existing(self, registry):
        s = registry.get("Value Investing")
        assert s is not None
        assert s.name == "Value Investing"

    def test_get_missing_returns_none(self, registry):
        assert registry.get("Nonexistent") is None

    def test_require_existing(self, registry):
        s = registry.require("Growth")
        assert s.system_prompt == "Focus on growth."

    def test_require_missing_raises(self, registry):
        with pytest.raises(ValueError, match="Unknown strategy"):
            registry.require("Nonexistent")

    def test_all_names(self, registry):
        names = registry.all_names()
        assert "Value Investing" in names
        assert "Growth" in names
        assert len(names) == 2

    def test_make_custom(self, registry):
        custom = registry.make_custom("My custom analysis focus.")
        assert custom.name == CUSTOM_STRATEGY_NAME
        assert custom.is_custom is True
        assert custom.system_prompt == "My custom analysis focus."

    def test_make_custom_with_description(self, registry):
        custom = registry.make_custom("Focus on X.", description="My desc")
        assert custom.description == "My desc"

    def test_make_custom_default_description(self, registry):
        custom = registry.make_custom("Focus on X.")
        assert custom.description != ""


class TestDefaultStrategiesYaml:
    """Smoke test: the shipped strategies.yaml is valid and loadable."""

    def test_default_yaml_loads(self):
        from core.strategy_config import get_strategy_registry
        # Clear the cache to avoid stale state
        get_strategy_registry.cache_clear()
        registry = get_strategy_registry()
        assert len(registry.all_names()) >= 3

    def test_all_strategies_have_system_prompt(self):
        from core.strategy_config import get_strategy_registry
        get_strategy_registry.cache_clear()
        registry = get_strategy_registry()
        for name in registry.all_names():
            s = registry.require(name)
            assert s.system_prompt.strip(), f"Strategy '{name}' has empty system_prompt"
