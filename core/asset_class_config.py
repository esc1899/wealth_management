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

# Asset classes that are diversified fund vehicles (analysed on fund terms — mandate,
# holdings, costs, same-category peers — NOT as single companies). Single source of truth
# shared by the FundamentalAnalyzer and Storychecker so a fund is never measured by
# equity yardsticks. Matches the four "*fonds" classes in config/asset_classes.yaml.
FUND_ASSET_CLASSES = {"Aktienfonds", "Rentenfonds", "Immobilienfonds", "Infrastrukturfonds"}


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
    block: Optional[str] = None   # aktien, geldwerte, sachwerte -- wo die Klasse auf Kacheln und Diagrammen steht
    farbe: str = "#5E6B7A"   # Farbe der Klasse, ueberall in der App dieselbe; ein Ton ihres Blocks
    pruefbar: bool = True    # laufen die Checks fuer Titel dieser Klasse (core/pruefung.py)

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

    def __init__(self, classes: dict[str, AssetClassConfig], bloecke: Optional[dict[str, str]] = None):
        self._classes = classes
        self._bloecke = bloecke or {}   # Block -> Farbe, in der Reihenfolge der YAML-Datei

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

    def bloecke(self) -> List[str]:
        """Die Bloecke in der Reihenfolge, in der Kacheln und Diagramme sie zeigen."""
        return list(self._bloecke)

    def block_von(self, name: str) -> Optional[str]:
        """Der Block einer Anlageklasse; None fuer eine unbekannte."""
        cfg = self._classes.get(name)
        return cfg.block if cfg else None

    def block_farbe(self, block: str) -> Optional[str]:
        return self._bloecke.get(block)

    def manual_valuation_names(self) -> List[str]:
        """Asset class names that require manual valuation (Immobilie, Grundstück)."""
        return [n for n, cfg in self._classes.items() if cfg.manual_valuation]


def load_asset_classes(path: str = _DEFAULT_CONFIG_PATH) -> AssetClassRegistry:
    """Parse asset_classes.yaml and return a validated registry."""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if "asset_classes" not in raw:
        raise ValueError(f"YAML at '{path}' must have a top-level 'asset_classes' key.")

    bloecke = {name: (daten or {}).get("farbe", "#5E6B7A") for name, daten in (raw.get("bloecke") or {}).items()}
    classes = {}
    for name, data in raw["asset_classes"].items():
        classes[name] = AssetClassConfig(name=name, **data)
        # Ein Block, den es nicht gibt, liesse die Klasse still von der Seite fallen.
        if bloecke and classes[name].block not in bloecke:
            raise ValueError(f"Asset class '{name}' names block {classes[name].block!r}; "
                             f"valid blocks: {list(bloecke)}")

    return AssetClassRegistry(classes, bloecke)


@lru_cache(maxsize=1)
def get_asset_class_registry(path: str = _DEFAULT_CONFIG_PATH) -> AssetClassRegistry:
    """Cached singleton — use this in application code."""
    return load_asset_classes(path)
