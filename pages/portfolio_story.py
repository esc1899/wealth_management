"""
Portfolio Checker — misst das Depot an der Portfolio-Story (lokal, Ollama).

Die Story selbst wird seit 10.10.2026 unter Pflege -> Portfolio-Story gepflegt
(pages/portfolio_narrativ.py), der Stand der Positions-Checks steht auf den Kacheln.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import streamlit as st

from core.i18n import t, current_language
from core.ui.verdicts import cloud_notice, verdict_badge, VERDICT_CONFIGS
from core.ui.markdown import llm_markdown
from core.portfolio_snapshot import build_portfolio_snapshot
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

# Die Story selbst pflegt die Seite Pflege -> Portfolio-Story (pages/portfolio_narrativ.py);
# den Stand der Positions-Checks zeigen die Kacheln. Hier bleibt der Check gegen die Story.
if not current_story or not current_story.story:
    st.info(t("portfolio_story.no_story_link"))

# ──────────────────────────────────────────────────────────────────────
# Section 3: Story-Check Settings & Main Button
# ──────────────────────────────────────────────────────────────────────

st.subheader(t("portfolio_story.story_check_section"))

if st.button(t("portfolio_story.run_button"), type="primary", width="stretch"):
    if not current_story or not current_story.story:
        st.error(t("portfolio_story.no_story_error"))
    else:
        # Dividenden gehören in den Prompt: das Ziel im Liquiditätsbedarf ist oft
        # ein Ausschüttungsziel. Ohne die berechneten Zahlen erfindet das Modell sie.
        if all_positions:
            portfolio_snapshot = build_portfolio_snapshot(all_positions, valuations_list)
        else:
            portfolio_snapshot = "## Portfolio\n" + t("portfolio_story.empty_portfolio") + "\n"

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
        # Mit Werten und Gewichten — der Prompt fragt nach Konzentration (>15% / >30%),
        # das ist ohne Zahlen nicht beantwortbar und wurde bisher geraten.
        _pr_snapshot = (
            build_portfolio_snapshot(all_positions, valuations_list)
            if all_positions else "(kein Portfolio)"
        )

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
