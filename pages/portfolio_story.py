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
# Cash Rule Pre-Check (deterministic, always runs before KI analysis)
# ──────────────────────────────────────────────────────────────────────

def _render_cash_rule_check() -> None:
    """Display cash rule status: target vs. actual liquid cash. FEAT-18: Moved to portfolio_cash_rule area."""
    import yaml

    # Load rule parameters from "Bargeldregel" skill (FEAT-18: now in portfolio_cash_rule area)
    rule = {"target_pct": 5.0, "min_eur": 10000, "max_eur": 100000}  # defaults
    try:
        skills = get_skills_repo().get_by_area("portfolio_cash_rule")
        bargeld_skill = next((s for s in skills if s.name == "Bargeldregel"), None)
        if bargeld_skill:
            parsed = yaml.safe_load(bargeld_skill.prompt)
            if isinstance(parsed, dict):
                for key in ("target_pct", "min_eur", "max_eur"):
                    if key in parsed:
                        rule[key] = float(parsed[key])
    except Exception:
        pass  # malformed skill → use defaults

    market_agent = get_market_agent()
    valuations = market_agent.get_portfolio_valuation()

    total_eur = sum(v.current_value_eur for v in valuations if v.current_value_eur)
    if total_eur is None or total_eur <= 0:
        return

    cash_eur = sum(
        v.current_value_eur for v in valuations
        if v.investment_type == "Bargeld" and v.current_value_eur
    )

    target = max(
        rule.get("min_eur", 10000),
        min(
            rule.get("max_eur", 100000),
            total_eur * rule.get("target_pct", 5.0) / 100,
        ),
    )

    st.caption(f"💰 {t('portfolio_story.cash_rule_title')}")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(t("portfolio_story.cash_rule_total"), f"{symbol()}{total_eur:,.0f}")
    with col2:
        st.metric(t("portfolio_story.cash_rule_current"), f"{symbol()}{cash_eur:,.0f}")
    with col3:
        st.metric(t("portfolio_story.cash_rule_target"), f"{symbol()}{target:,.0f}")

    if cash_eur >= target:
        st.success(t("portfolio_story.cash_rule_success"))
    elif cash_eur >= rule.get("min_eur", 10000):
        st.warning(
            t("portfolio_story.cash_rule_warning").format(
                current=f"{symbol()}{cash_eur:,.0f}",
                target=f"{symbol()}{target:,.0f}"
            )
        )
    else:
        st.error(
            t("portfolio_story.cash_rule_error").format(
                current=f"{symbol()}{cash_eur:,.0f}",
                minimum=f"{symbol()}{rule.get('min_eur', 10000):,.0f}"
            )
        )


# ──────────────────────────────────────────────────────────────────────
# Renderer Functions for Modular Checks (FEAT-18)
# ──────────────────────────────────────────────────────────────────────

