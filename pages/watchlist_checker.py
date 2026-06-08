"""
Watchlist Checker — evaluates which watchlist positions fit into the portfolio.

FEAT-40 Cockpit Refactor (2026-05-11):
- Section 1: Status-Matrix (alle Kandidaten × alle 4 Sub-Checks + WC-Fit)
- Section 2: Main WatchlistCheckerAgent run (Ollama, lokal)
- Section 3: Ergebnisse (vereinfachte Position-Cards, kein 4-Spalten-Expander)
- One-Click "Alle fehlenden Checks ausführen" Button
"""

import asyncio
import json
import logging
import os
import threading
import time
import streamlit as st
from dataclasses import dataclass as _dataclass
from datetime import datetime, timezone

import pandas as pd

from core.ui.verdicts import VERDICT_CONFIGS, verdict_icon, cloud_notice, fmt_verdict_matrix
from core.i18n import t, current_language

st.set_page_config(page_title="Watchlist Checker", layout="wide")

from state import (
    get_analysis_service,
    get_portfolio_service,
    get_watchlist_checker_agent,
    get_portfolio_story_repo,
    get_agent_runs_repo,
    get_portfolio_comment_model,
    get_portfolio_comment_service,
    get_app_config_repo,
    get_storychecker_repo,
    get_skills_repo,
    get_watchlist_checker_repo,
    get_market_agent,
    get_positions_repo,
)
from core.services.portfolio_comment_service import get_style_by_id
from config import config
from core.storage.analyses import PositionAnalysesRepository
from core.background_jobs import (
    run_storychecker_job,
    run_consensus_gap_job,
    run_devils_advocate_job,
    run_fundamental_job,
    run_capital_allocator_job,
)


logger = logging.getLogger(__name__)

_STALE_DAYS = 7
_JOB_ARGS = None  # set after config import below


def _is_stale(verdict_obj) -> bool:
    if verdict_obj is None or verdict_obj.created_at is None:
        return True
    created = verdict_obj.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).days >= _STALE_DAYS


def _run_parallel(jobs: list, lang: str, errors: list) -> int:
    """Start all job threads simultaneously, wait once for all. Returns total count.

    jobs: list of (target_fn, positions, label)
    All threads are started before we block — so navigating away doesn't abort remaining ones.
    """
    states = []
    for target, positions, label in jobs:
        j = {"running": True, "done": False, "count": 0, "error": None, "logs": []}
        threading.Thread(
            target=target,
            args=(positions, lang, j, config.DB_PATH, config.ENCRYPTION_KEY, config.LLM_API_KEY),
            daemon=True,
        ).start()
        states.append((j, label))

    with st.spinner(t("watchlist_checker.running_parallel_spinner").format(n=len(states))):
        while any(j["running"] for j, _ in states):
            time.sleep(1)

    total = 0
    for j, label in states:
        if j["error"]:
            errors.append(f"{label}: {j['error']}")
        else:
            total += j["count"]
    return total


# ------------------------------------------------------------------
# Helpers: Display normalization
# ------------------------------------------------------------------

@_dataclass
class _DisplayFit:
    """Normalized fit object for display."""
    position_id: int
    verdict: str
    summary: str


def _normalize_result(result):
    """Convert WatchlistCheckerAnalysis or WatchlistCheckResult to normalized form."""
    if hasattr(result, 'position_fits') and result.position_fits:
        return result, result.position_fits
    if hasattr(result, 'position_fits_json') and result.position_fits_json:
        try:
            fits_data = json.loads(result.position_fits_json)
            position_fits = [_DisplayFit(**fit) for fit in fits_data]
            return result, position_fits
        except Exception as e:
            logger.warning(f"Failed to deserialize position_fits_json: {e}")
            return result, []
    return result, []


# ─────────────────────────────────────────────────────────────────────
# Page Header
# ─────────────────────────────────────────────────────────────────────

st.title(f"📋 {t('watchlist_checker.title')}")
st.caption(t("watchlist_checker.subtitle"))

# ─────────────────────────────────────────────────────────────────────
# Init: Services + Data
# ─────────────────────────────────────────────────────────────────────

_portfolio_service = get_portfolio_service()
_analysis_service = get_analysis_service()
portfolio_story_repo = get_portfolio_story_repo()
agent = get_watchlist_checker_agent()
agent_runs_repo = get_agent_runs_repo()
wc_repo = get_watchlist_checker_repo()

