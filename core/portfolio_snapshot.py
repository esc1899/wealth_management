"""
Portfolio snapshot for local LLM prompts.

Renders the portfolio as text for the Ollama agents (Portfolio Checker,
Portfolio Robustness). Local-only — the snapshot carries names, values and
weights and must never be handed to a cloud agent.

Positions are matched to their valuation by `position_id`, not by symbol:
tickerless positions (Immobilie, Festgeld, Renten) carry a name-derived
pseudo-symbol truncated to 10 characters, and a ticker held in two depots
appears twice. A symbol-keyed lookup silently valued all of those at 0€.
"""

from __future__ import annotations

from typing import Optional


def build_portfolio_snapshot(
    positions,
    valuations,
    with_dividends: bool = True,
) -> str:
    """Render positions with value, portfolio weight and expected payouts.

    Args:
        positions: list[Position] — the portfolio, in display order
        valuations: list[PortfolioValuation] — from MarketDataAgent
        with_dividends: include per-position and total annual payouts. Needed
            whenever the story's goals are income-based, otherwise the model
            has to guess the numbers it is asked to judge.
    """
    by_pos_id = {v.position_id: v for v in valuations if v.position_id is not None}

    def _value(p) -> Optional[float]:
        v = by_pos_id.get(p.id) if p.id else None
        return v.current_value_eur if v and v.current_value_eur else None

    total = sum(v for v in (_value(p) for p in positions) if v) or 0.0

    lines = [
        "## Portfolio",
        f"Gesamtwert: {total:,.0f}€ ({len(positions)} Positionen)",
        "",
    ]

    for p in positions:
        val = _value(p)
        ticker = p.ticker or "kein Ticker"
        if val:
            weight = (val / total * 100) if total > 0 else 0.0
            line = f"- {p.name} ({ticker}, {p.asset_class}): {val:,.0f}€ — {weight:.1f}%"
        else:
            line = f"- {p.name} ({ticker}, {p.asset_class}): Wert unbekannt"

        if with_dividends:
            v = by_pos_id.get(p.id) if p.id else None
            payout = v.annual_dividend_eur if v else None
            if payout:
                line += f" | Dividende/Zins p.a.: {payout:,.0f}€"

        lines.append(line)

    if with_dividends:
        total_payout = sum(
            by_pos_id[p.id].annual_dividend_eur or 0.0
            for p in positions
            if p.id in by_pos_id
        )
        lines += [
            "",
            f"Erwartete Ausschüttungen gesamt: {total_payout:,.0f}€ p.a. "
            "(aus hinterlegten Dividenden-/Zinssätzen berechnet — diesen Wert "
            "verwenden, nicht schätzen)",
        ]

    return "\n".join(lines) + "\n"
