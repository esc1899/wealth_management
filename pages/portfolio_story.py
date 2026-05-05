"""
Portfolio Story — portfolio-level narrative, alignment check.
V2: Clean, focused on story integrity with position verdicts.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from datetime import datetime, timezone

import streamlit as st

from config import config
from core.currency import symbol
from core.i18n import t
from core.storage.models import PortfolioStory
from core.ui.verdicts import cloud_notice, verdict_badge, VERDICT_CONFIGS
from state import (
    get_analysis_service,
    get_app_config_repo,
    get_market_agent,
    get_portfolio_comment_model,
    get_portfolio_comment_service,
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


def _verdict_badge_compact(v, config_key: str) -> str:
    """Render verdict as badge for inline display, or '⚪ —' if None."""
    if v is None:
        return "⚪ —"
    return verdict_badge(v.verdict, VERDICT_CONFIGS[config_key])


def _render_position_details_expander(all_verdicts_by_agent, all_positions):
    """Render the Positions-Details expander with buttons + badges."""
    with st.expander(t("portfolio_story.position_details_label")):
        sc_verdicts = all_verdicts_by_agent.get("storychecker", {})
        cg_verdicts = all_verdicts_by_agent.get("consensus_gap", {})
        fa_verdicts = all_verdicts_by_agent.get("fundamental_analyzer", {})

        for p in all_positions:
            if not p.id or not p.ticker:
                continue

            sc_v = sc_verdicts.get(p.id)
            cg_v = cg_verdicts.get(p.id)
            fa_v = fa_verdicts.get(p.id)

            icon = _verdict_icon(sc_v.verdict if sc_v else "unknown")

            # Position name as button → deeplink to Position Dashboard
            if st.button(f"{icon} {p.name} ({p.ticker})", key=f"ps_pos_{p.id}"):
                st.session_state["pd_preselect_position_id"] = p.id
                st.switch_page("pages/position_dashboard.py")

            # Storychecker summary (existing behaviour)
            if sc_v and sc_v.summary:
                st.caption(sc_v.summary)

            # Three inline badges
            badges = (
                f"SC: {_verdict_badge_compact(sc_v, 'storychecker')} &nbsp;&nbsp; "
                f"CG: {_verdict_badge_compact(cg_v, 'consensus_gap')} &nbsp;&nbsp; "
                f"FA: {_verdict_badge_compact(fa_v, 'fundamental_analyzer')}"
            )
            st.markdown(f"<small>{badges}</small>", unsafe_allow_html=True)
            st.divider()


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
        from core.storage.base import get_connection, init_db, migrate_db, build_encryption_service
        from core.storage.positions import PositionsRepository
        from core.storage.analyses import PositionAnalysesRepository
        from core.storage.storychecker import StorycheckerRepository
        from core.llm.claude import ClaudeProvider
        from core.constants import CLAUDE_HAIKU
        from agents.storychecker_agent import StorycheckerAgent
        from state import get_skills_repo

        # Thread-local connection — exact pattern from watchlist_checker.py
        conn = get_connection(db_path)
        init_db(conn)
        migrate_db(conn)

        salt_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), "salt.bin")
        enc = build_encryption_service(enc_key, salt_path)
        pos_repo = PositionsRepository(conn, enc)
        analyses_repo = PositionAnalysesRepository(conn)
        storychecker_repo = StorycheckerRepository(conn)
        skills_repo = get_skills_repo()

        if config.OPENAI_BASE_URL:
            from core.llm.openai_compatible import OpenAICompatibleProvider
            llm = OpenAICompatibleProvider(api_key=config.OPENAI_API_KEY, model=config.LLM_DEFAULT_MODEL or "sonar", base_url=config.OPENAI_BASE_URL)
        else:
            llm = ClaudeProvider(api_key=api_key, model=CLAUDE_HAIKU, base_url=config.LLM_BASE_URL)

        agent = StorycheckerAgent(
            positions_repo=pos_repo,
            storychecker_repo=storychecker_repo,
            analyses_repo=analyses_repo,
            llm=llm,
            skills_repo=skills_repo,
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(
            agent.batch_check_all(positions=positions, language=language)
        )
        loop.close()

        success_count = sum(1 for _, err in results if err is None)
        errors = [f"{name}: {err}" for name, err in results if err is not None]
        job.update({
            "running": False,
            "done": True,
            "count": success_count,
            "error": "; ".join(errors) if errors else None,
        })
    except Exception as e:
        job.update({
            "running": False,
            "done": True,
            "count": 0,
            "error": str(e),
        })


st.set_page_config(page_title="Portfolio Story", page_icon="📖", layout="wide")
st.title(f"📖 {t('portfolio_story.title')}")
st.caption(t("portfolio_story.subtitle"))

# ──────────────────────────────────────────────────────────────────────
# Load data
# ──────────────────────────────────────────────────────────────────────

repo = get_portfolio_story_repo()
_portfolio_service = get_portfolio_service()
_analysis_service = get_analysis_service()
agent = get_portfolio_story_agent()
cloud_notice(agent.model, provider="ollama")

current_story = repo.get_current()
latest_analysis = repo.get_latest_analysis()

# Load valuations and positions early (needed for both button handler and results display)
market_agent = get_market_agent()
_portfolio_service = get_portfolio_service()
_analysis_service = get_analysis_service()

valuations_list = market_agent.get_portfolio_valuation() if market_agent else []
all_positions = _portfolio_service.get_portfolio_positions()

# Compute verdicts for all positions (all 3 agents at once)
all_ids = [p.id for p in all_positions if p.id]
all_verdicts_by_agent = _analysis_service.get_all_verdicts(all_ids) if all_ids else {}

# ──────────────────────────────────────────────────────────────────────
# Section 1: Define / Update Portfolio Story
# ──────────────────────────────────────────────────────────────────────

st.subheader(t("portfolio_story.story_section"))

with st.form("portfolio_story_form", clear_on_submit=False):
    col1, col2 = st.columns(2)

    with col1:
        story_text = st.text_area(
            t("portfolio_story.narrative_label"),
            value=current_story.story if current_story else "",
            height=150,
        )

    with col2:
        st.markdown(t("portfolio_story.goals_header"))
        target_year = st.number_input(
            t("portfolio_story.target_year_label"),
            value=current_story.target_year if current_story and current_story.target_year else 0,
            step=1,
            format="%d",
        )
        liquidity_need = st.text_input(
            t("portfolio_story.liquidity_label"),
            value=current_story.liquidity_need if current_story and current_story.liquidity_need else "",
        )
        priority_options = ["Wachstum", "Ausgewogenheit", "Einkommen", "Sicherheit"]
        current_priority = (current_story.priority or "Ausgewogenheit") if current_story else "Ausgewogenheit"
        try:
            default_index = priority_options.index(current_priority)
        except ValueError:
            default_index = 1
        priority = st.selectbox(
            t("portfolio_story.priority_label"),
            options=priority_options,
            index=default_index,
        )

    col1, col2 = st.columns(2)
    with col1:
        if st.form_submit_button(t("portfolio_story.save_button")):
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

            st.success(t("portfolio_story.saved_success"))
            st.rerun()

    with col2:
        if st.form_submit_button(t("portfolio_story.ai_draft_button")):
            if not current_story or not current_story.story:
                st.error(t("portfolio_story.ai_draft_no_story_error"))
            else:
                portfolio = _portfolio_service.get_portfolio_positions()
                if not portfolio:
                    st.error(t("portfolio_story.ai_draft_empty_error"))
                else:
                    positions_summary = "\n".join(
                        f"- {p.name} ({p.ticker})" for p in portfolio if p.ticker
                    )

                    with st.spinner(t("portfolio_story.ai_draft_spinner")):
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
    st.info(f"{t('portfolio_story.ai_draft_label')}\n\n{st.session_state['_ps_draft']}")

st.divider()

# ──────────────────────────────────────────────────────────────────────
# Section 2: Pre-checks (Story Checker for Positions)
# ──────────────────────────────────────────────────────────────────────

st.subheader(t("portfolio_story.pending_checks_section"))

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

        ts_str = t("portfolio_story.ts_last_run").format(ts=latest_ts.strftime('%d.%m. %H:%M')) if latest_ts else t("portfolio_story.ts_never")

        if n_missing_story > 0:
            st.info(
                t("portfolio_story.pending_info").format(n=n_missing_story, total=len(positions_with_story), ts=ts_str)
            )

# Checkbox for pre-checks
run_position_checks = st.checkbox(
    t("portfolio_story.run_pending_checkbox"),
    value=False,
    key="_ps_run_prechecks",
)

# Show job status if running
if "_PS_JOB" in st.session_state and st.session_state["_PS_JOB"]["running"]:
    st.info(t("portfolio_story.checks_running_info"))

st.divider()

# ──────────────────────────────────────────────────────────────────────
# Section 3: Story-Check Settings & Main Button
# ──────────────────────────────────────────────────────────────────────

st.subheader(t("portfolio_story.story_check_section"))

if st.button(t("portfolio_story.run_button"), type="primary", use_container_width=True):
    if not current_story or not current_story.story:
        st.error(t("portfolio_story.no_story_error"))
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
                      config.DB_PATH, config.ENCRYPTION_KEY, config.LLM_API_KEY),
                daemon=True,
            ).start()

            # Show spinner while waiting
            with st.spinner(t("portfolio_story.running_checks_spinner").format(n=len(missing_positions))):
                while _PS_JOB["running"]:
                    time.sleep(1)

            if _PS_JOB["error"]:
                st.error(f"❌ Error: {_PS_JOB['error']}")
            else:
                st.success(t("portfolio_story.checks_done_success").format(n=_PS_JOB['count']))

        # Build portfolio snapshot (WITHOUT dividends — LLM would invent numbers)
        valuations = {v.symbol: v for v in valuations_list} if valuations_list else {}

        portfolio_snapshot = "## Portfolio\n"
        if all_positions:
            for p in all_positions:
                val = valuations.get(p.ticker) if p.ticker else None
                val_eur = val.current_value_eur if val and val.current_value_eur else 0
                portfolio_snapshot += f"- {p.name} ({p.ticker}, {p.asset_class}): {val_eur:.0f}€\n"
        else:
            portfolio_snapshot += t("portfolio_story.empty_portfolio") + "\n"

        verdict_lines = []
        sc_verdicts_for_job = all_verdicts_by_agent.get("storychecker", {})
        for p in all_positions:
            if p.id and p.id in sc_verdicts_for_job:
                v = sc_verdicts_for_job[p.id]
                icon = {
                    "intact": "🟢",
                    "gemischt": "🟡",
                    "gefaehrdet": "🔴",
                }.get(v.verdict, "⚪")
                verdict_lines.append(f"- {p.name} ({p.ticker}): {icon} {v.summary or v.verdict}")
            elif p.story and p.ticker:
                verdict_lines.append(f"- {p.name} ({p.ticker}): {t('portfolio_story.verdict_pending')}")

        position_verdicts = "\n".join(verdict_lines) if verdict_lines else t("portfolio_story.no_verdicts")

        # Run main analysis
        with st.spinner(t("portfolio_story.analyze_spinner")):
            result = asyncio.run(
                agent.analyze_story_and_performance(
                    story=current_story,
                    portfolio_snapshot=portfolio_snapshot,
                    position_verdicts=position_verdicts,
                )
            )

            # Save analysis to database
            from core.storage.models import PortfolioStoryAnalysis
            analysis = PortfolioStoryAnalysis(
                verdict=result.verdict,
                summary=result.summary,
                perf_verdict=result.perf_verdict,
                perf_summary=result.perf_summary,
                stability_verdict=None,
                stability_summary=None,
                full_text=result.full_text,
                created_at=datetime.now(timezone.utc),
            )
            repo.save_analysis(analysis)

            st.session_state["_ps_result"] = result
            st.session_state["_ps_result_timestamp"] = datetime.now()

# ──────────────────────────────────────────────────────────────────────
# Section 4: Results
# ──────────────────────────────────────────────────────────────────────

st.divider()
st.subheader(t("portfolio_story.results_section"))

if "_ps_result" in st.session_state:
    result = st.session_state["_ps_result"]

    # Story Verdict
    col1, col2 = st.columns(2)
    with col1:
        icon = _verdict_icon(result.verdict)
        st.metric(f"{icon} {t('portfolio_story.story_verdict_label')}", result.verdict.upper())
        st.info(result.summary)

    with col2:
        perf_icon = _verdict_icon(result.perf_verdict)
        st.metric(f"{perf_icon} {t('portfolio_story.positions_verdict_label')}", result.perf_verdict.upper())
        st.info(result.perf_summary)

    # Full text expandable
    with st.expander(t("portfolio_story.full_analysis_label")):
        st.markdown(result.full_text)

    # Positions-Story-Details expandable
    _render_position_details_expander(all_verdicts_by_agent, all_positions)

# Latest saved analysis (if available)
elif latest_analysis:
    st.info(t("portfolio_story.last_analysis_label"))
    col1, col2 = st.columns(2)
    with col1:
        icon = _verdict_icon(latest_analysis.verdict)
        st.metric(f"{icon} {t('portfolio_story.story_verdict_label')}", latest_analysis.verdict.upper())
        if latest_analysis.summary:
            st.info(latest_analysis.summary)

    with col2:
        perf_icon = _verdict_icon(latest_analysis.perf_verdict)
        st.metric(f"{perf_icon} {t('portfolio_story.positions_verdict_label')}", latest_analysis.perf_verdict.upper())
        if latest_analysis.perf_summary:
            st.info(latest_analysis.perf_summary)

    with st.expander(t("portfolio_story.full_analysis_label")):
        st.markdown(latest_analysis.full_text)

    # Positions-Story-Details expandable (also show for saved analysis)
    _render_position_details_expander(all_verdicts_by_agent, all_positions)
else:
    st.info(t("portfolio_story.no_analysis"))

# ──────────────────────────────────────────────────────────────────────
# Section 5: KI-Kommentar
# ──────────────────────────────────────────────────────────────────────

_ps_full_text = None
if "_ps_result" in st.session_state:
    _ps_full_text = st.session_state["_ps_result"].full_text
elif latest_analysis and latest_analysis.full_text:
    _ps_full_text = latest_analysis.full_text

if _ps_full_text:
    from core.services.portfolio_comment_service import get_style_by_id

    _comment_style_id = get_app_config_repo().get("comment_style") or "humorvoll"
    _comment_style = get_style_by_id(_comment_style_id)
    _comment_service = get_portfolio_comment_service(get_portfolio_comment_model())

    _ctx = f"Portfolio Story-Check Ergebnis:\n{_ps_full_text}"
    _ctx_hash = hashlib.md5((_ctx + _comment_style_id).encode()).hexdigest()

    if st.session_state.get("_ps_comment_hash") != _ctx_hash:
        with st.spinner(f"{_comment_style['emoji']} {t('portfolio_story.ai_comment_spinner')}"):
            try:
                st.session_state["_ps_comment"] = _comment_service.generate_comment(_ctx, _comment_style_id)
                st.session_state["_ps_comment_hash"] = _ctx_hash
            except Exception as _e:
                logger.warning("KI-Kommentar fehlgeschlagen: %s", _e)
                st.session_state["_ps_comment"] = None

    if st.session_state.get("_ps_comment"):
        st.divider()
        st.subheader(t("portfolio_story.ai_comment_section"))
        with st.container(border=True):
            st.caption(f"{_comment_style['emoji']} **{_comment_style['name']}**")
            st.markdown(st.session_state["_ps_comment"])