watchlist = _portfolio_service.get_watchlist_positions()

if not watchlist:
    st.info(t("watchlist_checker.no_watchlist"))
    st.stop()

st.caption(t("watchlist_checker.watchlist_count").format(n=len(watchlist)))

# Pre-fetch all sub-check verdicts
watchlist_ids = [pos.id for pos in watchlist if pos.id]
sc_verdicts = _analysis_service.get_verdicts(watchlist_ids, "storychecker")
cg_verdicts = _analysis_service.get_verdicts(watchlist_ids, "consensus_gap")
fund_verdicts = _analysis_service.get_verdicts(watchlist_ids, "fundamental_analyzer")
ca_verdicts = _analysis_service.get_verdicts(watchlist_ids, "capital_allocator")
da_verdicts = _analysis_service.get_verdicts(watchlist_ids, "devils_advocate")

# Pre-load WC fits for matrix WC-Fit column
_latest_wc_result = wc_repo.get_latest_analysis()
_wc_fits: dict[int, _DisplayFit] = {}
if _latest_wc_result:
    _, _fits_list = _normalize_result(_latest_wc_result)
    _wc_fits = {f.position_id: f for f in _fits_list}

# Missing counts
n_missing_sc = sum(1 for pid in watchlist_ids if pid not in sc_verdicts)
n_missing_cg = sum(1 for pid in watchlist_ids if pid not in cg_verdicts)
n_missing_fund = sum(1 for pid in watchlist_ids if pid not in fund_verdicts)
n_missing_ca = sum(1 for pid in watchlist_ids if pid not in ca_verdicts)
n_missing_da = sum(1 for pid in watchlist_ids if pid not in da_verdicts)
n_total_missing = n_missing_sc + n_missing_cg + n_missing_fund + n_missing_ca + n_missing_da

# Stale counts (have a verdict but ≥ _STALE_DAYS old)
n_stale_sc = sum(1 for pid in watchlist_ids if pid in sc_verdicts and _is_stale(sc_verdicts[pid]))
n_stale_cg = sum(1 for pid in watchlist_ids if pid in cg_verdicts and _is_stale(cg_verdicts[pid]))
n_stale_fund = sum(1 for pid in watchlist_ids if pid in fund_verdicts and _is_stale(fund_verdicts[pid]))
n_stale_ca = sum(1 for pid in watchlist_ids if pid in ca_verdicts and _is_stale(ca_verdicts[pid]))
n_stale_da = sum(1 for pid in watchlist_ids if pid in da_verdicts and _is_stale(da_verdicts[pid]))
n_total_stale = n_stale_sc + n_stale_cg + n_stale_fund + n_stale_ca + n_stale_da

# Post-run success toast (set by cockpit button, shown after st.rerun())
if cockpit_msg := st.session_state.pop("_cockpit_done_msg", None):
    st.success(cockpit_msg)
if cockpit_errors := st.session_state.pop("_cockpit_errors", None):
    for _err in cockpit_errors:
        st.error(f"❌ {_err}")

# ─────────────────────────────────────────────────────────────────────
# Section 1: Status-Matrix (NEU, FEAT-40)
# ─────────────────────────────────────────────────────────────────────

st.subheader(t("watchlist_checker.cockpit_section"))

# Build matrix
matrix_rows = []
for pos in watchlist:
    if not pos.id:
        continue
    wc_fit = _wc_fits.get(pos.id)
    matrix_rows.append({
        "name": pos.name,
        "ticker": pos.ticker or "—",
        "sc": fmt_verdict_matrix(sc_verdicts.get(pos.id), "storychecker", stale_days=_STALE_DAYS),
        "fa": fmt_verdict_matrix(fund_verdicts.get(pos.id), "fundamental_analyzer", stale_days=_STALE_DAYS),
        "cg": fmt_verdict_matrix(cg_verdicts.get(pos.id), "consensus_gap", stale_days=_STALE_DAYS),
        "ca": fmt_verdict_matrix(ca_verdicts.get(pos.id), "capital_allocator", stale_days=_STALE_DAYS),
        "da": fmt_verdict_matrix(da_verdicts.get(pos.id), "devils_advocate", stale_days=_STALE_DAYS),
        "wc": (fmt_verdict_matrix(wc_fit, "watchlist_checker") if wc_fit else "⚪ —"),
    })

