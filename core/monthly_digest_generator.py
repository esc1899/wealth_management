"""
Monthly digest generator — builds a deterministic Markdown summary for a portfolio month.

Sections:
  1. Performance summary (top movers, total portfolio delta)
  2. Checker verdicts (SC/FA/CG analyses created this month)
  3. Macro snapshot (from cached macro_context if available)
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timezone
from typing import List, Optional

from core.monthly_attribution import compute_monthly_attribution, AttributionMonthRow


_MONTH_NAMES_DE = {
    1: "Januar", 2: "Februar", 3: "März", 4: "April",
    5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}

_AGENT_LABELS = {
    "storychecker": "Storychecker",
    "fundamental_analyzer": "Fundamental-Analyse",
    "consensus_gap": "Consensus Gap",
}


def generate_monthly_digest(
    valuations,
    analyses_repo,
    app_config_repo,
    year: int,
    month: int,
    market_repo=None,
    today=None,
    wealth_repo=None,
) -> str:
    """
    Generate a Markdown digest for the given month.

    Args:
        valuations: list[PortfolioValuation] — current portfolio state
        analyses_repo: PositionAnalysesRepository
        app_config_repo: AppConfigRepository (for macro snapshot)
        year, month: target period
        market_repo: MarketDataRepository (needed for attribution; optional)
    """
    month_label = f"{_MONTH_NAMES_DE[month]} {year}"
    month_key = f"{year:04d}-{month:02d}"
    month_start = date(year, month, 1).isoformat()
    month_end = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
    now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    lines: List[str] = [
        f"# Monatsdigest {month_label}",
        f"",
        f"_Generiert am {now_str}_",
        f"",
    ]

    # ------------------------------------------------------------------ #
    # Section 1: Performance                                               #
    # ------------------------------------------------------------------ #
    lines += ["## Performance", ""]

    attribution_rows: List[AttributionMonthRow] = []
    if market_repo is not None:
        try:
            attribution_rows = compute_monthly_attribution(valuations, market_repo, year, month, today=today, wealth_repo=wealth_repo)
        except Exception:
            pass

    if attribution_rows:
        total_contribution = sum(r.contribution_eur for r in attribution_rows)
        rows_with_data = [r for r in attribution_rows if r.delta_pct is not None]
        total_start = sum(
            r.contribution_eur / (r.delta_pct / 100)
            for r in rows_with_data
            if r.delta_pct and r.delta_pct != 0
        )
        total_pct = (total_contribution / total_start * 100) if total_start > 0 else None

        sign = "+" if total_contribution >= 0 else ""
        pct_str = f"{total_pct:+.1f}%" if total_pct is not None else "n/a"
        lines.append(f"**Portfolio gesamt:** {pct_str} ({sign}{total_contribution:,.0f}€)")
        lines.append("")

        winners = sorted(rows_with_data, key=lambda r: r.contribution_eur, reverse=True)[:3]
        losers = sorted(rows_with_data, key=lambda r: r.contribution_eur)[:3]

        if winners:
            w_parts = [f"{r.symbol} {r.delta_pct:+.1f}%" for r in winners if r.contribution_eur > 0]
            if w_parts:
                lines.append(f"**Beste Beiträge:** {', '.join(w_parts)}")
        if losers:
            l_parts = [f"{r.symbol} {r.delta_pct:+.1f}%" for r in losers if r.contribution_eur < 0]
            if l_parts:
                lines.append(f"**Schwächste Beiträge:** {', '.join(l_parts)}")

        total_div = sum(r.dividend_contribution_eur for r in attribution_rows)
        if total_div > 0:
            lines.append(f"**Geschätzte Dividenden:** +{total_div:,.0f}€ _(Jahresdividende ÷ 12, aktuelle Rate)_")
        lines.append("")
    else:
        lines += ["_Keine historischen Preisdaten für diesen Monat verfügbar._", ""]

    # ------------------------------------------------------------------ #
    # Section 2: Checker-Verdicts                                          #
    # ------------------------------------------------------------------ #
    lines += ["## Checker-Verdicts", ""]

    try:
        all_analyses = _get_analyses_for_month(analyses_repo, month_start, month_end)
        if all_analyses:
            by_agent: dict[str, list] = {}
            for a in all_analyses:
                by_agent.setdefault(a["agent"], []).append(a)

            for agent_key, label in _AGENT_LABELS.items():
                agent_analyses = by_agent.get(agent_key, [])
                if not agent_analyses:
                    continue
                verdict_counts: dict[str, int] = {}
                for a in agent_analyses:
                    v = a.get("verdict") or "unbekannt"
                    verdict_counts[v] = verdict_counts.get(v, 0) + 1
                verdict_parts = [f"{v}: {c}" for v, c in sorted(verdict_counts.items())]
                lines.append(f"**{label}:** {len(agent_analyses)} Analysen — {', '.join(verdict_parts)}")
            lines.append("")
        else:
            lines += [f"_Keine Checker-Analysen im {month_label}._", ""]
    except Exception:
        lines += ["_Verdicts nicht verfügbar._", ""]

    # ------------------------------------------------------------------ #
    # Section 3: Makro-Snapshot                                            #
    # ------------------------------------------------------------------ #
    lines += ["## Makro-Snapshot", ""]

    try:
        cached = app_config_repo.get_json("macro_context")
        if cached:
            parts = []
            if cached.get("vix") is not None:
                parts.append(f"VIX: {cached['vix']:.1f}")
            if cached.get("eur_usd") is not None:
                parts.append(f"EUR/USD: {cached['eur_usd']:.3f}")
            if cached.get("gold_eur") is not None:
                parts.append(f"Gold: {cached['gold_eur']:,.0f}€/oz")
            if cached.get("dax_change_pct") is not None:
                parts.append(f"DAX Tageschange: {cached['dax_change_pct']:+.1f}%")
            if parts:
                lines.append(" | ".join(parts))
                try:
                    ts = datetime.fromisoformat(cached["fetched_at"])
                    lines.append(f"_(Stand: {ts.strftime('%d.%m.%Y %H:%M')})_")
                except Exception:
                    pass
            else:
                lines.append("_Keine Makro-Daten verfügbar._")
        else:
            lines.append("_Keine Makro-Daten verfügbar._")
    except Exception:
        lines.append("_Makro-Daten nicht verfügbar._")

    lines.append("")
    return "\n".join(lines)


def _get_analyses_for_month(analyses_repo, month_start: str, month_end: str) -> list:
    """Query position_analyses rows created within the given month."""
    try:
        rows = analyses_repo._conn.execute(
            """
            SELECT agent, verdict FROM position_analyses
            WHERE created_at BETWEEN ? AND ?
            """,
            (month_start + "T00:00:00", month_end + "T23:59:59"),
        ).fetchall()
        return [{"agent": r["agent"], "verdict": r["verdict"]} for r in rows]
    except Exception:
        return []
