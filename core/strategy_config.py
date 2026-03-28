"""
Investmentstrategie-Konfiguration.
Lädt config/strategies.yaml und stellt die Definitionen app-weit bereit.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

import yaml
from pydantic import BaseModel

_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "strategies.yaml"
)

CUSTOM_STRATEGY_NAME = "Eigene Strategie"


class StrategyConfig(BaseModel):
    name: str
    description: str
    system_prompt: str
    is_custom: bool = False


class StrategyRegistry:
    """In-memory registry built from the YAML config."""

    def __init__(self, strategies: dict[str, StrategyConfig]):
        self._strategies = strategies

    def get(self, name: str) -> Optional[StrategyConfig]:
        return self._strategies.get(name)

    def require(self, name: str) -> StrategyConfig:
        cfg = self._strategies.get(name)
        if cfg is None:
            raise ValueError(
                f"Unknown strategy '{name}'. "
                f"Valid strategies: {list(self._strategies.keys())}"
            )
        return cfg

    def all_names(self) -> List[str]:
        return list(self._strategies.keys())

    def make_custom(self, system_prompt: str, description: str = "") -> StrategyConfig:
        """Create an ad-hoc custom strategy (not persisted in YAML)."""
        return StrategyConfig(
            name=CUSTOM_STRATEGY_NAME,
            description=description or "Benutzerdefinierte Analysestrategie",
            system_prompt=system_prompt,
            is_custom=True,
        )


def load_strategies(path: str = _DEFAULT_CONFIG_PATH) -> StrategyRegistry:
    """Parse strategies.yaml and return a validated registry."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if "strategies" not in raw:
        raise ValueError(f"YAML at '{path}' must have a top-level 'strategies' key.")

    strategies = {}
    for name, data in raw["strategies"].items():
        strategies[name] = StrategyConfig(name=name, **data)

    return StrategyRegistry(strategies)


@lru_cache(maxsize=1)
def get_strategy_registry(path: str = _DEFAULT_CONFIG_PATH) -> StrategyRegistry:
    """Cached singleton — use this in application code."""
    return load_strategies(path)