_matrix_selection = st.dataframe(
    pd.DataFrame(matrix_rows),
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    column_config={
        "name": st.column_config.TextColumn("Position", width="medium"),
        "ticker": st.column_config.TextColumn("Ticker", width="small"),
        "sc": st.column_config.TextColumn(t("watchlist_checker.cockpit_col_sc"), width="medium"),
        "fa": st.column_config.TextColumn(t("watchlist_checker.cockpit_col_fa"), width="medium"),
        "cg": st.column_config.TextColumn(t("watchlist_checker.cockpit_col_cg"), width="medium"),
        "ca": st.column_config.TextColumn(t("watchlist_checker.cockpit_col_ca"), width="medium"),
        "da": st.column_config.TextColumn(t("watchlist_checker.cockpit_col_da"), width="medium"),
        "wc": st.column_config.TextColumn(t("watchlist_checker.cockpit_col_wc"), width="medium"),
    },
)

# Delete dialog for selected position
@st.dialog(t("watchlist_checker.delete_confirm_title"))
def _show_delete_dialog(pos_id: int, pos_name: str) -> None:
    st.warning(t("watchlist_checker.delete_confirm_warning").format(name=pos_name))
    col_yes, col_no = st.columns(2)
    if col_yes.button(t("watchlist_checker.delete_confirm_yes"), type="primary", use_container_width=True):
        get_positions_repo().delete(pos_id)
        st.toast(t("watchlist_checker.delete_done"), icon="🗑️")
        st.rerun()
    if col_no.button(t("watchlist_checker.delete_confirm_no"), use_container_width=True):
        st.rerun()


if del_pending := st.session_state.pop("_wc_delete_pending", None):
    _show_delete_dialog(del_pending["id"], del_pending["name"])

# Navigation für ausgewählte Zeile
_selected_rows = _matrix_selection.selection.rows if _matrix_selection.selection else []
_valid_positions = [p for p in watchlist if p.id]
if _selected_rows and _selected_rows[0] < len(_valid_positions):
    _sel_pos = _valid_positions[_selected_rows[0]]

    # Checks fehlend oder veraltet für diese Zeile
    _row_missing_wc = []
    if _sel_pos.id not in sc_verdicts: _row_missing_wc.append("sc")
    if _sel_pos.id not in cg_verdicts: _row_missing_wc.append("cg")
    if _sel_pos.id not in fund_verdicts: _row_missing_wc.append("fa")
    if _sel_pos.id not in ca_verdicts: _row_missing_wc.append("ca")
    if _sel_pos.id not in da_verdicts: _row_missing_wc.append("da")

    _row_stale_wc = []
    if _sel_pos.id in sc_verdicts and _is_stale(sc_verdicts[_sel_pos.id]): _row_stale_wc.append("sc")
    if _sel_pos.id in cg_verdicts and _is_stale(cg_verdicts[_sel_pos.id]): _row_stale_wc.append("cg")
    if _sel_pos.id in fund_verdicts and _is_stale(fund_verdicts[_sel_pos.id]): _row_stale_wc.append("fa")
    if _sel_pos.id in ca_verdicts and _is_stale(ca_verdicts[_sel_pos.id]): _row_stale_wc.append("ca")
    if _sel_pos.id in da_verdicts and _is_stale(da_verdicts[_sel_pos.id]): _row_stale_wc.append("da")

    _row_needs_update = list(dict.fromkeys(_row_missing_wc + _row_stale_wc))

    _nav_col1, _nav_col2, _nav_col3, _nav_spacer = st.columns([1, 1, 2, 1])
    with _nav_col1:
        if st.button(t("watchlist_analysis.nav_button"), key="nav_to_wla_btn", use_container_width=True):
            st.session_state["wla_preselect_pos_id"] = _sel_pos.id
            st.switch_page("pages/watchlist_analysis.py")
    with _nav_col2:
        if st.button(t("watchlist_checker.delete_button"), key="nav_delete_btn", use_container_width=True):
            st.session_state["_wc_delete_pending"] = {"id": _sel_pos.id, "name": _sel_pos.name}
            st.rerun()
    with _nav_col3:
        if _row_needs_update:
            _row_btn_label = (
                t("watchlist_checker.cockpit_run_row_missing").format(n=len(_row_needs_update))
                if not _row_stale_wc
                else t("watchlist_checker.cockpit_run_row_update").format(n=len(_row_needs_update))
            )
            if st.button(_row_btn_label, key="wc_run_row_btn", use_container_width=True):
                _lang = current_language()
                _pos_single = [_sel_pos]
                _row_errors: list[str] = []
                _row_jobs = []
                if "sc" in _row_needs_update: _row_jobs.append((run_storychecker_job, _pos_single, "Story"))
                if "cg" in _row_needs_update: _row_jobs.append((run_consensus_gap_job, _pos_single, "Konsens"))
                if "fa" in _row_needs_update: _row_jobs.append((run_fundamental_job, _pos_single, "Fundamental"))
                if "ca" in _row_needs_update: _row_jobs.append((run_capital_allocator_job, _pos_single, "Capital Allocator"))
                if "da" in _row_needs_update: _row_jobs.append((run_devils_advocate_job, _pos_single, "Devil's Advocate"))
                _row_total = _run_parallel(_row_jobs, _lang, _row_errors)
                if _row_errors: st.session_state["_cockpit_errors"] = _row_errors
                st.session_state["_cockpit_done_msg"] = t("watchlist_checker.cockpit_done").format(n=_row_total)
                st.rerun()

