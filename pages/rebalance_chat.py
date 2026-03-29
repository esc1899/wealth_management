"""
Rebalance Chat — portfolio rebalancing analysis using local Ollama LLM.
"""

import asyncio

import streamlit as st

from core.i18n import t
from state import get_rebalance_agent, get_skills_repo

st.set_page_config(page_title="Rebalance", page_icon="⚖️", layout="wide")
st.title(f"⚖️ {t('rebalance_chat.title')}")
st.caption(t("rebalance_chat.subtitle"))
st.info(t("rebalance_chat.private_notice"), icon="🔒")

agent = get_rebalance_agent()

# ------------------------------------------------------------------
# Controls
# ------------------------------------------------------------------

col_controls, col_result = st.columns([1, 2])

with col_controls:
    st.subheader(t("rebalance_chat.settings_header"))

    # Skill selector
    rebalance_skills = get_skills_repo().get_by_area("rebalance")
    if rebalance_skills:
        skill_names = [s.name for s in rebalance_skills]
        _skill_map = {s.name: s for s in rebalance_skills}
        selected_skill_name = st.selectbox(t("rebalance_chat.skill_label"), skill_names)
        selected_skill = _skill_map[selected_skill_name]
        if selected_skill.description:
            st.caption(selected_skill.description)
        skill_prompt = selected_skill.prompt
    else:
        st.warning(t("rebalance_chat.no_skill"))
        selected_skill_name = "Default"
        skill_prompt = (
            "Analyze the portfolio and suggest which positions are overweighted, "
            "underweighted, or should be trimmed."
        )

    if st.button(t("rebalance_chat.run_button"), use_container_width=True, type="primary"):
        with st.spinner(t("rebalance_chat.thinking")):
            try:
                result = asyncio.run(
                    agent.analyze(
                        skill_name=selected_skill_name,
                        skill_prompt=skill_prompt,
                    )
                )
                st.session_state["rebalance_result"] = result
                st.session_state["rebalance_skill"] = selected_skill_name
            except Exception as exc:
                st.session_state["rebalance_result"] = (
                    f"⚠️ {t('common.agent_error')}: {exc}"
                )

# ------------------------------------------------------------------
# Result panel
# ------------------------------------------------------------------

with col_result:
    if "rebalance_result" in st.session_state:
        st.subheader(
            t("rebalance_chat.result_header").format(
                skill=st.session_state.get("rebalance_skill", "")
            )
        )
        st.markdown(st.session_state["rebalance_result"])
        st.caption(t("common.ai_disclaimer"))
    else:
        st.info(t("rebalance_chat.select_skill"))
