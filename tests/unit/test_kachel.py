"""Die Kachel für die Startseite des Mac mini (scripts/kachel.py): Tagesveränderung in
Prozent aus denselben Bewertungen wie die Analyse-Seite, kein Betrag in Euro."""

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import kachel as k  # noqa: E402


@dataclass
class FakeValuation:
    symbol: str
    name: str = ""
    day_pnl_eur: Optional[float] = None
    current_value_eur: Optional[float] = None
    in_portfolio: bool = True


class TestKachel:
    def test_tagesveraenderung_ist_die_summenformel_der_analyse(self):
        vals = [
            FakeValuation("SAP", "SAP SE", day_pnl_eur=20.0, current_value_eur=1020.0),     # Vortag 1000
            FakeValuation("ALV", "Allianz", day_pnl_eur=-10.0, current_value_eur=990.0),    # Vortag 1000
            FakeValuation("GOLD", "Gold", day_pnl_eur=None, current_value_eur=500.0),       # ohne Tageskurs
            FakeValuation("WL", "Watch", day_pnl_eur=99.0, current_value_eur=100.0, in_portfolio=False),
        ]
        d = k.kachel(vals, stand=datetime(2026, 9, 21, 12, 40))
        assert d["zeilen"][0] == {"text": "+0,50 % heute", "zustand": "gut"}   # 10 / 2000
        assert d["zeilen"][1:] == ["3 Positionen", "1 ohne Tageskurs"]
        assert d["satz"] == "Größte Bewegung: SAP SE +2,00 %"
        assert d["stand"].startswith("2026-09-21T") and "+" in d["stand"][10:]   # naives UTC -> Ortszeit
        assert "€" not in json.dumps(d, ensure_ascii=False)

    def test_minus_ist_schlecht_und_ohne_kurse_keine_null(self):
        d = k.kachel([FakeValuation("A", "A", day_pnl_eur=-5.0, current_value_eur=95.0)],
                     stand=datetime.now(timezone.utc))
        assert d["zeilen"][0] == {"text": "−5,00 % heute", "zustand": "schlecht"}
        assert d["zeilen"][1] == "1 Position"
        leer = k.kachel([FakeValuation("A", "A", current_value_eur=95.0)], stand=datetime.now(timezone.utc))
        assert leer["zeilen"] == ["keine Tageskurse", "1 Position"] and leer["satz"] is None

    def test_ohne_startseite_passiert_nichts(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("DIENSTE_HOME", str(tmp_path / "gibt-es-nicht"))
        assert k.main([]) == 0
        assert "nichts zu tun" in capsys.readouterr().out
