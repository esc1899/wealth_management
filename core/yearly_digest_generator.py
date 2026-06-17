"""
Yearly digest generator — builds a deterministic Markdown summary for a portfolio year.

Sections:
  1. Performance summary (top movers YTD, total portfolio delta)
  2. Checker verdicts (SC/FA/CG analyses created during the year)
  3. Monthly performance overview (contribution per month from monthly_digests)
  4. Macro snapshot (from cached macro_context if available)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from core.yearly_attribution import compute_yearly_attribution, AttributionYearRow


_MONTH_NAMES_DE = {
    1: "Jan", 2: "Feb", 3: "Mär", 4: "Apr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Okt", 11: "Nov", 12: "Dez",
}

_AGENT_LABELS = {
    "storychecker": "Storychecker",
    "fundamental_analyzer": "Fundamental-Analyse",
    "consensus_gap": "Consensus Gap",
}


def generate_yearly_digest(
    valuations,
    analyses_repo,
    app_config_repo,
    year: int,
    market_repo=None,
    monthly_digest_repo=None,
    wealth_repo=None,
) -> str:
    """
    Generate a Markdown digest for the given year.

    Args:
        valuations: list[PortfolioValuation] — current portfolio state
        analyses_repo: PositionAnalysesRepository
        app_config_repo: AppConfigRepository (for macro snapshot)
        year: target year
        market_repo: MarketDataRepository (needed for attribution; optional)
        monthly_digest_repo: MonthlyDigestRepository (for monthly overview; optional)
    """
    year_label = str(year)
    year_start = f"{year:04d}-01-01"
    year_end = f"{year:04d}-12-31"
    now_str = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    lines: List[str] = [
        f"# Jahresdigest {year_label}",
        f"",
        f"_Generiert am {now_str}_",
        f"",
    ]

    # ------------------------------------------------------------------ #
    # Section 1: Performance                                               #
    # ------------------------------------------------------------------ #
    lines += ["## Performance", ""]

    attribution_rows: List[AttributionYearRow] = []
    if market_repo is not None:
        try:
            attribution_rows = compute_yearly_attribution(valuations, market_repo, year, wealth_repo=wealth_repo)
        except Exception:
            pass

    if attribution_rows:
        total_contribution = sum(r.contribution_eur for r in attribution_rows)
        total_start = sum(
            r.contribution_eur + (r.start_price_eur * r.quantity if r.unit != "g"
                                  else r.start_price_eur / 31.1035 * r.quantity)
            for r in attribution_rows
            if r.start_price_eur and r.quantity and r.delta_pct is not None
        )
        # Simpler: reconstruct start from contribution and delta
        rows_with_data = [r for r in attribution_rows if r.delta_pct is not None]
        total_start_v2 = sum(
            r.contribution_eur / (r.delta_pct / 100)
            for r in rows_with_data
            if r.delta_pct and r.delta_pct != 0
        )
        total_pct = (total_contribution / total_start_v2 * 100) if total_start_v2 > 0 else None

        sign = "+" if total_contribution >= 0 else ""
        pct_str = f"{total_pct:+.1f}%" if total_pct is not None else "n/a"
        lines.append(f"**Portfolio gesamt {year_label}:** {pct_str} ({sign}{total_contribution:,.0f}€)")
        lines.append("")

        winners = sorted(rows_with_data, key=lambda r: r.contribution_eur, reverse=True)[:5]
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
            lines.append(f"**Geschätzte Dividenden:** +{total_div:,.0f}€ _(aktuelle Jahresdividende, keine tatsächlichen Zahlungen)_")
        lines.append("")
    else:
        lines += ["_Keine historischen Preisdaten für dieses Jahr verfügbar._", ""]

    # ------------------------------------------------------------------ #
    # Section 2: Checker-Verdicts                                          #
    # ------------------------------------------------------------------ #
    lines += ["## Checker-Verdicts", ""]

    try:
        all_analyses = _get_analyses_for_year(analyses_repo, year_start, year_end)
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
            lines += [f"_Keine Checker-Analysen im Jahr {year_label}._", ""]
    except Exception:
        lines += ["_Verdicts nicht verfügbar._", ""]

    # ------------------------------------------------------------------ #
    # Section 3: Monatsübersicht                                           #
    # ------------------------------------------------------------------ #
    if monthly_digest_repo is not None:
        lines += ["## Monatsübersicht", ""]
        try:
            for m in range(1, 13):
                month_key = f"{year:04d}-{m:02d}"
                digest = monthly_digest_repo.get(month_key)
                if digest:
                    lines.append(f"- **{_MONTH_NAMES_DE[m]}**: Digest vorhanden ({digest.generated_at.strftime('%d.%m.')})")
                else:
                    lines.append(f"- **{_MONTH_NAMES_DE[m]}**: —")
            lines.append("")
        except Exception:
            lines += ["_Monatsübersicht nicht verfügbar._", ""]

    # ------------------------------------------------------------------ #
    # Section 4: Makro-Snapshot                                            #
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


def _get_analyses_for_year(analyses_repo, year_start: str, year_end: str) -> list:
    """Query position_analyses rows created within the given year."""
    try:
        rows = analyses_repo._conn.execute(
            """
            SELECT agent, verdict FROM position_analyses
            WHERE created_at BETWEEN ? AND ?
            """,
            (year_start + "T00:00:00", year_end + "T23:59:59"),
        ).fetchall()
        return [{"agent": r["agent"], "verdict": r["verdict"]} for r in rows]
    except Exception:
        return []
