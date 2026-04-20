"""
Unit tests for AssetClassConfig / AssetClassRegistry.
"""

import os
import textwrap
import pytest

from core.asset_class_config import load_asset_classes, AssetClassConfig


YAML_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "asset_classes.yaml"
)


# ------------------------------------------------------------------
# Load from real config file
# ------------------------------------------------------------------

class TestLoadRealConfig:
    def setup_method(self):
        self.registry = load_asset_classes(YAML_PATH)

    def test_known_classes_present(self):
        assert "Aktie" in self.registry.all_names()
        assert "Edelmetall" in self.registry.all_names()
        assert "Aktienfonds" in self.registry.all_names()
        assert "Immobilienfonds" in self.registry.all_names()

    def test_aktie_investment_type(self):
        assert self.registry.get("Aktie").investment_type == "Wertpapiere"

    def test_edelmetall_investment_type(self):
        assert self.registry.get("Edelmetall").investment_type == "Rohstoffe"

    def test_immobilienfonds_investment_type(self):
        assert self.registry.get("Immobilienfonds").investment_type == "Immobilien"

    def test_investment_types_unique(self):
        types = self.registry.investment_types()
        assert len(types) == len(set(types))

    def test_investment_types_contains_all_three(self):
        types = self.registry.investment_types()
        assert "Wertpapiere" in types
        assert "Immobilien" in types
        assert "Rohstoffe" in types

    def test_classes_for_wertpapiere(self):
        classes = self.registry.classes_for_type("Wertpapiere")
        assert "Aktie" in classes
        assert "Aktienfonds" in classes

    def test_edelmetall_unit_options(self):
        cfg = self.registry.get("Edelmetall")
        assert "Troy Oz" in cfg.unit_options
        assert "g" in cfg.unit_options

    def test_aktie_requires_ticker(self):
        assert self.registry.get("Aktie").requires_ticker is True

    def test_field_visibility(self):
        cfg = self.registry.get("Aktie")
        assert cfg.is_field_visible("isin") is True
        assert cfg.is_field_visible("extra_data") is False

    def test_edelmetall_unit_field_visible(self):
        cfg = self.registry.get("Edelmetall")
        assert cfg.is_field_visible("unit") is True

    def test_require_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown asset class"):
            self.registry.require("Unbekannt")

    def test_get_unknown_returns_none(self):
        assert self.registry.get("Unbekannt") is None


# ------------------------------------------------------------------
# Validation of YAML structure
# ------------------------------------------------------------------

class TestYAMLValidation:
    def _write_yaml(self, tmp_path, content: str) -> str:
        p = tmp_path / "asset_classes.yaml"
        p.write_text(textwrap.dedent(content))
        return str(p)

    def test_missing_top_level_key_raises(self, tmp_path):
        path = self._write_yaml(tmp_path, """
            classes:
              Aktie:
                investment_type: Wertpapiere
        """)
        with pytest.raises(ValueError, match="asset_classes"):
            load_asset_classes(path)

    def test_unknown_visible_field_raises(self, tmp_path):
        path = self._write_yaml(tmp_path, """
            asset_classes:
              Test:
                investment_type: Wertpapiere
                default_unit: Stück
                visible_fields: [ticker, nonexistent_field]
                price_source: yfinance
                requires_ticker: true
        """)
        with pytest.raises(Exception):
            load_asset_classes(path)

    def test_minimal_valid_class(self, tmp_path):
        path = self._write_yaml(tmp_path, """
            asset_classes:
              MyClass:
                investment_type: Renten
                default_unit: Stück
                visible_fields: [ticker, quantity]
                price_source: yfinance
        """)
        reg = load_asset_classes(path)
        assert reg.get("MyClass") is not None
        assert reg.get("MyClass").investment_type == "Renten"