def _render_stability_check() -> None:
    """Render stability check selector and analysis. FEAT-18: Modular check."""
    skills_repo = get_skills_repo()
    stability_skills = skills_repo.get_by_area("portfolio_stability")

    if not stability_skills:
        st.info(
            "ℹ️ **Stabilitäts-Check nicht konfiguriert**\n\n"
            "Füge einen Skill unter Bereich `portfolio_stability` hinzu, um diesen Check zu aktivieren.\n\n"
            "_Skills: Josef's Regel, Sektor-Limits, Geographische Streuung_"
        )
        return

    # Skill selection reads from session_state (set by ⚙️ Einstellungen expander below)
    skill_options = {s.name: s for s in stability_skills if not s.hidden}
    skill_names = list(skill_options.keys())
    _default_skill = "Josef's Regel (3-Säulen-Stabilität)"
    _default_name = _default_skill if _default_skill in skill_names else (skill_names[0] if skill_names else None)
    _sel_name = st.session_state.get("stability_check_skill", _default_name)
    selected_skill = skill_options.get(_sel_name) or (list(skill_options.values())[0] if skill_options else None)

    # Josef-Vorschau: show current allocation before running the LLM check
    _prev_vals = get_market_agent().get_portfolio_valuation()
    if _prev_vals:
        from core.portfolio_stability import JOSEF_CATEGORY, compute_josef_allocation as _cja
        _j = _cja(_prev_vals)
        _j_total = sum(v.current_value_eur or 0 for v in _prev_vals if JOSEF_CATEGORY.get(v.investment_type))
        _unclassified = [v for v in _prev_vals if not JOSEF_CATEGORY.get(v.investment_type) and v.current_value_eur]
        c1, c2, c3 = st.columns(3)
        c1.metric("Aktien (Ziel 33%)", f"{_j['Aktien']:.0f}%", delta=f"{_j['Aktien']-33:.0f}pp")
        c2.metric("Renten/Geld (Ziel 33%)", f"{_j['Renten/Geld']:.0f}%", delta=f"{_j['Renten/Geld']-33:.0f}pp")
        c3.metric("Rohstoffe+Immo (Ziel 33%)", f"{_j['Rohstoffe']:.0f}%", delta=f"{_j['Rohstoffe']-33:.0f}pp")
        with st.expander("🔍 Josef-Details", expanded=False):
            import pandas as pd
            _rows = [
                {
                    "Position": v.name,
                    "Anlageklasse": v.asset_class,
                    "investment_type": v.investment_type,
                    "Josef-Säule": JOSEF_CATEGORY.get(v.investment_type, "⚠️ NICHT KLASSIFIZIERT"),
                    f"Wert ({symbol()})": f"{v.current_value_eur:,.0f}" if v.current_value_eur else "—",
                }
                for v in _prev_vals if v.current_value_eur and v.current_value_eur > 0
            ]
            if _rows:
                st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)
            if _unclassified:
                st.warning(
                    f"⚠️ {len(_unclassified)} Position(en) nicht klassifiziert — fehlen in Josef-Berechnung:\n"
                    + "\n".join(f"- {v.name} (investment_type: `{v.investment_type}`)" for v in _unclassified)
                )

    if st.button("🔄 Stabilitäts-Check durchführen", use_container_width=True, key="btn_stability"):
        with st.spinner("Analysiere Stabilität…"):
            valuations = get_market_agent().get_portfolio_valuation()
            portfolio = _portfolio_service.get_portfolio_positions()

            # Build portfolio snapshot (same as in story check)
            snapshot_lines = ["**Portfolio Snapshot**\n"]
            for p in portfolio:
                if p.ticker:
                    ticker_str = f" ({p.ticker})"
                    snapshot_lines.append(f"- {p.name}{ticker_str} [{p.asset_class}]")

            from core.portfolio_stability import JOSEF_CATEGORY, compute_josef_allocation
            from agents.portfolio_story_agent import PortfolioMetrics

            # Non-tradeable positions (use portfolio list — v.symbol always truthy due to name[:10] fallback)
            valuation_map = {v.name: v for v in valuations}
            non_tradeable = [p for p in portfolio if not p.ticker]
            non_tradeable_lines = []
            for p in non_tradeable:
                v = valuation_map.get(p.name)
                if v and v.current_value_eur:
                    josef_cat = JOSEF_CATEGORY.get(p.investment_type, "?")
                    non_tradeable_lines.append(
                        f"- {p.name} [{p.asset_class}] → {josef_cat} ({symbol()}{v.current_value_eur:,.0f})"
                    )

            if non_tradeable_lines:
                snapshot_lines.append("\n**Nicht-börsengehandelt:**")
                snapshot_lines.extend(non_tradeable_lines)

            # Physical Immobilien
            physical_immo = [v for v in valuations if v.in_portfolio and v.asset_class in {"Immobilie", "Grundstück"}]
            if physical_immo:
                snapshot_lines.append("\n**Direkte Immobilien:**")
                for v in physical_immo:
                    snapshot_lines.append(f"- {v.name}: {symbol()}{v.current_value_eur:,.0f}")
            else:
                snapshot_lines.append("\n**Direkte Immobilien: keine**")

            portfolio_snapshot = "\n".join(snapshot_lines)

            # Compute metrics
            total_value = sum(v.current_value_eur or 0 for v in valuations)
            total_cost = sum(v.cost_basis_eur or 0 for v in valuations)
            total_pnl = total_value - total_cost
            total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
            total_dividend = sum(v.annual_dividend_eur or 0 for v in valuations)
            dividend_yield = (total_dividend / total_value * 100) if total_value > 0 else 0

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

            # Run stability check
            async def run_stability_check():
                return await agent.analyze_stability(
                    metrics=metrics,
                    portfolio_snapshot=portfolio_snapshot,
                    skill_prompt=selected_skill.prompt,
                )

            stability_result = asyncio.run(run_stability_check())

            # Store in session state for display
            st.session_state["_stability_result"] = stability_result
            st.success("✅ Stabilitäts-Check durchgeführt!")
            st.rerun()