# One-click button
if n_total_missing > 0:
    n_incomplete_positions = sum(
        1 for pid in watchlist_ids
        if pid not in sc_verdicts or pid not in cg_verdicts
        or pid not in fund_verdicts or pid not in ca_verdicts or pid not in da_verdicts
    )
    st.caption(t("watchlist_checker.cockpit_missing_summary").format(
        n=n_total_missing,
        positions=n_incomplete_positions,
    ))

    if st.button(t("watchlist_checker.cockpit_run_all_missing"), key="cockpit_run_all_btn"):
        _lang = current_language()
        _errors: list[str] = []
        _all_jobs = []
        if n_missing_sc > 0:
            _all_jobs.append((run_storychecker_job, [p for p in watchlist if p.id and p.id not in sc_verdicts], "Story"))
        if n_missing_cg > 0:
            _all_jobs.append((run_consensus_gap_job, [p for p in watchlist if p.id and p.id not in cg_verdicts], "Konsens"))
        if n_missing_fund > 0:
            _all_jobs.append((run_fundamental_job, [p for p in watchlist if p.id and p.id not in fund_verdicts], "Fundamental"))
        if n_missing_ca > 0:
            _all_jobs.append((run_capital_allocator_job, [p for p in watchlist if p.id and p.id not in ca_verdicts], "Capital Allocator"))
        if n_missing_da > 0:
            _all_jobs.append((run_devils_advocate_job, [p for p in watchlist if p.id and p.id not in da_verdicts], "Devil's Advocate"))
        total_done = _run_parallel(_all_jobs, _lang, _errors)
        if _errors:
            st.session_state["_cockpit_errors"] = _errors
        st.session_state["_cockpit_done_msg"] = t("watchlist_checker.cockpit_done").format(n=total_done)
        st.rerun()
else:
    st.success(t("watchlist_checker.cockpit_all_complete"))

