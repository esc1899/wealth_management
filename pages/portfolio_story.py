"""
Portfolio Story — portfolio-level narrative, alignment check, performance review.
V2: Clean slate — only story & performance checks, no stability/cash checks.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import streamlit as st

from core.currency import symbol
from core.i18n import t
from core.storage.models import PortfolioStory
from core.ui.verdicts import cloud_notice
from state import (
    get_analysis_service,
    get_market_agent,
    get_portfolio_service,
    get_portfolio_story_agent,
    get_portfolio_story_repo,
    get_skills_repo,
)

logger = logging.getLogger(__name__)


def _verdict_icon(verdict: str) -> str:
    """Return emoji icon for a verdict."""
    mapping = {
        "intact": "🟢",
        "gemischt": "🟡",
        "gefaehrdet": "🔴",
        "on_track": "🟢",
        "achtung": "🟡",
        "kritisch": "🔴",
        "unknown": "⚪",
    }
    return mapping.get(verdict.lower(), "⚪")


def _fit_role_display(fit_role: str) -> tuple[str, str]:
    """Return (icon, label) for a position fit role."""
    mapping = {
        "Wachstumsmotor": ("🔵", "Wachstumsmotor"),
        "Stabilitätsanker": ("🟡", "Stabilitätsanker"),
        "Einkommensquelle": ("🟢", "Einkommensquelle"),
        "Diversifikationselement": ("🟣", "Diversifikationselement"),
        "Fehlplatzierung": ("🔴", "Fehlplatzierung"),
    }
    return mapping.get(fit_role, ("⚪", "Unbekannt"))


st.set_page_config(page_title="Portfolio Story", page_icon="📖", layout="wide")
st.title("📖 Portfolio Story")
st.caption("Dein langfristiges Anlage-Narrativ und Alignment-Check")

# ──────────────────────────────────────────────────────────────────────
# Load data
# ──────────────────────────────────────────────────────────────────────

repo = get_portfolio_story_repo()
_portfolio_service = get_portfolio_service()
_analysis_service = get_analysis_service()
agent = get_portfolio_story_agent()
cloud_notice(agent.model)

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
        )

    with col2:
        st.markdown("**Ziele & Kontext**")
        target_year = st.number_input(
            "Ziel-Jahr (optional)",
            value=current_story.target_year if current_story and current_story.target_year else 0,
            step=1,
            format="%d",
        )
        liquidity_need = st.text_input(
            "Liquiditätsbedarf (optional)",
            value=current_story.liquidity_need if current_story and current_story.liquidity_need else "",
        )
        priority_options = ["Wachstum", "Ausgewogenheit", "Einkommen", "Sicherheit"]
        current_priority = (current_story.priority or "Ausgewogenheit") if current_story else "Ausgewogenheit"
        try:
            default_index = priority_options.index(current_priority)
        except ValueError:
            default_index = 1
        priority = st.selectbox(
            "Priorität",
            options=priority_options,
            index=default_index,
        )

    col1, col2 = st.columns(2)
    with col1:
        if st.form_submit_button("💾 Story speichern"):
            target_year_val = target_year if target_year > 0 else None
            liquidity_need_val = liquidity_need if liquidity_need.strip() else None

            if current_story:
                current_story.story = story_text
                current_story.target_year = target_year_val
                current_story.liquidity_need = liquidity_need_val
                current_story.priority = priority
                repo.save(current_story)
            else:
                new_story = PortfolioStory(
                    story=story_text,
                    target_year=target_year_val,
                    liquidity_need=liquidity_need_val,
                    priority=priority,
                )
                repo.save(new_story)
                current_story = new_story

            st.success("✅ Story gespeichert!")
            st.rerun()

    with col2:
        if st.form_submit_button("✨ KI-Entwurf"):
            if not current_story or not current_story.story:
                st.error("❌ Bitte speichere zuerst eine Story-Idee oder Outline.")
            else:
                portfolio = _portfolio_service.get_portfolio_positions()
                if not portfolio:
                    st.error("❌ Portfolio ist leer.")
                else:
                    positions_summary = "\n".join(
                        f"- {p.name} ({p.ticker})" for p in portfolio if p.ticker
                    )

                    with st.spinner("KI generiert Entwurf..."):
                        draft = asyncio.run(
                            agent.generate_story_draft(
                                positions_summary=positions_summary,
                                existing_story=current_story,
                                story_text=story_text,
                                target_year=target_year_val if target_year_val else None,
                                liquidity_need=liquidity_need_val,
                                priority=priority,
                            )
                        )
                        st.session_state["_ps_draft"] = draft
                        st.rerun()

if "_ps_draft" in st.session_state:
    st.info(f"**KI-Entwurf:**\n\n{st.session_state['_ps_draft']}")

st.divider()

# ──────────────────────────────────────────────────────────────────────
# Section 2: Pre-checks (Story Checker)
# ──────────────────────────────────────────────────────────────────────

st.subheader("2️⃣ Ausstehende Positions-Story-Checks")

# Get portfolio positions to count pending story checks
portfolio = _portfolio_service.get_portfolio_positions()
n_positions_with_ticker = 0
n_missing_story = 0

if portfolio:
    # Only count positions with ticker (those that can have story checks)
    positions_with_ticker = [p for p in portfolio if p.ticker]
    n_positions_with_ticker = len(positions_with_ticker)

    if positions_with_ticker:
        portfolio_ids = [p.id for p in positions_with_ticker]

        # Count missing story checker verdicts
        story_verdicts = _analysis_service.get_verdicts(portfolio_ids, "storychecker")
        n_missing_story = sum(1 for pid in portfolio_ids if pid not in story_verdicts)

        # Get latest timestamp
        latest_ts = None
        for verdict_obj in story_verdicts.values():
            if verdict_obj and hasattr(verdict_obj, 'created_at') and verdict_obj.created_at:
                if latest_ts is None or verdict_obj.created_at > latest_ts:
                    latest_ts = verdict_obj.created_at

        ts_str = f" (zuletzt: {latest_ts.strftime('%d.%m. %H:%M')})" if latest_ts else " (noch nicht gelaufen)"

        if n_missing_story > 0:
            st.info(
                f"💡 **Story Checker**: {n_missing_story}/{n_positions_with_ticker} Positionen ausstehend{ts_str}"
            )

# Checkbox for pre-checks
run_position_checks = st.checkbox(
    "☑ Ausstehende Positions-Storychecks vor Analyse ausführen",
    value=False,
    key="_ps_run_prechecks",
)

st.divider()

# ──────────────────────────────────────────────────────────────────────
# Section 3: Story-Check Settings & Main Button
# ──────────────────────────────────────────────────────────────────────

st.subheader("3️⃣ Portfolio Story-Check")

# Skill Selector for Story Analysis
skills_repo = get_skills_repo()
story_skills = skills_repo.get_by_area("portfolio_story")
skill_options = {s.name: s for s in story_skills if not s.hidden}

if skill_options:
    skill_names = list(skill_options.keys())
    selected_skill_name = st.selectbox(
        "Story-Check Fokus-Bereich",
        options=skill_names,
        index=0,
        key="portfolio_story_skill",
    )
    selected_skill = skill_options[selected_skill_name]
else:
    selected_skill = None

if st.button("📖 Portfolio Story-Check ausführen", type="primary", use_container_width=True):
    if not current_story or not current_story.story:
        st.error("❌ Bitte definiere zuerst eine Portfolio-Story.")
    else:
        # Run pre-checks if enabled (only for positions with missing verdicts)
        if run_position_checks and n_missing_story > 0:
            with st.spinner(f"Führe {n_missing_story} ausstehende Positions-Story-Checks aus..."):
                positions_with_ticker = [p for p in portfolio if p.ticker]
                portfolio_ids = [p.id for p in positions_with_ticker]
                story_verdicts = _analysis_service.get_verdicts(portfolio_ids, "storychecker")
                missing_ids = [pid for pid in portfolio_ids if pid not in story_verdicts]

                # TODO: Call storychecker agent for missing_ids
                # For now, just show that we would run them
                st.info(f"Würde {len(missing_ids)} Positionen prüfen (Storychecker-Integration ausstehend)")

        # Build portfolio + dividend snapshots
        portfolio = _portfolio_service.get_portfolio_positions()
        market_agent = get_market_agent()

        valuations_list = market_agent.get_portfolio_valuation() if market_agent else []
        valuations = {v.symbol: v for v in valuations_list} if valuations_list else {}

        portfolio_snapshot = "## Portfolio\n"
        if portfolio:
            for p in portfolio:
                val = valuations.get(p.ticker) if p.ticker else None
                val_eur = val.current_value_eur if val and val.current_value_eur else 0
                div_str = ""
                if val and val.annual_dividend_eur and val.annual_dividend_eur > 0:
                    div_str = f", Dividende: {val.annual_dividend_eur:.0f}€/Jahr ({(val.dividend_yield_pct or 0) * 100:.1f}%)"
                portfolio_snapshot += f"- {p.name} ({p.ticker}, {p.asset_class}): {val_eur:.0f}€{div_str}\n"
        else:
            portfolio_snapshot += "(Leer)\n"

        dividend_snapshot = "## Dividenden\n"
        total_annual_dividend = sum(
            v.annual_dividend_eur for v in valuations_list
            if v.annual_dividend_eur
        )
        total_eur = sum(v.current_value_eur for v in valuations_list if v.current_value_eur)
        dividend_yield = (total_annual_dividend / total_eur * 100) if total_eur > 0 else 0
        dividend_snapshot += f"**Gesamt-Dividende**: {total_annual_dividend:.0f}€/Jahr ({dividend_yield:.2f}% Rendite)\n"

        # Get inflation rate if available
        inflation_rate = None
        inflation_pos = next((v for v in valuations_list if v.symbol == "HICP"), None)
        if inflation_pos:
            inflation_rate = inflation_pos.day_pnl_pct

        # Run main analysis
        with st.spinner("Analysiere Portfolio gegen Story und Ziele..."):
            result = asyncio.run(
                agent.analyze_story_and_performance(
                    story=current_story,
                    portfolio_snapshot=portfolio_snapshot,
                    dividend_snapshot=dividend_snapshot,
                    skill_prompt=selected_skill.prompt if selected_skill else None,
                    inflation_rate=inflation_rate,
                )
            )

            st.session_state["_ps_result"] = result
            st.session_state["_ps_result_timestamp"] = datetime.now()

# ──────────────────────────────────────────────────────────────────────
# Section 4: Results
# ──────────────────────────────────────────────────────────────────────

st.divider()
st.subheader("📊 Ergebnisse")

if "_ps_result" in st.session_state:
    result = st.session_state["_ps_result"]

    # Story Verdict
    col1, col2 = st.columns(2)
    with col1:
        icon = _verdict_icon(result.verdict)
        st.metric(f"{icon} Story-Urteil", result.verdict.upper())
        st.info(result.summary)

    with col2:
        perf_icon = _verdict_icon(result.perf_verdict)
        st.metric(f"{perf_icon} Performance-Urteil", result.perf_verdict.upper())
        st.info(result.perf_summary)

    # Full text expandable
    with st.expander("📄 Vollständige Analyse"):
        st.markdown(result.full_text)

# Latest saved analysis (if available)
elif latest_analysis:
    st.info("**Letzte gespeicherte Analyse:**")
    col1, col2 = st.columns(2)
    with col1:
        icon = _verdict_icon(latest_analysis.verdict)
        st.metric(f"{icon} Story-Urteil", latest_analysis.verdict.upper())
        if latest_analysis.summary:
            st.info(latest_analysis.summary)

    with col2:
        perf_icon = _verdict_icon(latest_analysis.perf_verdict)
        st.metric(f"{perf_icon} Performance-Urteil", latest_analysis.perf_verdict.upper())
        if latest_analysis.perf_summary:
            st.info(latest_analysis.perf_summary)

    with st.expander("📄 Vollständige Analyse"):
        st.markdown(latest_analysis.full_text)
else:
    st.info("Noch keine Analyse vorhanden. Klick auf 'Portfolio Story-Check ausführen' um zu starten.")