def _render_story_check() -> None:
    """Render story & performance check. FEAT-18: Modular check."""
    if not current_story:
        st.info("ℹ️ **Portfolio Story erforderlich**\n\nDefiniere deine Portfolio Story im Abschnitt 1.")
        return

    skills_repo = get_skills_repo()
    story_skills = skills_repo.get_by_area("portfolio_story")

    # Skill selection reads from session_state (set by ⚙️ Einstellungen expander below)
    skill_options = {s.name: s for s in story_skills if not s.hidden} if story_skills else {}
    _NO_FOCUS = " — (kein spezifischer Fokus)"
    _sel_story = st.session_state.get("story_check_skill", _NO_FOCUS)
    selected_skill = skill_options.get(_sel_story) if skill_options else None

    if st.button("🔄 Story-Check durchführen", use_container_width=True, key="btn_story"):
        with st.spinner("Analysiere Story & Performance…"):
            valuations = get_market_agent().get_portfolio_valuation()
            portfolio = _portfolio_service.get_portfolio_positions()

            # Build portfolio snapshot
            snapshot_lines = ["**Portfolio Snapshot (Börsengehandelte Positionen)**\n"]
            for p in portfolio:
                if p.ticker:
                    ticker_str = f" ({p.ticker})"
                    snapshot_lines.append(f"- {p.name}{ticker_str} [{p.asset_class}]")

            from core.portfolio_stability import JOSEF_CATEGORY

            # Non-tradeable positions (use portfolio list — v.symbol always truthy due to name[:10] fallback)
            valuation_map_s = {v.name: v for v in valuations}
            non_tradeable_s = [p for p in portfolio if not p.ticker]
            non_tradeable_lines = []
            for p in non_tradeable_s:
                v = valuation_map_s.get(p.name)
                if v and v.current_value_eur:
                    josef_cat = JOSEF_CATEGORY.get(p.investment_type, "?")
                    non_tradeable_lines.append(
                        f"- {p.name} [{p.asset_class}] → {josef_cat} ({symbol()}{v.current_value_eur:,.0f})"
                    )

            if non_tradeable_lines:
                snapshot_lines.append("\n**Nicht-börsengehandelt (in Josef-Regel enthalten):**")
                snapshot_lines.extend(non_tradeable_lines)

            physical_immo = [v for v in valuations if v.in_portfolio and v.asset_class in {"Immobilie", "Grundstück"}]
            if physical_immo:
                snapshot_lines.append("\n**Direkte Immobilien (physisch, nicht fondbasiert):**")
                for v in physical_immo:
                    snapshot_lines.append(f"- {v.name} [{v.asset_class}]: {symbol()}{v.current_value_eur:,.0f}")
            else:
                snapshot_lines.append("\n**Direkte Immobilien (physisch): keine im Portfolio**")

            portfolio_snapshot = "\n".join(snapshot_lines)

            # Build dividend snapshot
            dividend_lines = []
            for v in valuations:
                if v.annual_dividend_eur and v.annual_dividend_eur > 0:
                    dividend_lines.append(
                        f"- {v.name}: {symbol()}{v.annual_dividend_eur:.0f}/Jahr ({v.dividend_yield_pct*100:.1f}%)"
                    )
            dividend_snapshot = "\n".join(dividend_lines) or "(Keine Dividenden)"

            # Run story & performance check
            async def run_story_check():
                return await agent.analyze_story_and_performance(
                    story=current_story,
                    portfolio_snapshot=portfolio_snapshot,
                    dividend_snapshot=dividend_snapshot,
                    skill_prompt=selected_skill.prompt if selected_skill else None,
                    inflation_rate=None,
                )

            story_result = asyncio.run(run_story_check())
            st.session_state["_story_result"] = story_result
            st.success("✅ Story-Check durchgeführt!")
            st.rerun()


