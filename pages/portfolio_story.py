"""
Portfolio Story — portfolio-level narrative, alignment check, performance review.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import streamlit as st

from core.currency import symbol
from core.i18n import t
from core.storage.models import PortfolioStory
from state import (
    get_analyses_repo,
    get_market_agent,
    get_market_repo,
    get_portfolio_story_agent,
    get_portfolio_story_repo,
    get_positions_repo,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Helper functions (must be defined early)
# ──────────────────────────────────────────────────────────────────────


def _verdict_icon(verdict: str) -> str:
    """Return emoji icon for a verdict."""
    mapping = {
        "intact": "🟢",
        "gemischt": "🟡",
        "gefaehrdet": "🔴",
        "on_track": "🟢",
        "achtung": "🟡",
        "kritisch": "🔴",
        "stabil": "🟢",
        "instabil": "🔴",
        "unknown": "⚪",
    }
    return mapping.get(verdict.lower(), "⚪")


def _verdict_icon_short(verdict: str) -> str:
    """Return just the emoji for a verdict (for compact display)."""
    return _verdict_icon(verdict)


def _fit_icon(fit_verdict: str) -> str:
    """Return emoji icon for a position fit verdict."""
    mapping = {
        "stärkt": "🟢",
        "schwächt": "🔴",
        "neutral": "⚪",
    }
    return mapping.get(fit_verdict.lower(), "⚪")


st.set_page_config(page_title="Portfolio Story", page_icon="📖", layout="wide")
st.title("📖 Portfolio Story")
st.caption("Dein langfristiges Anlage-Narrativ und Alignment-Check")

# ──────────────────────────────────────────────────────────────────────
# Load data
# ──────────────────────────────────────────────────────────────────────

repo = get_portfolio_story_repo()
positions_repo = get_positions_repo()
market_repo = get_market_repo()
analyses_repo = get_analyses_repo()
agent = get_portfolio_story_agent()

current_story = repo.get_current()
latest_analysis = repo.get_latest_analysis()


# ──────────────────────────────────────────────────────────────────────
# Section 1: Define / Update Portfolio Story
# ──────────────────────────────────────────────────────────────────────

st.subheader("1️⃣ Portfolio Story — Definieren & Updaten")

with st.form("portfolio_story_form", clear_on_submit=False):
    col1, col2 = st.columns(2)
    with col1:
        story_text = st.text_area(
            "Dein Portfolio-Narrativ",
            value=current_story.story if current_story else "",
            height=150,
            help="Deine langfristigen Ziele, Zeithorizont, Prioritäten, Lebens-Meilensteine",
        )
        target_year = st.number_input(
            "Ziel-Jahr",
            value=current_story.target_year if current_story else 2040,
            min_value=2025,
            max_value=2100,
            step=1,
        )

    with col2:
        liquidity_need = st.text_area(
            "Liquiditätsbedarf",
            value=current_story.liquidity_need if current_story else "",
            height=100,
            placeholder="z.B. 2028: Immobilienkauf ~150k EUR",
        )
        priority = st.selectbox(
            "Priorität",
            options=["Wachstum", "Einkommen", "Sicherheit", "Gemischt"],
            index=(
                ["Wachstum", "Einkommen", "Sicherheit", "Gemischt"].index(
                    current_story.priority
                )
                if current_story
                else 3
            ),
        )

    col_save, col_draft = st.columns([1, 1])
    with col_save:
        save_clicked = st.form_submit_button("💾 Speichern", use_container_width=True)
    with col_draft:
        draft_clicked = st.form_submit_button("🤖 AI-Vorschlag", use_container_width=True)

    if save_clicked and story_text.strip():
        new_story = PortfolioStory(
            id=current_story.id if current_story else None,
            story=story_text.strip(),
            target_year=int(target_year),
            liquidity_need=liquidity_need.strip() or None,
            priority=priority,
            created_at=current_story.created_at if current_story else datetime.now(),
            updated_at=datetime.now(),
        )
        saved = repo.save(new_story)
        st.success("✅ Portfolio Story gespeichert!")
        st.rerun()

    if draft_clicked:
        # Generate AI draft with current form inputs
        with st.spinner("🤖 Generiere AI-Vorschlag…"):
            portfolio = positions_repo.get_portfolio()
            if portfolio:
                positions_summary = "\n".join(
                    [f"- {p.name} ({p.ticker or 'n/a'}): {p.asset_class}" for p in portfolio]
                )
            else:
                positions_summary = "(leeres Portfolio)"

            draft = asyncio.run(
                agent.generate_story_draft(
                    positions_summary=positions_summary,
                    existing_story=current_story,
                    story_text=story_text.strip() if story_text.strip() else None,
                    target_year=int(target_year),
                    liquidity_need=liquidity_need.strip() if liquidity_need.strip() else None,
                    priority=priority,
                )
            )
            st.session_state["_story_draft"] = draft
            st.rerun()

# Show draft if available
if "_story_draft" in st.session_state and st.session_state["_story_draft"]:
    with st.info("🤖 **AI-Vorschlag** (in das Feld oben kopieren)"):
        st.code(st.session_state["_story_draft"])
    if st.button("❌ Verwerfen"):
        del st.session_state["_story_draft"]
        st.rerun()

st.divider()

# ──────────────────────────────────────────────────────────────────────
# Section 2: Story Check + Performance Check
# ──────────────────────────────────────────────────────────────────────

st.subheader("2️⃣ Checks — Ausrichtung & Performance")

if not current_story:
    st.warning("⚠️ Bitte definiere zuerst deine Portfolio Story oben.")
else:
    col_check, col_history = st.columns([2, 1])

    with col_check:
        if st.button("🔄 Story-Check durchführen", use_container_width=True):
            with st.spinner("Analysiere Portfolio gegen Story…"):
                # Build portfolio snapshot
                portfolio = positions_repo.get_portfolio()
                watchlist = positions_repo.get_watchlist()

                if portfolio:
                    from agents.rebalance_agent import RebalanceAgent
                    # Reuse _build_portfolio_context from rebalance agent
                    # For now, create a simple snapshot
                    snapshot_lines = ["**Portfolio Snapshot**\n"]
                    for p in portfolio:
                        ticker_str = f" ({p.ticker})" if p.ticker else ""
                        snapshot_lines.append(
                            f"- {p.name}{ticker_str} [{p.asset_class}]"
                        )
                    portfolio_snapshot = "\n".join(snapshot_lines)
                else:
                    portfolio_snapshot = "(Leeres Portfolio)"

                # Build dividend snapshot
                valuations = get_market_agent().get_portfolio_valuation()
                dividend_lines = []
                for v in valuations:
                    if v.annual_dividend_eur and v.annual_dividend_eur > 0:
                        dividend_lines.append(
                            f"- {v.name}: {symbol()}{v.annual_dividend_eur:.0f}/Jahr "
                            f"({v.dividend_yield_pct*100:.1f}%)"
                        )
                dividend_snapshot = "\n".join(dividend_lines) or "(Keine Dividenden)"

                # Compute metrics (simplified)
                total_value = sum(v.current_value_eur or 0 for v in valuations)
                total_cost = sum(v.cost_basis_eur or 0 for v in valuations)
                total_pnl = total_value - total_cost
                total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
                total_dividend = sum(v.annual_dividend_eur or 0 for v in valuations)
                dividend_yield = (total_dividend / total_value * 100) if total_value > 0 else 0

                from agents.portfolio_story_agent import PortfolioMetrics

                metrics = PortfolioMetrics(
                    total_value_eur=total_value,
                    total_pnl_eur=total_pnl,
                    total_pnl_pct=total_pnl_pct,
                    total_annual_dividend_eur=total_dividend,
                    portfolio_dividend_yield_pct=dividend_yield,
                    josef_aktien_pct=33.3,  # Placeholder
                    josef_renten_pct=33.3,
                    josef_rohstoffe_pct=33.3,
                    positions_count=len(portfolio),
                )

                # Build verdicts dict for position analysis
                pos_ids = [p.id for p in portfolio if p.id]
                verdicts_by_position = {}
                if pos_ids:
                    vs = analyses_repo.get_latest_bulk(pos_ids, "storychecker")
                    vf = analyses_repo.get_latest_bulk(pos_ids, "fundamental")
                    vc = analyses_repo.get_latest_bulk(pos_ids, "consensus_gap")
                    for pos_id in pos_ids:
                        verdicts_by_position[pos_id] = {
                            "storychecker": vs.get(pos_id),
                            "fundamental": vf.get(pos_id),
                            "consensus_gap": vc.get(pos_id),
                        }

                # Run analysis (portfolio-level + position-level in parallel)
                async def run_checks():
                    analysis, position_fits = await asyncio.gather(
                        agent.analyze(
                            story=current_story,
                            portfolio_snapshot=portfolio_snapshot,
                            metrics=metrics,
                            dividend_snapshot=dividend_snapshot,
                            inflation_rate=None,  # TODO: fetch from Tavily
                        ),
                        agent.analyze_positions(
                            story=current_story,
                            positions=portfolio,
                            verdicts=verdicts_by_position,
                        )
                    )
                    return analysis, position_fits

                analysis, position_fits = asyncio.run(run_checks())

                # Save analysis and position fits
                saved_analysis = repo.save_analysis(analysis)
                if position_fits:
                    repo.save_position_fits(position_fits)

                st.success("✅ Story-Check durchgeführt!")
                st.rerun()

    with col_history:
        st.caption("Bisherige Checks")
        history = repo.get_analysis_history(limit=5)
        for h in history:
            date_str = h.created_at.strftime("%d.%m.%Y")
            verdict_icon = _verdict_icon(h.verdict)
            st.text(f"{verdict_icon} {date_str}")

    if latest_analysis:
        st.divider()

        # Display analysis
        st.markdown(f"### Aktuellste Analyse — {latest_analysis.created_at.strftime('%d.%m.%Y %H:%M')}")

        # Story Check
        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(
                    f"**Story-Urteil:** {_verdict_icon(latest_analysis.verdict)} {latest_analysis.verdict.title()}"
                )
                st.markdown(f"_{latest_analysis.summary}_")
            with col2:
                if st.button("▼ Details", key="story_details"):
                    st.session_state["_expand_story"] = not st.session_state.get(
                        "_expand_story", False
                    )

            if st.session_state.get("_expand_story"):
                st.markdown("---")
                # Extract story sections from full_text
                st.caption("Aus der vollständigen Analyse:")
                st.text(latest_analysis.full_text)

        # Performance Check
        with st.container(border=True):
            st.markdown(
                f"**Performance-Urteil:** {_verdict_icon(latest_analysis.perf_verdict)} {latest_analysis.perf_verdict.title()}"
            )
            st.markdown(f"_{latest_analysis.perf_summary}_")

        # Stability Check
        with st.container(border=True):
            st.markdown(
                f"**Stabilitäts-Urteil:** {_verdict_icon(latest_analysis.stability_verdict)} {latest_analysis.stability_verdict.title()}"
            )
            st.markdown(f"_{latest_analysis.stability_summary}_")

st.divider()

# ──────────────────────────────────────────────────────────────────────
# Helpers (define early so they can be used later)
# ──────────────────────────────────────────────────────────────────────


def _verdict_icon(verdict: str) -> str:
    """Return emoji icon for a verdict."""
    mapping = {
        "intact": "🟢",
        "gemischt": "🟡",
        "gefaehrdet": "🔴",
        "on_track": "🟢",
        "achtung": "🟡",
        "kritisch": "🔴",
        "stabil": "🟢",
        "instabil": "🔴",
        "unknown": "⚪",
    }
    return mapping.get(verdict.lower(), "⚪")


def _verdict_icon_short(verdict: str) -> str:
    """Return just the emoji for a verdict (for compact display)."""
    return _verdict_icon(verdict)


# ──────────────────────────────────────────────────────────────────────
# Section 3: Investment Overview — How each position fits the story
# ──────────────────────────────────────────────────────────────────────

st.subheader("3️⃣ Einzelne Investitionen — Passung zur Portfolio Story")

portfolio = positions_repo.get_portfolio()
if not portfolio:
    st.info("ℹ️ Portfolio ist leer.")
else:
    # Get all verdicts and position fits
    pos_ids = [p.id for p in portfolio if p.id]
    verdicts_story = analyses_repo.get_latest_bulk(pos_ids, "storychecker")
    verdicts_fundamental = analyses_repo.get_latest_bulk(pos_ids, "fundamental")
    verdicts_consensus = analyses_repo.get_latest_bulk(pos_ids, "consensus_gap")
    position_fits = repo.get_latest_position_fits(pos_ids)

    # Filter: only show positions with at least one verdict or position fit
    positions_with_verdicts = [
        pos for pos in portfolio
        if pos.id and (
            verdicts_story.get(pos.id)
            or verdicts_fundamental.get(pos.id)
            or verdicts_consensus.get(pos.id)
            or position_fits.get(pos.id)
        )
    ]

    if not positions_with_verdicts:
        st.info("ℹ️ Keine Positionen mit Analysen gefunden.")
    else:
        # Sort by worst verdict (simplified: just list them)
        for pos in positions_with_verdicts:
            vs = verdicts_story.get(pos.id)
            vf = verdicts_fundamental.get(pos.id)
            vc = verdicts_consensus.get(pos.id)
            pf = position_fits.get(pos.id)

            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 1.5, 1.5])

                with col1:
                    st.markdown(
                        f"**{pos.ticker or pos.name}** — {pos.name}\n"
                        f"_{pos.asset_class}_"
                    )

                with col2:
                    # Position fit badge (story alignment)
                    if pf:
                        fit_emoji = _fit_icon(pf.fit_verdict)
                        fit_label = pf.fit_verdict.capitalize()
                        st.markdown(f"{fit_emoji} **{fit_label}**\n_{pf.fit_summary}_")
                    else:
                        st.caption("_(Story-Fit ausstehend)_")

                with col3:
                    # Show 3 verdicts inline
                    verdict_str = ""
                    if vs:
                        verdict_str += f"{_verdict_icon_short(vs.verdict)} "
                    if vf:
                        verdict_str += f"{_verdict_icon_short(vf.verdict)} "
                    if vc:
                        verdict_str += f"{_verdict_icon_short(vc.verdict)}"

                    st.text(verdict_str.strip() or "⚪")

                # Expander for full details
                with st.expander("Vollständige Details"):
                    if vs:
                        st.markdown(
                            f"**🟢/🟡/🔴 Story-Check**\n"
                            f"{_verdict_icon(vs.verdict)} **{vs.verdict.title()}**\n\n"
                            f"> {vs.summary}"
                        )
                    if vf:
                        st.markdown(
                            f"**Fundamentalbewertung**\n"
                            f"{_verdict_icon(vf.verdict)} **{vf.verdict.title()}**\n\n"
                            f"> {vf.summary}"
                        )
                    if vc:
                        st.markdown(
                            f"**Konsens-Lücke**\n"
                            f"{_verdict_icon(vc.verdict)} **{vc.verdict.title()}**\n\n"
                            f"> {vc.summary}"
                        )
