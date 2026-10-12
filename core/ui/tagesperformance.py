"""Die Tagesperformance des Depots: ein Satz, darunter die Balken je Titel.

Eine Anzeige fuer zwei Seiten (12.10.2026): oben auf der Depot-Startseite, weil Erik dort
taeglich zuerst nach dem Tag schaut, und auf der Analyse vor Monat und Jahr. Beide rufen
dieselbe Funktion, damit nirgends eine zweite Zahl entsteht. Gelesen wird die Bewertung aus der
Datenbank (``MarketDataAgent.get_portfolio_valuation``); Kurse holt hier nichts -- die haelt
der stuendliche Kachel-Job frisch, und der Satz sagt, von wann sie sind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from core.currency import symbol
from core.i18n import fmt_dt, t
from core.symbol_aggregation import aggregate_day_pnl
from core.ui.charts import bar_label, style_bar_chart


@dataclass
class Summen:
    analyse: float          # Depot mit Ticker, ohne ausgeschlossene Positionen
    vermoegen: float        # das ganze Depot, wie in der Vermoegenshistorie
    ausgeschlossen: float
    ausgeschlossen_zahl: int


def summen(valuations) -> Summen:
    depot = [v for v in valuations if v.in_portfolio and v.current_value_eur]
    vermoegen = sum(v.current_value_eur for v in depot)
    analyse = sum(v.current_value_eur for v in depot if not getattr(v, "analysis_excluded", False))
    zahl = sum(1 for v in depot if getattr(v, "analysis_excluded", False) and v.current_value_eur > 0)
    return Summen(analyse, vermoegen, vermoegen - analyse, zahl)


def _euro(wert: float, vorzeichen: bool = False) -> str:
    text = f"{wert:+,.2f}" if vorzeichen else f"{wert:,.0f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def kursstand(letzter_abruf: Optional[datetime]) -> str:
    """"Kurse vom 12.10. 10:40" -- der Abruf ist naives UTC, angezeigt in Ortszeit."""
    if letzter_abruf is None:
        return t("analysis.no_price_data")
    return f"{t('analysis.prices_as_of')} {fmt_dt(letzter_abruf.replace(tzinfo=timezone.utc).astimezone())}"


def zeigen(valuations, s: Optional[Summen] = None, hoehe: Optional[int] = None) -> None:
    """Satz und Balken; ohne Tageskurse ein Hinweis statt der Balken."""
    s = s or summen(valuations)
    spalte_eur, spalte_pct = t("analysis.day_pnl_col"), t("analysis.day_pnl_pct_col")
    # Erst je Symbol zusammenfassen -- derselbe Titel in zwei Depots ist ein Balken.
    zeilen = [{"Symbol": a.symbol, spalte_eur: a.day_pnl_eur, spalte_pct: a.day_pnl_pct}
              for a in aggregate_day_pnl(valuations)]
    if not zeilen:
        st.info(t("analysis.no_day_pnl"))
        return

    df = pd.DataFrame(zeilen).sort_values(spalte_eur)
    tag = df[spalte_eur].sum()
    teile = []
    if s.analyse - tag:
        teile.append(f"{tag / (s.analyse - tag) * 100:+.2f}% Analyse")
    if s.vermoegen - tag:
        teile.append(f"{tag / (s.vermoegen - tag) * 100:+.2f}% Gesamt")
    st.markdown(f"**{t('tagesperformance.heute')}: {symbol()}{_euro(tag, vorzeichen=True)} — "
                f"{' · '.join(teile)}**")

    fig = px.bar(
        df, x="Symbol", y=spalte_eur,
        color=spalte_eur,
        color_continuous_scale=["red", "lightgrey", "green"],
        color_continuous_midpoint=0,
        text=[bar_label(r[spalte_eur], r[spalte_pct]) for _, r in df.iterrows()],
    )
    style_bar_chart(fig)
    if hoehe:
        fig.update_layout(height=hoehe)
    st.plotly_chart(fig)