# ──────────────────────────────────────────────────────────────────────
# Section 2: Checks — collapsible expander with modular checks
# ──────────────────────────────────────────────────────────────────────

with st.expander("2️⃣ Checks — Ausrichtung & Performance & Stabilität", expanded=True):
    if not current_story:
        st.warning("⚠️ Bitte definiere zuerst deine Portfolio Story oben.")
    else:
        # 💰 Bargeldregel — always show at top of checks section
        _render_cash_rule_check()

        st.divider()

        # Stabilitäts-Check
        st.caption("**Stabilitäts-Check:**")
        _render_stability_check()

        if st.session_state.get("_stability_result"):
            with st.container(border=True):
                sr = st.session_state["_stability_result"]
                st.markdown(f"**Stabilitäts-Urteil:** {_verdict_icon(sr.verdict)} {sr.verdict.title()}")
                if sr.summary:
                    st.markdown(f"_{sr.summary}_")
                with st.expander("Details"):
                    st.text(sr.full_text)

        st.divider()

        # Story & Performance Check
        st.caption("**Story & Performance Check:**")
        _render_story_check()

        if st.session_state.get("_story_result"):
            with st.container(border=True):
                sr = st.session_state["_story_result"]
                st.markdown(f"**Story-Urteil:** {_verdict_icon(sr.verdict)} {sr.verdict.title()}")
                if sr.summary:
                    st.markdown(f"_{sr.summary}_")

            with st.container(border=True):
                sr = st.session_state["_story_result"]
                st.markdown(f"**Performance-Urteil:** {_verdict_icon(sr.perf_verdict)} {sr.perf_verdict.title()}")
                if sr.perf_summary:
                    st.markdown(f"_{sr.perf_summary}_")

        # ⚙️ Einstellungen — skill selectors (collapsed by default)
        _stability_skills_for_settings = get_skills_repo().get_by_area("portfolio_stability")
        _story_skills_for_settings = get_skills_repo().get_by_area("portfolio_story")
        if _stability_skills_for_settings or _story_skills_for_settings:
            with st.expander("⚙️ Einstellungen", expanded=False):
                if _stability_skills_for_settings:
                    _stab_opts = [s.name for s in _stability_skills_for_settings if not s.hidden]
                    _stab_default = "Josef's Regel (3-Säulen-Stabilität)"
                    _stab_idx = _stab_opts.index(_stab_default) if _stab_default in _stab_opts else 0
                    st.selectbox(
                        "Stabilitäts-Fokus",
                        options=_stab_opts,
                        index=_stab_idx,
                        key="stability_check_skill",
                    )
                if _story_skills_for_settings:
                    _story_opts = [s.name for s in _story_skills_for_settings if not s.hidden]
                    _NO_FOCUS = " — (kein spezifischer Fokus)"
                    st.selectbox(
                        "Story-Fokus (optional)",
                        options=[_NO_FOCUS] + _story_opts,
                        index=0,
                        key="story_check_skill",
                    )

        # Aktuellste gespeicherte Analyse (legacy data from analyze())
        if latest_analysis:
            st.divider()
            st.markdown(f"### Aktuellste Analyse — {latest_analysis.created_at.strftime('%d.%m.%Y %H:%M')}")

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
                            st.session_state["_expand_story"] = not st.session_state.get("_expand_story", False)

                    if st.session_state.get("_expand_story"):
                        st.markdown("---")
                        st.caption("Aus der vollständigen Analyse:")
                        st.text(latest_analysis.full_text or "(kein Text)")

            if latest_analysis.perf_verdict:
                with st.container(border=True):
                    st.markdown(
                        f"**Performance-Urteil:** {_verdict_icon(latest_analysis.perf_verdict)} {latest_analysis.perf_verdict.title()}"
                    )
                    if latest_analysis.perf_summary:
                        st.markdown(f"_{latest_analysis.perf_summary}_")

            if latest_analysis.stability_verdict:
                with st.container(border=True):
                    st.markdown(
                        f"**Stabilitäts-Urteil:** {_verdict_icon(latest_analysis.stability_verdict)} {latest_analysis.stability_verdict.title()}"
                    )
                    if latest_analysis.stability_summary:
                        st.markdown(f"_{latest_analysis.stability_summary}_")

            from core.services.portfolio_comment_service import get_style_by_id
            import hashlib

            _comment_style_id = get_app_config_repo().get("comment_style") or "humorvoll"
            _comment_style = get_style_by_id(_comment_style_id)
            comment_service = get_portfolio_comment_service()

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

