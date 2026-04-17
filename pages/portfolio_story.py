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
from core.ui.verdicts import cloud_notice
from state import (
    get_analysis_service,
    get_app_config_repo,
    get_market_agent,
    get_market_repo,
    get_portfolio_comment_service,
    get_portfolio_service,
    get_portfolio_story_agent,
    get_portfolio_story_repo,
    get_skills_repo,
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
market_repo = get_market_repo()
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

    save_clicked = st.form_submit_button("💾 Speichern", use_container_width=True)

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


# ──────────────────────────────────────────────────────────────────────
# Section 2: Story Check + Performance Check
# ──────────────────────────────────────────────────────────────────────

st.subheader("2️⃣ Checks — Ausrichtung & Performance")

if not current_story:
    st.warning("⚠️ Bitte definiere zuerst deine Portfolio Story oben.")
else:
    # Pre-check: Load portfolio once for pre-check before button
    _portfolio_for_precheck = _portfolio_service.get_portfolio_positions()

    if _portfolio_for_precheck:
        # Per-agent eligible IDs — mirrors each dedicated page's filter logic
        _eligible_ids_per_agent = {
            "storychecker": [p.id for p in _portfolio_for_precheck
                             if p.id and p.story and not p.analysis_excluded],
            "fundamental":  [p.id for p in _portfolio_for_precheck
                             if p.id and p.ticker and not p.analysis_excluded],
            "consensus_gap":[p.id for p in _portfolio_for_precheck
                             if p.id and p.story and not p.analysis_excluded],
        }
        _pre_status = []

        for agent_name, agent_label, page_path in [
            ("storychecker", "Story Checker", "pages/storychecker.py"),
            ("fundamental", "Fundamental Analyzer", "pages/fundamental_analyzer.py"),
            ("consensus_gap", "Konsens-Lücken", "pages/consensus_gap.py"),
        ]:
            ids = _eligible_ids_per_agent[agent_name]
            b = _analysis_service.get_verdicts(ids, agent_name)
            n = sum(1 for pid in ids if pid not in b)

            # Get timestamp of latest analysis
            latest_ts = None
            for verdict_obj in b.values():
                if verdict_obj and hasattr(verdict_obj, 'created_at') and verdict_obj.created_at:
                    ts = verdict_obj.created_at
                    # Normalize to naive datetime for comparison
                    if hasattr(ts, 'replace'):
                        ts = ts.replace(tzinfo=None) if ts.tzinfo else ts
                    if latest_ts is None or ts > latest_ts:
                        latest_ts = ts

            ts_str = f" (zuletzt: {latest_ts.strftime('%d.%m. %H:%M')})" if latest_ts else " (noch nicht gelaufen)"

            _pre_status.append({
                "label": agent_label,
                "page": page_path,
                "n_missing": n,
                "total": len(ids),
                "timestamp": ts_str,
                "agent_name": agent_name,
            })

        _has_missing_pre = any(s["n_missing"] > 0 for s in _pre_status)
        if _has_missing_pre:
            st.info(
                "💡 Für bessere Story-Check-Ergebnisse folgende Analysen ausführen:\n"
                + "\n".join(
                    f"- {s['label']} ({s['n_missing']}/{s['total']} ausstehend){s['timestamp']}"
                    for s in _pre_status if s["n_missing"] > 0
                )
            )

            # Buttons to run missing analyses
            col_buttons_pre = st.columns(len([s for s in _pre_status if s["n_missing"] > 0]))
            for idx, s in enumerate([s for s in _pre_status if s["n_missing"] > 0]):
                with col_buttons_pre[idx]:
                    if st.button(f"→ {s['label']}", key=f"_nav_pre_{s['agent_name']}", use_container_width=True):
                        st.switch_page(s["page"])

    col_check, col_history = st.columns([2, 1])

    with col_check:
        # Skill selector for Portfolio Story
        skills_repo = get_skills_repo()
        portfolio_story_skills = skills_repo.get_by_area("portfolio_story")
        skill_options = {s.name: s for s in portfolio_story_skills if not s.hidden}

        if skill_options:
            skill_names = list(skill_options.keys())
            selected_skill_name = st.selectbox(
                "Fokus-Bereich",
                options=skill_names,
                index=0,  # Default to first skill (Josef's Regel)
                key="portfolio_story_skill",
            )
            selected_skill = skill_options[selected_skill_name]
        else:
            selected_skill = None

        if st.button("🔄 Story-Check durchführen", use_container_width=True):
            with st.spinner("Analysiere Portfolio gegen Story…"):
                # Build portfolio snapshot
                portfolio = _portfolio_service.get_portfolio_positions()
                watchlist = _portfolio_service.get_watchlist_positions()

                # Get valuations (includes all positions: tradeable + non-tradeable)
                valuations = get_market_agent().get_portfolio_valuation()

                if portfolio:
                    from core.portfolio_stability import JOSEF_CATEGORY

                    # Tradeable positions (börsengehandelt = haben ticker)
                    snapshot_lines = ["**Portfolio Snapshot (Börsengehandelte Positionen)**\n"]
                    tradeable_names = {p.name for p in portfolio if p.ticker}

                    for p in portfolio:
                        if p.ticker:  # Only show tradeable in main section
                            ticker_str = f" ({p.ticker})"
                            snapshot_lines.append(
                                f"- {p.name}{ticker_str} [{p.asset_class}]"
                            )

                    # Non-tradeable positions (keine ticker = Immobilien, Festgeld, etc.)
                    # Diese zählen in der Josef-Regel mit, müssen aber erklärt werden
                    non_tradeable_lines = []
                    for v in valuations:
                        if v.in_portfolio and not v.symbol:  # in_portfolio aber kein symbol = non-tradeable
                            josef_cat = JOSEF_CATEGORY.get(v.investment_type, "?")
                            non_tradeable_lines.append(
                                f"- {v.name} [{v.asset_class}] → {josef_cat} ({symbol()}{v.current_value_eur:,.0f})"
                            )

                    if non_tradeable_lines:
                        snapshot_lines.append("\n**Nicht-börsengehandelt (in Josef-Regel enthalten):**")
                        snapshot_lines.extend(non_tradeable_lines)

                    portfolio_snapshot = "\n".join(snapshot_lines)
                else:
                    portfolio_snapshot = "(Leeres Portfolio)"

                # Build dividend snapshot
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
                from core.portfolio_stability import compute_josef_allocation

                # Compute real Josef-Regel allocation from actual portfolio valuations
                josef = compute_josef_allocation(valuations)

                metrics = PortfolioMetrics(
                    total_value_eur=total_value,
                    total_pnl_eur=total_pnl,
                    total_pnl_pct=total_pnl_pct,
                    total_annual_dividend_eur=total_dividend,
                    portfolio_dividend_yield_pct=dividend_yield,
                    josef_aktien_pct=josef["Aktien"],
                    josef_renten_pct=josef["Renten/Geld"],
                    josef_rohstoffe_pct=josef["Rohstoffe"],
                    positions_count=len(portfolio),
                )

                # Build verdicts dict for position analysis
                pos_ids = [p.id for p in portfolio if p.id]
                verdicts_by_position = {}
                if pos_ids:
                    vs = _analysis_service.get_verdicts(pos_ids, "storychecker")
                    vf = _analysis_service.get_verdicts(pos_ids, "fundamental")
                    vc = _analysis_service.get_verdicts(pos_ids, "consensus_gap")
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
                            selected_skill=selected_skill,
                        ),
                        agent.analyze_positions(
                            story=current_story,
                            positions=portfolio,
                            verdicts=verdicts_by_position,
                        )
                    )
                    return analysis, position_fits

                analysis, position_fits = asyncio.run(run_checks())

                st.success("✅ Story-Check durchgeführt!")
                st.rerun()

    with col_history:
        st.caption("Analysen-Verlauf")
        history = repo.get_analysis_history(limit=3)
        if not history:
            st.caption("_(noch keine Analysen)_")
        else:
            for h in history:
                date_str = h.created_at.strftime("%d.%m.%Y %H:%M")
                verdict_icon = _verdict_icon(h.verdict)
                st.caption(f"{verdict_icon} {date_str}")

    if latest_analysis:
        st.divider()

        # Display analysis
        st.markdown(f"### Aktuellste Analyse — {latest_analysis.created_at.strftime('%d.%m.%Y %H:%M')}")

        # Story Check
        if latest_analysis.verdict:
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(
                        f"**Story-Urteil:** {_verdict_icon(latest_analysis.verdict)} {latest_analysis.verdict.title()}"
                    )
                    if latest_analysis.summary:
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
                    st.text(latest_analysis.full_text or "(kein Text)")

        # Performance Check
        if latest_analysis.perf_verdict:
            with st.container(border=True):
                st.markdown(
                    f"**Performance-Urteil:** {_verdict_icon(latest_analysis.perf_verdict)} {latest_analysis.perf_verdict.title()}"
                )
                if latest_analysis.perf_summary:
                    st.markdown(f"_{latest_analysis.perf_summary}_")

        # Stability Check
        if latest_analysis.stability_verdict:
            with st.container(border=True):
                st.markdown(
                    f"**Stabilitäts-Urteil:** {_verdict_icon(latest_analysis.stability_verdict)} {latest_analysis.stability_verdict.title()}"
                )
                if latest_analysis.stability_summary:
                    st.markdown(f"_{latest_analysis.stability_summary}_")

        # --- KI-Kommentar (Auto-generated, cached) ----------------------------------------------------------
        from core.services.portfolio_comment_service import get_style_by_id
        import hashlib

        _comment_style_id = get_app_config_repo().get("comment_style") or "humorvoll"
        _comment_style = get_style_by_id(_comment_style_id)
        comment_service = get_portfolio_comment_service()

        # Cache by context + style hash (regenerate only if input changes)
        _ctx = (
            f"Story: {latest_analysis.verdict} — {latest_analysis.summary}\n"
            f"Performance: {latest_analysis.perf_verdict} — {latest_analysis.perf_summary}\n"
            f"Stabilität: {latest_analysis.stability_verdict} — {latest_analysis.stability_summary}\n"
            f"Volltext:\n{latest_analysis.full_text}"
        )
        _ctx_hash = hashlib.md5((_ctx + _comment_style_id).encode()).hexdigest()

        if st.session_state.get("_story_comment_hash") != _ctx_hash:
            with st.spinner(f"{_comment_style['emoji']} Generiere Kommentar..."):
                st.session_state["_story_comment"] = comment_service.generate_comment(_ctx, _comment_style_id)
                st.session_state["_story_comment_hash"] = _ctx_hash

        if st.session_state.get("_story_comment"):
            with st.container(border=True):
                st.caption(f"{_comment_style['emoji']} **{_comment_style['name']}**")
                st.markdown(st.session_state["_story_comment"])
                if st.button("🔄 Nochmal", key="_story_comment_retry"):
                    del st.session_state["_story_comment"]
                    st.rerun()

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

portfolio = _portfolio_service.get_portfolio_positions()
if not portfolio:
    st.info("ℹ️ Portfolio ist leer.")
else:
    # Get all verdicts and position fits
    pos_ids = [p.id for p in portfolio if p.id]
    verdicts_story = _analysis_service.get_verdicts(pos_ids, "storychecker")
    verdicts_fundamental = _analysis_service.get_verdicts(pos_ids, "fundamental")
    verdicts_consensus = _analysis_service.get_verdicts(pos_ids, "consensus_gap")
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
                        fit_emoji, fit_label = _fit_role_display(pf.fit_role)
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
