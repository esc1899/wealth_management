"""
News Chat — recent news digest for portfolio positions using Claude + web search.
"""

import asyncio

import streamlit as st

from core.i18n import t
from state import get_news_agent, get_positions_repo, get_skills_repo

st.set_page_config(page_title="News Digest", page_icon="📰", layout="wide")
st.title(f"📰 {t('news_chat.title')}")
st.caption(t("news_chat.subtitle"))
st.info(t("news_chat.cloud_notice"), icon="ℹ️")

agent = get_news_agent()
positions_repo = get_positions_repo()

# ------------------------------------------------------------------
# Load portfolio tickers
# ------------------------------------------------------------------

portfolio = positions_repo.get_portfolio()
ticker_map: dict[str, str] = {
    p.ticker: p.name for p in portfolio if p.ticker
}
tickers = list(ticker_map.keys())

# ------------------------------------------------------------------
# Controls
# ------------------------------------------------------------------

col_controls, col_result = st.columns([1, 2])

with col_controls:
    st.subheader(t("news_chat.settings_header"))

    if not tickers:
        st.warning(t("news_chat.empty_portfolio"))
        st.stop()

    st.caption(f"{t('news_chat.positions_found')}: {', '.join(tickers)}")

    # Skill selector
    news_skills = get_skills_repo().get_by_area("news")
    if news_skills:
        skill_names = [s.name for s in news_skills]
        _skill_map = {s.name: s for s in news_skills}
        selected_skill_name = st.selectbox(t("news_chat.skill_label"), skill_names)
        selected_skill = _skill_map[selected_skill_name]
        skill_prompt = selected_skill.prompt
    else:
        st.warning(t("news_chat.no_skill"))
        selected_skill_name = "Default"
        skill_prompt = ""

    if st.button(t("news_chat.run_button"), use_container_width=True, type="primary"):
        with st.spinner(t("news_chat.thinking")):
            try:
                result = asyncio.run(
                    agent.run_digest(
                        tickers=tickers,
                        ticker_names=ticker_map,
                        skill_name=selected_skill_name,
                        skill_prompt=skill_prompt,
                    )
                )
                st.session_state["news_result"] = result
                st.session_state["news_skill"] = selected_skill_name
            except Exception as exc:
                st.session_state["news_result"] = f"⚠️ {t('common.agent_error')}: {exc}"

# ------------------------------------------------------------------
# Result panel
# ------------------------------------------------------------------

with col_result:
    if "news_result" in st.session_state:
        st.subheader(
            t("news_chat.result_header").format(
                skill=st.session_state.get("news_skill", "")
            )
        )
        st.markdown(st.session_state["news_result"])
        st.caption(t("common.ai_disclaimer"))
    else:
        st.info(t("news_chat.select_skill"))