# ──────────────────────────────────────────────────────────────────────
# Section 3: Positions-Checks (pending status + navigation)
# ──────────────────────────────────────────────────────────────────────

if current_story:
    st.subheader("3️⃣ Positions-Checks")

    _portfolio_for_checks = _portfolio_service.get_portfolio_positions()
    if _portfolio_for_checks:
        _eligible_ids_per_agent = {
            "storychecker": [p.id for p in _portfolio_for_checks
                             if p.id and p.story and not p.analysis_excluded],
            "fundamental":  [p.id for p in _portfolio_for_checks
                             if p.id and p.ticker and not p.analysis_excluded],
            "consensus_gap":[p.id for p in _portfolio_for_checks
                             if p.id and p.story and not p.analysis_excluded],
        }
        _agent_configs = [
            ("storychecker", "Story Checker", "pages/storychecker.py"),
            ("fundamental", "Fundamental Analyzer", "pages/fundamental_analyzer.py"),
            ("consensus_gap", "Konsens-Lücken", "pages/consensus_gap.py"),
        ]
        _pre_status = []
        for agent_name, agent_label, page_path in _agent_configs:
            ids = _eligible_ids_per_agent[agent_name]
            b = _analysis_service.get_verdicts(ids, agent_name)
            n = sum(1 for pid in ids if pid not in b)
            latest_ts = None
            for verdict_obj in b.values():
                if verdict_obj and hasattr(verdict_obj, 'created_at') and verdict_obj.created_at:
                    ts = verdict_obj.created_at
                    if hasattr(ts, 'replace'):
                        ts = ts.replace(tzinfo=None) if ts.tzinfo else ts
                    if latest_ts is None or ts > latest_ts:
                        latest_ts = ts
            ts_str = latest_ts.strftime("%d.%m. %H:%M") if latest_ts else "—"
            _pre_status.append({
                "label": agent_label,
                "page": page_path,
                "n_missing": n,
                "total": len(ids),
                "ts_str": ts_str,
                "agent_name": agent_name,
            })

        # Metrics row: pending counts per agent
        _metric_cols = st.columns(len(_pre_status))
        for idx, s in enumerate(_pre_status):
            with _metric_cols[idx]:
                st.metric(
                    s["label"],
                    f"{s['n_missing']}/{s['total']} ausstehend",
                    help=f"Zuletzt: {s['ts_str']}",
                )

        _include_prechecks = st.checkbox(
            "☑ Portfolio-Checks (Stabilität + Story) vor Positions-Check ausführen",
            key="_ps_include_prechecks",
            value=False,
        )

        _AUTO_RUN_FLAGS = {
            "storychecker": "_auto_run_storychecker",
            "consensus_gap": "_auto_run_consensus_gap",
        }

        _btn_cols = st.columns(len(_pre_status))
        for idx, s in enumerate(_pre_status):
            with _btn_cols[idx]:
                _has_pending = s["n_missing"] > 0
                _btn_label = (
                    f"→ {s['label']}: {s['n_missing']} prüfen"
                    if _has_pending
                    else f"✅ {s['label']}: alle geprüft"
                )
                if s["agent_name"] == "fundamental":
                    if st.button(f"→ {s['label']}", key=f"_nav_{s['agent_name']}", use_container_width=True):
                        st.switch_page(s["page"])
                else:
                    if st.button(
                        _btn_label,
                        key=f"_nav_{s['agent_name']}",
                        use_container_width=True,
                        disabled=not _has_pending,
                    ):
                        if _include_prechecks:
                            with st.spinner("Führe Portfolio-Checks durch…"):
                                from core.portfolio_stability import JOSEF_CATEGORY, compute_josef_allocation
                                from agents.portfolio_story_agent import PortfolioMetrics
                                _vals = get_market_agent().get_portfolio_valuation()
                                _port = _portfolio_service.get_portfolio_positions()
                                _vmap = {v.name: v for v in _vals}
                                _snap = ["**Portfolio Snapshot**\n"]
                                for _p in _port:
                                    if _p.ticker:
                                        _snap.append(f"- {_p.name} ({_p.ticker}) [{_p.asset_class}]")
                                _nt = [_p for _p in _port if not _p.ticker]
                                _nt_lines = []
                                for _p in _nt:
                                    _v = _vmap.get(_p.name)
                                    if _v and _v.current_value_eur:
                                        _jcat = JOSEF_CATEGORY.get(_p.investment_type, "?")
                                        _nt_lines.append(f"- {_p.name} [{_p.asset_class}] → {_jcat} ({symbol()}{_v.current_value_eur:,.0f})")
                                if _nt_lines:
                                    _snap.append("\n**Nicht-börsengehandelt:**")
                                    _snap.extend(_nt_lines)
                                _snap_str = "\n".join(_snap)
                                _tv = sum(v.current_value_eur or 0 for v in _vals)
                                _tc = sum(v.cost_basis_eur or 0 for v in _vals)
                                _josef = compute_josef_allocation(_vals)
                                _metrics = PortfolioMetrics(
                                    total_value_eur=_tv,
                                    total_pnl_eur=_tv - _tc,
                                    total_pnl_pct=((_tv - _tc) / _tc * 100) if _tc > 0 else 0,
                                    total_annual_dividend_eur=sum(v.annual_dividend_eur or 0 for v in _vals),
                                    portfolio_dividend_yield_pct=(sum(v.annual_dividend_eur or 0 for v in _vals) / _tv * 100) if _tv > 0 else 0,
                                    josef_aktien_pct=_josef["Aktien"],
                                    josef_renten_pct=_josef["Renten/Geld"],
                                    josef_rohstoffe_pct=_josef["Rohstoffe"],
                                    positions_count=len(_port),
                                )
                                _stab_skills = get_skills_repo().get_by_area("portfolio_stability")
                                if _stab_skills:
                                    _stab_opts = {s.name: s for s in _stab_skills if not s.hidden}
                                    _stab_sel = st.session_state.get("stability_check_skill", "Josef's Regel (3-Säulen-Stabilität)")
                                    _stab_skill = _stab_opts.get(_stab_sel) or list(_stab_opts.values())[0]
                                    async def _run_stab():
                                        return await agent.analyze_stability(
                                            metrics=_metrics,
                                            portfolio_snapshot=_snap_str,
                                            skill_prompt=_stab_skill.prompt,
                                        )
                                    st.session_state["_stability_result"] = asyncio.run(_run_stab())
                        flag = _AUTO_RUN_FLAGS.get(s["agent_name"])
                        if flag:
                            st.session_state[flag] = True
                        st.switch_page(s["page"])

st.divider()

# ──────────────────────────────────────────────────────────────────────
# Section 4: Investment Overview — How each position fits the story
# ──────────────────────────────────────────────────────────────────────

st.subheader("4️⃣ Einzelne Investitionen — Passung zur Portfolio Story")

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
