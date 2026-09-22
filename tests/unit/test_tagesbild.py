"""Das Tagesbild (core/tagesbild.py): eine Rechnung für Kachel und Dashboard."""

from dataclasses import dataclass
from typing import Optional

from core.tagesbild import groesste_bewegung, prozent, tagesbild


@dataclass
class FakeValuation:
    symbol: str
    name: str = ""
    day_pnl_eur: Optional[float] = None
    current_value_eur: Optional[float] = None
    in_portfolio: bool = True


class TestProzent:
    def test_deutsch_mit_vorzeichen(self):
        assert prozent(0.4212) == "+0,42 %"
        assert prozent(-1.076) == "−1,08 %"     # typografisches Minus
        assert prozent(0.001) == "±0,00 %"


class TestTagesbild:
    def test_summenformel_der_analyse_und_groesste_bewegung(self):
        vals = [
            FakeValuation("SAP", "SAP SE", day_pnl_eur=20.0, current_value_eur=1020.0),     # Vortag 1000
            FakeValuation("ALV", "Allianz", day_pnl_eur=-10.0, current_value_eur=990.0),    # Vortag 1000
            FakeValuation("GOLD", "Gold", day_pnl_eur=None, current_value_eur=500.0),       # ohne Tageskurs
            FakeValuation("WL", "Watch", day_pnl_eur=99.0, current_value_eur=100.0, in_portfolio=False),
        ]
        b = tagesbild(vals)
        assert b.prozent == 0.5                      # 10 / 2000
        assert (b.positionen, b.ohne_tageskurs) == (3, 1)
        assert (b.groesste_name, b.groesste_prozent) == ("SAP SE", 2.0)
        assert groesste_bewegung(b) == "Größte Bewegung: SAP SE +2,00 %"

    def test_zweimal_gehalten_ist_eine_bewegung(self):
        # derselbe Ticker in zwei Depots: ein Symbol, Prozent aus den Summen
        vals = [
            FakeValuation("SAP", "SAP SE", day_pnl_eur=10.0, current_value_eur=1010.0),
            FakeValuation("SAP", "SAP SE", day_pnl_eur=30.0, current_value_eur=1030.0),
        ]
        b = tagesbild(vals)
        assert b.groesste_prozent == 2.0 and b.prozent == 2.0

    def test_ohne_tageskurse_keine_null(self):
        b = tagesbild([FakeValuation("A", "A", current_value_eur=95.0)])
        assert b.prozent is None and b.groesste_name is None and groesste_bewegung(b) is None
        assert (b.positionen, b.ohne_tageskurs) == (1, 1)

    def test_ohne_namen_steht_das_symbol(self):
        b = tagesbild([FakeValuation("ALV", day_pnl_eur=-5.0, current_value_eur=95.0)])
        assert groesste_bewegung(b) == "Größte Bewegung: ALV −5,00 %"
