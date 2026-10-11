"""Portfolio-Story — das Narrativ des Depots definieren, pflegen und das Depot daran messen.

Herausgelöst aus dem Portfolio Checker (10.10.2026): Die Story ist Pflege wie die Positionen
und braucht kein Sprachmodell. Seit 11.10.2026 steht auch der Check gegen die Story hier,
der Portfolio Checker ist ausgeblendet. KI-Entwurf und Check sind Extras; ohne erreichbares
Ollama sind sie ausgegraut (core/ui/lokales_modell.py).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import streamlit as st

from core.i18n import fmt_dt, t
from core.portfolio_snapshot import build_portfolio_snapshot
from core.storage.models import PortfolioStory, PortfolioStoryAnalysis
from core.ui.ki import ki_knopf
from core.ui.lokales_modell import hinweis_einrichten, lokales_modell_bereit
from core.ui.markdown import llm_markdown
from state import (
    get_analysis_service,
    get_market_agent,
    get_portfolio_service,
    get_portfolio_story_agent,
    get_portfolio_story_repo,
)

_ICON = {"intact": "🟢", "gemischt": "🟡", "gefaehrdet": "🔴"}

st.set_page_config(page_title="Portfolio-Story", page_icon="📖", layout="wide")
st.title(t("portfolio_story.pflege_title"))
st.caption(t("portfolio_story.pflege_subtitle"))

repo = get_portfolio_story_repo()
current_story = repo.get_current()
ki_bereit = lokales_modell_bereit()

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

    # Für beide Knöpfe gleich -- vorher nur im Speichern-Zweig gesetzt, der Entwurf scheiterte.
    target_year_val = target_year if target_year > 0 else None
    liquidity_need_val = liquidity_need if liquidity_need.strip() else None

    col1, col2 = st.columns(2)
    with col1:
        if st.form_submit_button(t("portfolio_story.save_button")):
            if current_story:
                current_story.story = story_text
                current_story.target_year = target_year_val
                current_story.liquidity_need = liquidity_need_val
                current_story.priority = priority
                repo.save(current_story)
            else:
                repo.save(PortfolioStory(
                    story=story_text,
                    target_year=target_year_val,
                    liquidity_need=liquidity_need_val,
                    priority=priority,
                ))
            st.success(t("portfolio_story.saved_success"))
            st.rerun()

    with col2:
        if ki_knopf(t("portfolio_story.ai_draft_button"), wo="lokal", key="ps_entwurf", form=True, disabled=not ki_bereit):
            if not current_story or not current_story.story:
                st.error(t("portfolio_story.ai_draft_no_story_error"))
            else:
                portfolio = get_portfolio_service().get_portfolio_positions()
                if not portfolio:
                    st.error(t("portfolio_story.ai_draft_empty_error"))
                else:
                    positions_summary = "\n".join(f"- {p.name} ({p.ticker})" for p in portfolio if p.ticker)
                    with st.spinner(t("portfolio_story.ai_draft_spinner")):
                        st.session_state["_ps_draft"] = asyncio.run(
                            get_portfolio_story_agent().generate_story_draft(
                                positions_summary=positions_summary,
                                existing_story=current_story,
                                story_text=story_text,
                                target_year=target_year_val,
                                liquidity_need=liquidity_need_val,
                                priority=priority,
                            )
                        )
                    st.rerun()
        if not ki_bereit:
            hinweis_einrichten()

if "_ps_draft" in st.session_state:
    st.info(f"{t('portfolio_story.ai_draft_label')}\n\n{st.session_state['_ps_draft']}")


# ──────────────────────────────────────────────────────────────────────
# Der Check gegen die Story (lokal): misst das Depot und die Urteile der Storychecks an der
# Story. Nur auf Knopfdruck, nie beim Oeffnen der Seite; das letzte Ergebnis steht darunter.
# ──────────────────────────────────────────────────────────────────────


def _story_check(story: PortfolioStory) -> None:
    """Ein Lauf: Snapshot mit Werten (das Modell fragt nach Gewichten und Dividenden, ohne Zahlen
    erfaende es sie) und die Storychecker-Urteile je Position, Ergebnis in die Datenbank."""
    positionen = get_portfolio_service().get_portfolio_positions()
    market_agent = get_market_agent()
    bewertungen = market_agent.get_portfolio_valuation() if market_agent else []
    snapshot = (build_portfolio_snapshot(positionen, bewertungen) if positionen
                else "## Portfolio\n" + t("portfolio_story.empty_portfolio") + "\n")

    ids = [p.id for p in positionen if p.id]
    urteile = get_analysis_service().get_all_verdicts(ids).get("storychecker", {}) if ids else {}
    zeilen = []
    for p in positionen:
        v = urteile.get(p.id) if p.id else None
        if v:
            zeilen.append(f"- {p.name} ({p.ticker}): {_ICON.get(v.verdict, '⚪')} {v.summary or v.verdict}")
        elif p.story and p.ticker:
            zeilen.append(f"- {p.name} ({p.ticker}): {t('portfolio_story.verdict_pending')}")

    with st.spinner(t("portfolio_story.analyze_spinner")):
        ergebnis = asyncio.run(get_portfolio_story_agent().analyze_story_and_performance(
            story=story,
            portfolio_snapshot=snapshot,
            position_verdicts="\n".join(zeilen) or t("portfolio_story.no_verdicts"),
        ))
    repo.save_analysis(PortfolioStoryAnalysis(
        verdict=ergebnis.verdict,
        summary=ergebnis.summary,
        perf_verdict=ergebnis.perf_verdict,
        perf_summary=ergebnis.perf_summary,
        stability_verdict=None,
        stability_summary=None,
        full_text=ergebnis.full_text,
        created_at=datetime.now(timezone.utc),
    ))


st.divider()
st.subheader(t("portfolio_story.check_title"))
st.caption(t("portfolio_story.check_subtitle"))

if ki_knopf(t("portfolio_story.check_button"), wo="lokal", key="ps_check", disabled=not ki_bereit):
    if not current_story or not current_story.story:
        st.error(t("portfolio_story.no_story_error"))
    else:
        _story_check(current_story)
        st.rerun()
if not ki_bereit:
    hinweis_einrichten()

letzte = repo.get_latest_analysis()
if letzte is None:
    st.info(t("portfolio_story.check_nie"))
else:
    if letzte.created_at:
        zeit = letzte.created_at
        if zeit.tzinfo:
            zeit = zeit.astimezone()
        st.caption(t("portfolio_story.check_vom").format(ts=fmt_dt(zeit)))
    links, rechts = st.columns(2)
    with links:
        st.metric(f"{_ICON.get(letzte.verdict, '⚪')} {t('portfolio_story.story_verdict_label')}",
                  letzte.verdict.upper())
        if letzte.summary:
            st.info(letzte.summary)
    with rechts:
        st.metric(f"{_ICON.get(letzte.perf_verdict, '⚪')} {t('portfolio_story.positions_verdict_label')}",
                  (letzte.perf_verdict or "—").upper())
        if letzte.perf_summary:
            st.info(letzte.perf_summary)
    if letzte.full_text:
        with st.expander(t("portfolio_story.full_analysis_label")):
            llm_markdown(letzte.full_text)
