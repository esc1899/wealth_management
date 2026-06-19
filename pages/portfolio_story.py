"""
Portfolio Story — portfolio-level narrative, alignment check.
V2: Clean, focused on story integrity with position verdicts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timezone

import streamlit as st

import pandas as pd

from config import config
from core.background_jobs import run_storychecker_job, run_consensus_gap_job, run_fundamental_job
from core.currency import symbol
from core.i18n import t, current_language
from core.storage.models import PortfolioStory
from core.ui.verdicts import cloud_notice, verdict_badge, VERDICT_CONFIGS, fmt_verdict_matrix, accumulation_matrix_cell
from core.ui.markdown import llm_markdown
from core.accumulation import accumulation_for_position
from state import (
    get_analysis_service,
    get_app_config_repo,
    get_market_agent,
    get_portfolio_comment_model,
    get_portfolio_comment_service,
    get_portfolio_robustness_agent,
    get_portfolio_robustness_repo,
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


st.set_page_config(page_title="Portfolio Checker", page_icon="🔍", layout="wide")
st.title(f"🔍 {t('portfolio_story.title')}")
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

# Precompute check status for status matrix (Section 2)
sc_verdicts = all_verdicts_by_agent.get("storychecker", {})
cg_verdicts = all_verdicts_by_agent.get("consensus_gap", {})
fa_verdicts = all_verdicts_by_agent.get("fundamental_analyzer", {})
_valid_portfolio = [p for p in all_positions if p.id and p.ticker and not p.analysis_excluded]
_sc_eligible_ids = {p.id for p in _valid_portfolio if p.story}
_cg_fa_eligible_ids = {p.id for p in _valid_portfolio}
n_missing_sc = sum(1 for pid in _sc_eligible_ids if pid not in sc_verdicts)
n_missing_cg = sum(1 for pid in _cg_fa_eligible_ids if pid not in cg_verdicts)
n_missing_fa = sum(1 for pid in _cg_fa_eligible_ids if pid not in fa_verdicts)
n_total_missing = n_missing_sc + n_missing_cg + n_missing_fa

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
# Section 2: Positions-Check Status Matrix
# ──────────────────────────────────────────────────────────────────────

st.subheader(t("portfolio_story.cockpit_section"))

# Post-run toasts
if cockpit_msg := st.session_state.pop("_pc_done_msg", None):
    st.success(cockpit_msg)
if cockpit_errors := st.session_state.pop("_pc_errors", None):
    for _err in cockpit_errors:
        st.error(f"❌ {_err}")

# Build matrix rows (SC only for positions with story; all others get CG+FA cells)
_acc_yields = {
    v.symbol.upper(): v.dividend_yield_pct
    for v in get_market_agent().get_portfolio_valuation(include_watchlist=True)
    if v.symbol
}
_matrix_rows = []
for _p in _valid_portfolio:
    _sc_cell = fmt_verdict_matrix(sc_verdicts.get(_p.id), "storychecker") if _p.story else "—"
    _cg_cell = fmt_verdict_matrix(cg_verdicts.get(_p.id), "consensus_gap")
    _fa_cell = fmt_verdict_matrix(fa_verdicts.get(_p.id), "fundamental_analyzer")
    _acc = accumulation_for_position(
        _p.ticker, sc_verdicts.get(_p.id), fa_verdicts.get(_p.id), _acc_yields
    )
    _matrix_rows.append({
        "name": _p.name,
        "ticker": _p.ticker or "—",
        "sc": _sc_cell,
        "cg": _cg_cell,
        "fa": _fa_cell,
        "acc": accumulation_matrix_cell(_acc),
    })

_matrix_selection = st.dataframe(
    pd.DataFrame(_matrix_rows),
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "name": st.column_config.TextColumn("Position", width="medium"),
        "ticker": st.column_config.TextColumn("Ticker", width="small"),
        "sc": st.column_config.TextColumn(t("portfolio_story.cockpit_col_sc"), width="medium"),
        "cg": st.column_config.TextColumn(t("portfolio_story.cockpit_col_cg"), width="medium"),
        "fa": st.column_config.TextColumn(t("portfolio_story.cockpit_col_fa"), width="medium"),
        "acc": st.column_config.TextColumn(t("accumulation.col"), width="medium"),
    },
)

# Row selection → action buttons (directly below table)
_selected_rows = _matrix_selection.selection.rows if _matrix_selection.selection else []
if _selected_rows and _selected_rows[0] < len(_valid_portfolio):
    _sel_pos = _valid_portfolio[_selected_rows[0]]
    _row_missing = []
    if _sel_pos.id in _sc_eligible_ids and _sel_pos.id not in sc_verdicts: _row_missing.append("sc")
    if _sel_pos.id not in cg_verdicts: _row_missing.append("cg")
    if _sel_pos.id not in fa_verdicts: _row_missing.append("fa")

    with st.container(border=True):
        st.caption(f"**{_sel_pos.name}** ({_sel_pos.ticker})")
        _nav_col1, _nav_col2, _nav_spacer = st.columns([1, 2, 3])
        with _nav_col1:
            if st.button(t("portfolio_story.nav_to_pd"), key="pc_nav_pd_btn", use_container_width=True):
                st.session_state["pd_preselect_position_id"] = _sel_pos.id
                st.switch_page("pages/position_dashboard.py")
        with _nav_col2:
            if _row_missing:
                if st.button(t("portfolio_story.cockpit_run_row_missing").format(n=len(_row_missing)), key="pc_run_row_btn", use_container_width=True):
                    _lang = current_language()
                    _row_total = 0
                    _row_errors: list[str] = []
                    _pos_single = [_sel_pos]
                    _JOB_ARGS = (config.DB_PATH, config.ENCRYPTION_KEY, config.LLM_API_KEY)

                    def _run_row_job_pc(target, spinner_text, label):
                        _j = {"running": True, "done": False, "count": 0, "error": None}
                        threading.Thread(target=target, args=(_pos_single, _lang, _j) + _JOB_ARGS, daemon=True).start()
                        with st.spinner(spinner_text):
                            while _j["running"]: time.sleep(1)
                        if _j["error"]: _row_errors.append(f"{label}: {_j['error']}"); return 0
                        return _j["count"]

                    if "sc" in _row_missing:
                        _row_total += _run_row_job_pc(run_storychecker_job, t("watchlist_checker.running_story_spinner").format(n=1), "Story Checker")
                    if "cg" in _row_missing:
                        _row_total += _run_row_job_pc(run_consensus_gap_job, t("watchlist_checker.running_consensus_spinner").format(n=1), "Konsens-Lücken")
                    if "fa" in _row_missing:
                        _row_total += _run_row_job_pc(run_fundamental_job, t("watchlist_checker.running_fund_spinner").format(n=1), "Fundamental")

                    if _row_errors: st.session_state["_pc_errors"] = _row_errors
                    st.session_state["_pc_done_msg"] = t("watchlist_checker.cockpit_done").format(n=_row_total)
                    st.rerun()

# Global: run all missing / all complete
if n_total_missing > 0:
    n_incomplete = sum(
        1 for p in _valid_portfolio if (
            (p.id in _sc_eligible_ids and p.id not in sc_verdicts) or
            p.id not in cg_verdicts or p.id not in fa_verdicts
        )
    )
    st.caption(t("watchlist_checker.cockpit_missing_summary").format(n=n_total_missing, positions=n_incomplete))
    if st.button(t("portfolio_story.cockpit_run_all_missing"), key="pc_run_all_btn"):
        _lang = current_language()
        _total_done = 0
        _all_errors: list[str] = []
        _JOB_ARGS_ALL = (config.DB_PATH, config.ENCRYPTION_KEY, config.LLM_API_KEY)

        def _run_all_job(target, positions, spinner_text, label):
            _j = {"running": True, "done": False, "count": 0, "error": None}
            threading.Thread(target=target, args=(positions, _lang, _j) + _JOB_ARGS_ALL, daemon=True).start()
            with st.spinner(spinner_text):
                while _j["running"]: time.sleep(1)
            if _j["error"]: _all_errors.append(f"{label}: {_j['error']}"); return 0
            return _j["count"]

        if n_missing_sc > 0:
            _missing = [p for p in _valid_portfolio if p.id in _sc_eligible_ids and p.id not in sc_verdicts]
            _total_done += _run_all_job(run_storychecker_job, _missing, t("watchlist_checker.running_story_spinner").format(n=len(_missing)), "Story Checker")
        if n_missing_cg > 0:
            _missing = [p for p in _valid_portfolio if p.id in _cg_fa_eligible_ids and p.id not in cg_verdicts]
            _total_done += _run_all_job(run_consensus_gap_job, _missing, t("watchlist_checker.running_consensus_spinner").format(n=len(_missing)), "Konsens-Lücken")
        if n_missing_fa > 0:
            _missing = [p for p in _valid_portfolio if p.id in _cg_fa_eligible_ids and p.id not in fa_verdicts]
            _total_done += _run_all_job(run_fundamental_job, _missing, t("watchlist_checker.running_fund_spinner").format(n=len(_missing)), "Fundamental")

        if _all_errors: st.session_state["_pc_errors"] = _all_errors
        st.session_state["_pc_done_msg"] = t("watchlist_checker.cockpit_done").format(n=_total_done)
        st.rerun()
else:
    st.success(t("watchlist_checker.cockpit_all_complete"))

st.divider()

# ──────────────────────────────────────────────────────────────────────
# Section 3: Story-Check Settings & Main Button
# ──────────────────────────────────────────────────────────────────────

st.subheader(t("portfolio_story.story_check_section"))

if st.button(t("portfolio_story.run_button"), type="primary", use_container_width=True):
    if not current_story or not current_story.story:
        st.error(t("portfolio_story.no_story_error"))
    else:
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
    _ts = st.session_state.get("_ps_result_timestamp")
    if _ts:
        st.caption(f"Analyse vom {_ts.strftime('%d.%m.%Y %H:%M')}")

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
        llm_markdown(result.full_text)

    # Positions-Story-Details expandable
    _render_position_details_expander(all_verdicts_by_agent, all_positions)

# Latest saved analysis (if available)
elif latest_analysis:
    _saved_ts = latest_analysis.created_at
    if _saved_ts:
        _ts_str = _saved_ts.strftime('%d.%m.%Y %H:%M') if hasattr(_saved_ts, 'strftime') else str(_saved_ts)[:16]
        st.caption(f"Analyse vom {_ts_str}")
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
        llm_markdown(latest_analysis.full_text)

    # Positions-Story-Details expandable (also show for saved analysis)
    _render_position_details_expander(all_verdicts_by_agent, all_positions)
else:
    st.info(t("portfolio_story.no_analysis"))

# ──────────────────────────────────────────────────────────────────────
# Section 5: Portfolio-Gegenanalyse (Ollama, lokal)
# ──────────────────────────────────────────────────────────────────────

st.divider()
with st.container(border=True):
    st.subheader(t("portfolio_robustness.section_header"))
    st.caption(t("portfolio_robustness.section_subtitle"))

    _pr_agent = get_portfolio_robustness_agent()
    _pr_repo = get_portfolio_robustness_repo()
    cloud_notice(_pr_agent.model, provider="ollama")

    _pr_latest = _pr_repo.get_latest()

    _pr_btn_type = "secondary"
    if st.button(t("portfolio_robustness.run_button"), key="pr_run_btn", type=_pr_btn_type):
        _pr_lang = current_language()
        # Build portfolio snapshot (same as for Portfolio Story)
        _pr_snapshot_lines = []
        for _p in all_positions:
            _ticker = f" ({_p.ticker})" if _p.ticker else ""
            _pr_snapshot_lines.append(f"- {_p.name}{_ticker} [{_p.asset_class}]")
        _pr_snapshot = "\n".join(_pr_snapshot_lines) if _pr_snapshot_lines else "(kein Portfolio)"

        # Build verdicts summary from all available agents
        _pr_verdict_lines = []
        for _agent_name, _agent_verdicts in all_verdicts_by_agent.items():
            for _p in all_positions:
                if _p.id and _p.id in _agent_verdicts:
                    _v = _agent_verdicts[_p.id]
                    _pr_verdict_lines.append(f"- {_p.name} ({_agent_name}): {_v.verdict}")
        _pr_verdicts_str = "\n".join(_pr_verdict_lines) if _pr_verdict_lines else "(keine Verdicts)"

        with st.spinner(t("portfolio_robustness.running_spinner")):
            try:
                _pr_result = asyncio.run(
                    _pr_agent.analyze(
                        portfolio_snapshot=_pr_snapshot,
                        position_verdicts=_pr_verdicts_str,
                        language=_pr_lang,
                        position_count=len(all_positions),
                    )
                )
                _pr_latest = _pr_repo.save(
                    verdict=_pr_result.verdict,
                    summary=_pr_result.summary,
                    analysis_text=_pr_result.analysis_text,
                    position_count=_pr_result.position_count,
                )
                st.session_state["_pr_result"] = _pr_result
            except Exception as _pr_exc:
                st.error(f"Fehler: {_pr_exc}")

    if "_pr_result" in st.session_state:
        _pr_show = st.session_state["_pr_result"]
    elif _pr_latest:
        _pr_show = _pr_latest
    else:
        _pr_show = None

    if _pr_show:
        _pr_badge = verdict_badge(_pr_show.verdict, VERDICT_CONFIGS["portfolio_robustness"])
        _pr_col1, _pr_col2 = st.columns([4, 1])
        with _pr_col1:
            st.markdown(f"**{_pr_badge}**")
            if _pr_show.summary:
                llm_markdown(f"_{_pr_show.summary}_")
        with _pr_col2:
            if _pr_show.created_at:
                st.caption(_pr_show.created_at.strftime("%d. %b %Y, %H:%M"))
        with st.expander(t("portfolio_robustness.full_analysis"), expanded=False):
            llm_markdown(_pr_show.analysis_text)

        # History (last 3)
        _pr_history = _pr_repo.list_recent(limit=5)
        if len(_pr_history) > 1:
            with st.expander(t("portfolio_robustness.history_header"), expanded=False):
                for _h in _pr_history[1:4]:
                    _h_badge = verdict_badge(_h.verdict, VERDICT_CONFIGS["portfolio_robustness"])
                    _h_ts = _h.created_at.strftime("%d.%m.%Y %H:%M") if _h.created_at else "—"
                    st.markdown(f"**{_h_ts}** — {_h_badge}")
                    if _h.summary:
                        st.caption(_h.summary)
    else:
        st.info(t("portfolio_robustness.no_analysis"))

# ──────────────────────────────────────────────────────────────────────
# Section 6: KI-Kommentar
# ──────────────────────────────────────────────────────────────────────

_ps_full_text = None
if "_ps_result" in st.session_state:
    _ps_full_text = st.session_state["_ps_result"].full_text
elif latest_analysis and latest_analysis.full_text:
    _ps_full_text = latest_analysis.full_text

if _ps_full_text:
    from core.ui.ai_comment import render_ai_comment

    render_ai_comment(
        state_key="_ps",
        ctx=f"Portfolio Story-Check Ergebnis:\n{_ps_full_text}",
        style_id=get_app_config_repo().get("comment_style") or "humorvoll",
        comment_service=get_portfolio_comment_service(get_portfolio_comment_model()),
        section_title=t("portfolio_story.ai_comment_section"),
    )