# Global stale update button (shown independently of missing)
if n_total_stale > 0:
    n_stale_positions = sum(
        1 for pid in watchlist_ids
        if (pid in sc_verdicts and _is_stale(sc_verdicts[pid]))
        or (pid in cg_verdicts and _is_stale(cg_verdicts[pid]))
        or (pid in fund_verdicts and _is_stale(fund_verdicts[pid]))
        or (pid in ca_verdicts and _is_stale(ca_verdicts[pid]))
        or (pid in da_verdicts and _is_stale(da_verdicts[pid]))
    )
    st.caption(t("watchlist_checker.cockpit_stale_summary").format(
        n=n_total_stale, positions=n_stale_positions
    ))
    if st.button(t("watchlist_checker.cockpit_run_all_stale").format(n=n_total_stale), key="cockpit_run_stale_btn"):
        _lang = current_language()
        _errors: list[str] = []
        _stale_jobs = []
        if n_stale_sc > 0:
            _stale_jobs.append((run_storychecker_job, [p for p in watchlist if p.id and p.id in sc_verdicts and _is_stale(sc_verdicts[p.id])], "Story"))
        if n_stale_cg > 0:
            _stale_jobs.append((run_consensus_gap_job, [p for p in watchlist if p.id and p.id in cg_verdicts and _is_stale(cg_verdicts[p.id])], "Konsens"))
        if n_stale_fund > 0:
            _stale_jobs.append((run_fundamental_job, [p for p in watchlist if p.id and p.id in fund_verdicts and _is_stale(fund_verdicts[p.id])], "Fundamental"))
        if n_stale_ca > 0:
            _stale_jobs.append((run_capital_allocator_job, [p for p in watchlist if p.id and p.id in ca_verdicts and _is_stale(ca_verdicts[p.id])], "Capital Allocator"))
        if n_stale_da > 0:
            _stale_jobs.append((run_devils_advocate_job, [p for p in watchlist if p.id and p.id in da_verdicts and _is_stale(da_verdicts[p.id])], "Devil's Advocate"))
        total_done = _run_parallel(_stale_jobs, _lang, _errors)
        if _errors:
            st.session_state["_cockpit_errors"] = _errors
        st.session_state["_cockpit_done_msg"] = t("watchlist_checker.cockpit_done").format(n=total_done)
        st.rerun()

# ─────────────────────────────────────────────────────────────────────
# Section 2: Watchlist prüfen (Main WatchlistCheckerAgent, Ollama)
# ─────────────────────────────────────────────────────────────────────

st.divider()
st.subheader(t("watchlist_checker.check_section"))
cloud_notice(agent.model, provider="ollama")

if st.button(t("watchlist_checker.run_button"), key="check_watchlist_btn"):
    _lang = current_language()

    with st.spinner(t("watchlist_checker.checking_spinner")):
        from collections import Counter
        portfolio = _portfolio_service.get_portfolio_positions()

        portfolio_snapshot = "## Portfolio Allocation (Josef's Regel)\n"
        if portfolio:
            counts = Counter(p.asset_class for p in portfolio if p.asset_class)
            total = len(portfolio)
            for asset_class, count in counts.most_common():
                pct = 100 * count / total if total else 0
                portfolio_snapshot += f"- {asset_class}: {count} Positionen ({pct:.0f}%)\n"
        else:
            portfolio_snapshot += t("watchlist_checker.empty_portfolio") + "\n"

        story_analysis_text = None
        story_analysis = portfolio_story_repo.get_latest_analysis()
        if story_analysis:
            story_analysis_text = f"""## Portfolio Story Context
Story: {story_analysis.verdict}
Summary: {story_analysis.summary}
Performance: {story_analysis.perf_verdict} - {story_analysis.perf_summary}
{t("watchlist_checker.stability_label")} {story_analysis.stability_verdict} - {story_analysis.stability_summary}

Full Analysis:
{story_analysis.full_text}
"""

        try:
            result = asyncio.run(
                agent.check_watchlist(
                    portfolio_snapshot=portfolio_snapshot,
                    watchlist_positions=watchlist,
                    story_analysis_text=story_analysis_text,
                    selected_skill=None,
                    language=_lang,
                )
            )
            st.success(t("watchlist_checker.check_done"))
            st.session_state["_watchlist_check_result"] = result

        except Exception as e:
            st.error(t("watchlist_checker.error").format(error=str(e)))

# ─────────────────────────────────────────────────────────────────────
# Section 3: Ergebnisse
# ─────────────────────────────────────────────────────────────────────

# Load result from session_state or DB
if not st.session_state.get("_watchlist_check_result"):
    if _latest_wc_result:
        st.session_state["_watchlist_check_result"] = _latest_wc_result

