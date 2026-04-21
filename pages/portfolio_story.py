"""
Portfolio Story — portfolio-level narrative, alignment check.
V2: Clean, focused on story integrity with position verdicts.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime

import streamlit as st

from config import config
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
)

logger = logging.getLogger(__name__)


def _verdict_icon(verdict: str) -> str:
    """Return emoji icon for a verdict."""
    mapping = {
        "intact": "🟢",
        "gemischt": "🟡",
        "gefaehrdet": "🔴",
        "unknown": "⚪",
    }
    return mapping.get(verdict.lower(), "⚪")


# ──────────────────────────────────────────────────────────────────────
# Background Job for Storychecker Pre-checks
# ──────────────────────────────────────────────────────────────────────

_PS_JOB = {
    "running": False,
    "done": False,
    "count": 0,
    "error": None,
    "agents": [],
}

_JOB_DEFAULTS = {
    "running": False,
    "done": False,
    "count": 0,
    "error": None,
    "agents": [],
}


def _run_storychecker_job(
    positions,
    language: str,
    job: dict,
    db_path: str,
    enc_key: str,
    api_key: str,
) -> None:
    """
    Run storychecker for given positions in a background thread.
    Uses thread-local DB connection (not Streamlit singletons).
    Imports from core.storage.base (thread-safe) not state_db (Streamlit singleton).
    """
    try:
        from core.storage.base import get_connection, init_db, migrate_db
        from core.storage.positions import PositionsRepository
        from core.storage.analyses import PositionAnalysesRepository
        from core.storage.storychecker import StorycheckerRepository
        from core.storage.skills import SkillsRepository
        from core.llm.claude import ClaudeProvider
        from core.constants import CLAUDE_HAIKU
        from agents.storychecker_agent import StorycheckerAgent

        # Establish thread-local connection (not Streamlit singleton)
        conn = get_connection(db_path)
        init_db(conn)
        migrate_db(conn)

        # Build repos
        pos_repo = PositionsRepository(conn)
        analyses_repo = PositionAnalysesRepository(conn)
        storychecker_repo = StorycheckerRepository(conn)
        skills_repo = SkillsRepository(conn)

        # Build LLM
        llm = ClaudeProvider(api_key=api_key, model=CLAUDE_HAIKU)

        # Build agent with all required repos
        agent = StorycheckerAgent(
            positions_repo=pos_repo,
            storychecker_repo=storychecker_repo,
            analyses_repo=analyses_repo,
            llm=llm,
            skills_repo=skills_repo,
        )

        # Run batch check
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(
            agent.batch_check_all(positions=positions, language=language)
        )
        loop.close()

        # Count successes
        success_count = sum(1 for name, error in results if error is None)
        job.update({
            "running": False,
            "done": True,
            "count": success_count,
            "error": None,
        })
    except Exception as e:
        job.update({
            "running": False,
            "done": True,
            "count": 0,
            "error": str(e),
        })


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
# Section 2: Pre-checks (Story Checker for Positions)
# ──────────────────────────────────────────────────────────────────────

st.subheader("2️⃣ Ausstehende Positions-Story-Checks")

portfolio = _portfolio_service.get_portfolio_positions()
positions_with_story = []
n_missing_story = 0
story_verdicts = {}

if portfolio:
    # Only positions with story field set
    positions_with_story = [p for p in portfolio if p.story and p.ticker]

    if positions_with_story:
        portfolio_ids = [p.id for p in positions_with_story]

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
                f"💡 **Story Checker**: {n_missing_story}/{len(positions_with_story)} Positionen ausstehend{ts_str}"
            )

# Checkbox for pre-checks
run_position_checks = st.checkbox(
    "☑ Ausstehende Positions-Storychecks vor Analyse ausführen",
    value=False,
    key="_ps_run_prechecks",
)

# Show job status if running
if "_PS_JOB" in st.session_state and st.session_state["_PS_JOB"]["running"]:
    st.info("⏳ Storychecker läuft im Hintergrund...")

st.divider()

# ──────────────────────────────────────────────────────────────────────
# Section 3: Story-Check Settings & Main Button
# ──────────────────────────────────────────────────────────────────────

st.subheader("3️⃣ Portfolio Story-Check")

if st.button("📖 Portfolio Story-Check ausführen", type="primary", use_container_width=True):
    if not current_story or not current_story.story:
        st.error("❌ Bitte definiere zuerst eine Portfolio-Story.")
    else:
        # Run pre-checks if enabled (only missing ones)
        if run_position_checks and n_missing_story > 0 and positions_with_story:
            # Start background thread
            missing_positions = [
                p for p in positions_with_story
                if p.id not in story_verdicts
            ]

            _PS_JOB.update({
                **_JOB_DEFAULTS,
                "running": True,
                "agents": ["Story Checker"],
            })
            st.session_state["_PS_JOB"] = _PS_JOB

            threading.Thread(
                target=_run_storychecker_job,
                args=(missing_positions, "de", _PS_JOB,
                      config.DB_PATH, config.ENCRYPTION_KEY, config.ANTHROPIC_API_KEY),
                daemon=True,
            ).start()

            # Show spinner while waiting
            with st.spinner(f"Führe {len(missing_positions)} Story-Checks aus..."):
                while _PS_JOB["running"]:
                    time.sleep(1)

            if _PS_JOB["error"]:
                st.error(f"❌ Error: {_PS_JOB['error']}")
            else:
                st.success(f"✅ {_PS_JOB['count']} Story-Checks abgeschlossen")

        # Build portfolio snapshot (WITHOUT dividends — LLM would invent numbers)
        portfolio = _portfolio_service.get_portfolio_positions()
        market_agent = get_market_agent()

        valuations_list = market_agent.get_portfolio_valuation() if market_agent else []
        valuations = {v.symbol: v for v in valuations_list} if valuations_list else {}

        portfolio_snapshot = "## Portfolio\n"
        if portfolio:
            for p in portfolio:
                val = valuations.get(p.ticker) if p.ticker else None
                val_eur = val.current_value_eur if val and val.current_value_eur else 0
                portfolio_snapshot += f"- {p.name} ({p.ticker}, {p.asset_class}): {val_eur:.0f}€\n"
        else:
            portfolio_snapshot += "(Leer)\n"

        # Load position verdicts for the story analysis
        all_positions = _portfolio_service.get_portfolio_positions()
        all_ids = [p.id for p in all_positions if p.id]
        all_verdicts = _analysis_service.get_verdicts(all_ids, "storychecker") if all_ids else {}

        verdict_lines = []
        for p in all_positions:
            if p.id and p.id in all_verdicts:
                v = all_verdicts[p.id]
                icon = {
                    "intact": "🟢",
                    "gemischt": "🟡",
                    "gefaehrdet": "🔴",
                }.get(v.verdict, "⚪")
                verdict_lines.append(f"- {p.name} ({p.ticker}): {icon} {v.summary or v.verdict}")
            elif p.story and p.ticker:
                verdict_lines.append(f"- {p.name} ({p.ticker}): ⚪ (ausstehend)")

        position_verdicts = "\n".join(verdict_lines) if verdict_lines else "(Keine Position-Verdicts verfügbar)"

        # Run main analysis
        with st.spinner("Analysiere Portfolio gegen Story..."):
            result = asyncio.run(
                agent.analyze_story_and_performance(
                    story=current_story,
                    portfolio_snapshot=portfolio_snapshot,
                    position_verdicts=position_verdicts,
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
        st.metric(f"{perf_icon} Positions-Urteil", result.perf_verdict.upper())
        st.info(result.perf_summary)

    # Full text expandable
    with st.expander("📄 Vollständige Analyse"):
        st.markdown(result.full_text)

    # Dividend summary (deterministisch, nicht vom LLM erfunden)
    st.divider()
    st.subheader("💰 Portfolio-Dividenden")
    total_dividend = sum(
        v.annual_dividend_eur for v in valuations_list
        if v.annual_dividend_eur
    )
    total_eur = sum(v.current_value_eur for v in valuations_list if v.current_value_eur)
    dividend_yield = (total_dividend / total_eur * 100) if total_eur > 0 else 0

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Jährliche Gesamtdividende", f"{total_dividend:.0f}€")
    with col2:
        st.metric("Dividend Yield", f"{dividend_yield:.2f}%")

    # Positions-Story-Details expandable
    with st.expander("📋 Positions-Story-Details"):
        for p in all_positions:
            if p.id and p.id in all_verdicts:
                v = all_verdicts[p.id]
                icon = {
                    "intact": "🟢",
                    "gemischt": "🟡",
                    "gefaehrdet": "🔴",
                }.get(v.verdict, "⚪")
                st.markdown(f"**{icon} {p.name}** ({p.ticker})")
                if v.summary:
                    st.caption(v.summary)
            elif p.story and p.ticker:
                st.markdown(f"**⚪ {p.name}** ({p.ticker}) — Story-Check ausstehend")

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
        st.metric(f"{perf_icon} Positions-Urteil", latest_analysis.perf_verdict.upper())
        if latest_analysis.perf_summary:
            st.info(latest_analysis.perf_summary)

    with st.expander("📄 Vollständige Analyse"):
        st.markdown(latest_analysis.full_text)
else:
    st.info("Noch keine Analyse vorhanden. Klick auf 'Portfolio Story-Check ausführen' um zu starten.")
