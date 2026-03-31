"""
Story Checker — validates investment theses against established strategies.

Cloud ☁️ agent: only watchlist positions are sent to the API.
No portfolio quantities, purchase prices, or portfolio positions are exposed.
"""

import asyncio

import streamlit as st

from agents.storychecker_agent import STRATEGIES
from core.i18n import t
from state import get_positions_repo, get_storychecker_agent

st.set_page_config(page_title="Story Checker", page_icon="🔍", layout="wide")
st.title(f"🔍 {t('storychecker.title')}")
st.caption(t("storychecker.subtitle"))

agent = get_storychecker_agent()
st.info(t("storychecker.cloud_notice").format(model=agent._llm.model), icon="ℹ️")

# Explanation — expanded by default so new users see it immediately; collapsible after
with st.expander(t("storychecker.what_is_this"), expanded=True):
    st.markdown(t("storychecker.explanation"))

# ------------------------------------------------------------------
# Load watchlist positions that have a story
# ------------------------------------------------------------------

all_watchlist = get_positions_repo().get_watchlist()
positions_with_story = [p for p in all_watchlist if p.story]

# ------------------------------------------------------------------
# Layout: left control panel | right result
# ------------------------------------------------------------------

col_left, col_right = st.columns([1, 2])

with col_left:
    if not positions_with_story:
        st.warning(t("storychecker.no_stories"))
        st.caption(t("storychecker.no_stories_hint"))
    else:
        pos_labels = [
            f"{p.name} ({p.ticker})" if p.ticker else p.name
            for p in positions_with_story
        ]

        selected_idx = st.selectbox(
            t("storychecker.pick_position"),
            options=range(len(positions_with_story)),
            format_func=lambda i: pos_labels[i],
        )
        selected_position = positions_with_story[selected_idx]

        strategy_names = list(STRATEGIES.keys())
        selected_strategy = st.selectbox(
            t("storychecker.pick_strategy"),
            options=strategy_names,
        )

        if selected_position.story:
            with st.expander(t("storychecker.show_story"), expanded=False):
                st.markdown(selected_position.story)

        run_clicked = st.button(
            t("storychecker.run_button"),
            type="primary",
            use_container_width=True,
        )

        if run_clicked:
            with st.spinner(t("storychecker.thinking")):
                try:
                    result = asyncio.run(
                        agent.analyze(selected_position, selected_strategy)
                    )
                    st.session_state["sc_result"] = result
                    st.session_state["sc_result_meta"] = {
                        "name": selected_position.name,
                        "strategy": selected_strategy,
                    }
                except Exception as exc:
                    st.error(f"⚠️ {t('storychecker.error')}: {exc}")
            st.rerun()

with col_right:
    if "sc_result" in st.session_state:
        meta = st.session_state.get("sc_result_meta", {})
        st.caption(
            t("storychecker.result_caption").format(
                name=meta.get("name", ""),
                strategy=meta.get("strategy", ""),
            )
        )
        st.markdown(st.session_state["sc_result"])
        st.caption(t("common.ai_disclaimer"))
    else:
        st.info(t("storychecker.select_to_start"))