if st.session_state.get("_watchlist_check_result"):
    st.divider()
    st.subheader(t("watchlist_checker.results_section"))

    result = st.session_state["_watchlist_check_result"]
    result, position_fits = _normalize_result(result)

    if hasattr(result, 'created_at') and result.created_at:
        _wc_ts = result.created_at
        _wc_ts_str = _wc_ts.strftime('%d.%m.%Y %H:%M') if hasattr(_wc_ts, 'strftime') else str(_wc_ts)[:16]
        st.caption(f"Analyse vom {_wc_ts_str}")

    # Fit-counts summary
    if hasattr(result, 'fit_counts'):
        try:
            fit_counts = json.loads(result.fit_counts) if isinstance(result.fit_counts, str) else (result.fit_counts or {})
        except (json.JSONDecodeError, ValueError):
            fit_counts = {
                "sehr_passend": sum(1 for f in position_fits if f.verdict == "sehr_passend"),
                "passend": sum(1 for f in position_fits if f.verdict == "passend"),
                "neutral": sum(1 for f in position_fits if f.verdict == "neutral"),
                "nicht_passend": sum(1 for f in position_fits if f.verdict == "nicht_passend"),
            }
    else:
        fit_counts = {
            "sehr_passend": sum(1 for f in position_fits if f.verdict == "sehr_passend"),
            "passend": sum(1 for f in position_fits if f.verdict == "passend"),
            "neutral": sum(1 for f in position_fits if f.verdict == "neutral"),
            "nicht_passend": sum(1 for f in position_fits if f.verdict == "nicht_passend"),
        }

    _wc_config = VERDICT_CONFIGS["watchlist_checker"]
    st.markdown(
        f"{verdict_icon('sehr_passend', _wc_config)} {t('watchlist_checker.very_fitting')} {fit_counts.get('sehr_passend', 0)} | "
        f"{verdict_icon('passend', _wc_config)} {t('watchlist_checker.fitting')} {fit_counts.get('passend', 0)} | "
        f"{verdict_icon('neutral', _wc_config)} {t('watchlist_checker.neutral')} {fit_counts.get('neutral', 0)} | "
        f"{verdict_icon('nicht_passend', _wc_config)} {t('watchlist_checker.not_fitting')} {fit_counts.get('nicht_passend', 0)}"
    )

    st.divider()
    st.markdown(t("watchlist_checker.position_details_header"))

    # Simplified position-fit cards (sub-check details are visible in matrix above)
    for fit in position_fits:
        pos = next((p for p in watchlist if p.id == fit.position_id), None)
        if pos:
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    verdict_emoji = verdict_icon(fit.verdict, _wc_config)
                    st.markdown(f"**{verdict_emoji} {pos.name}** ({pos.ticker})")
                    st.caption(fit.summary)
                with col2:
                    st.metric("Fit", fit.verdict.replace("_", " ").title())

    # KI-Kommentar
    import hashlib
    _comment_style_id = get_app_config_repo().get("comment_style") or "humorvoll"
    _comment_style = get_style_by_id(_comment_style_id)
    comment_service = get_portfolio_comment_service(get_portfolio_comment_model())

    full_text = result.full_text if hasattr(result, 'full_text') else ""
    _ctx = f"Watchlist-Check Ergebnis:\n{full_text}"
    _ctx_hash = hashlib.md5((_ctx + _comment_style_id).encode()).hexdigest()

    if st.session_state.get("_watchlist_comment_hash") != _ctx_hash:
        st.session_state["_watchlist_comment_hash"] = _ctx_hash  # set first to prevent retry loops
        with st.spinner(f"{_comment_style['emoji']} {t('watchlist_checker.ai_comment_spinner')}"):
            try:
                st.session_state["_watchlist_comment"] = comment_service.generate_comment(_ctx, _comment_style_id)
            except Exception as _e:
                logger.warning("KI-Kommentar fehlgeschlagen: %s", _e)
                st.warning(t("watchlist_checker.ai_comment_unavailable"))

    st.divider()
    st.subheader(t("watchlist_checker.ai_comment_section"))

    if st.session_state.get("_watchlist_comment"):
        with st.container(border=True):
            st.caption(f"{_comment_style['emoji']} **{_comment_style['name']}**")
            st.markdown(st.session_state["_watchlist_comment"])

    st.divider()
    with st.expander(t("watchlist_checker.full_analysis_label")):
        st.caption(t("watchlist_checker.full_llm_label"))
        st.text(result.full_text if hasattr(result, 'full_text') else "")

        st.divider()
        st.caption(t("watchlist_checker.metadata_label"))
        latest_run = agent_runs_repo.get_latest_run("watchlist_checker")
        if latest_run:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Agent", latest_run["agent_name"])
            with col2:
                st.metric("Model", latest_run["model"])
            with col3:
                st.metric("Timestamp", latest_run["created_at"][:10])
            st.caption(f"Context: {latest_run['context_summary']}")
