"""Portfolio-Story — das Narrativ des Depots definieren und pflegen (Bereich Pflege).

Herausgelöst aus dem Portfolio Checker (10.10.2026): Die Story ist Pflege wie die Positionen
und braucht kein Sprachmodell. Der Portfolio Checker liest sie von hier. Der KI-Entwurf ist
ein Extra; ohne erreichbares Ollama ist er ausgegraut (core/ui/lokales_modell.py).
"""

from __future__ import annotations

import asyncio

import streamlit as st

from core.i18n import t
from core.storage.models import PortfolioStory
from core.ui.lokales_modell import hinweis_einrichten, lokales_modell_bereit
from state import get_portfolio_service, get_portfolio_story_agent, get_portfolio_story_repo

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
        if st.form_submit_button(t("portfolio_story.ai_draft_button"), disabled=not ki_bereit):
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
