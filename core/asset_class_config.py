"""
Asset class configuration.
Loads config/asset_classes.yaml and provides the definitions application-wide.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

import yaml
from pydantic import BaseModel, field_validator

_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "asset_classes.yaml"
)

ALL_FIELDS = [
    "isin", "wkn", "ticker", "quantity", "unit",
    "purchase_price", "purchase_date",
    "recommendation_source", "strategy", "notes", "extra_data",
]


class AssetClassConfig(BaseModel):
    name: str
    investment_type: str
    default_unit: str
    unit_options: List[str] = []
    visible_fields: List[str]
    price_source: str
    requires_ticker: bool = True
    auto_fetch: bool = True
    watchlist_eligible: bool = True
    manual_valuation: bool = False
    extra_fields: List[str] = []
    anlagearten: List[str] = []

    @field_validator("visible_fields")
    @classmethod
    def fields_must_be_known(cls, v: List[str]) -> List[str]:
        unknown = set(v) - set(ALL_FIELDS)
        if unknown:
            raise ValueError(f"Unknown fields in visible_fields: {unknown}")
        return v

    def is_field_visible(self, field: str) -> bool:
        return field in self.visible_fields


class AssetClassRegistry:
    """In-memory registry built from the YAML config."""

    def __init__(self, classes: dict[str, AssetClassConfig]):
        self._classes = classes

    def get(self, name: str) -> Optional[AssetClassConfig]:
        return self._classes.get(name)

    def require(self, name: str) -> AssetClassConfig:
        cfg = self._classes.get(name)
        if cfg is None:
            raise ValueError(
                f"Unknown asset class '{name}'. "
                f"Valid classes: {list(self._classes.keys())}"
            )
        return cfg

    def all_names(self) -> List[str]:
        return list(self._classes.keys())

    def investment_types(self) -> List[str]:
        seen = []
        for cfg in self._classes.values():
            if cfg.investment_type not in seen:
                seen.append(cfg.investment_type)
        return seen

    def classes_for_type(self, investment_type: str) -> List[str]:
        return [
            name for name, cfg in self._classes.items()
            if cfg.investment_type == investment_type
        ]

    def watchlist_eligible_names(self) -> List[str]:
        """Asset class names that can appear on the watchlist."""
        return [n for n, cfg in self._classes.items() if cfg.watchlist_eligible]

    def auto_fetch_names(self) -> List[str]:
        """Asset class names whose prices are fetched automatically via yfinance."""
        return [n for n, cfg in self._classes.items() if cfg.auto_fetch]

    def manual_valuation_names(self) -> List[str]:
        """Asset class names that require manual valuation (Immobilie, Grundstück)."""
        return [n for n, cfg in self._classes.items() if cfg.manual_valuation]


def load_asset_classes(path: str = _DEFAULT_CONFIG_PATH) -> AssetClassRegistry:
    """Parse asset_classes.yaml and return a validated registry."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if "asset_classes" not in raw:
        raise ValueError(f"YAML at '{path}' must have a top-level 'asset_classes' key.")

    classes = {}
    for name, data in raw["asset_classes"].items():
        classes[name] = AssetClassConfig(name=name, **data)

    return AssetClassRegistry(classes)


@lru_cache(maxsize=1)
def get_asset_class_registry(path: str = _DEFAULT_CONFIG_PATH) -> AssetClassRegistry:
    """Cached singleton — use this in application code."""
    return load_asset_classes(path)
