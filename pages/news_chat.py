"""
News Chat — recent news digest for portfolio positions using Claude + web search.
Results are persisted and accessible from the sidebar history.
"""

import asyncio

import streamlit as st

from core.i18n import t
from state import get_news_agent, get_news_repo, get_positions_repo, get_skills_repo

st.set_page_config(page_title="News Digest", page_icon="📰", layout="wide")
st.title(f"📰 {t('news_chat.title')}")
st.caption(t("news_chat.subtitle"))
st.info(t("news_chat.cloud_notice"), icon="ℹ️")

agent = get_news_agent()
news_repo = get_news_repo()
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
# Sidebar — past runs
# ------------------------------------------------------------------

def _render_sidebar():
    past_runs = news_repo.list_runs(limit=30)
    if not past_runs:
        st.sidebar.caption(t("news_chat.no_history"))
        return

    st.sidebar.subheader(t("news_chat.history_header"))
    for run in past_runs:
        date_str = run.created_at.strftime("%Y-%m-%d %H:%M")
        ticker_count = len(run.tickers.split(", ")) if run.tickers else 0
        label = f"{date_str} · {run.skill_name} · {ticker_count} {t('news_chat.history_tickers')}"
        col_btn, col_del = st.sidebar.columns([5, 1])
        if col_btn.button(label, key=f"run_{run.id}", use_container_width=True):
            st.session_state["news_result"] = run.result
            st.session_state["news_skill"] = run.skill_name
            st.rerun()
        if col_del.button("🗑", key=f"del_{run.id}"):
            news_repo.delete_run(run.id)
            if st.session_state.get("news_run_id") == run.id:
                st.session_state.pop("news_result", None)
                st.session_state.pop("news_skill", None)
                st.session_state.pop("news_run_id", None)
            st.rerun()


_render_sidebar()


# ------------------------------------------------------------------
# Helper: render digest as expandable sections
# ------------------------------------------------------------------

def _render_digest(result: str):
    """Split markdown digest by ## sections and render each as an expander."""
    # Split on section headers — each position gets its own ## block
    sections = []
    current: list[str] = []
    for line in result.splitlines():
        if line.startswith("## ") and current:
            sections.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current))

    if not sections or (len(sections) == 1 and not sections[0].startswith("## ")):
        # No sections found — fall back to plain markdown
        st.markdown(result)
        return

    for section in sections:
        lines = section.strip().splitlines()
        if not lines:
            continue

        header = lines[0].lstrip("# ").strip()  # e.g. "AAPL — Apple Inc."

        # Pick assessment emoji for the expander label
        body = "\n".join(lines[1:])
        if "🔴" in body:
            emoji = "🔴"
        elif "🟡" in body:
            emoji = "🟡"
        else:
            emoji = "🟢"

        with st.expander(f"{emoji} {header}", expanded=False):
            st.markdown(body)


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
                run = news_repo.save_run(
                    skill_name=selected_skill_name,
                    tickers=tickers,
                    result=result,
                )
                st.session_state["news_result"] = result
                st.session_state["news_skill"] = selected_skill_name
                st.session_state["news_run_id"] = run.id
            except Exception as exc:
                st.error(f"⚠️ {t('common.agent_error')}: {exc}")
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
        _render_digest(st.session_state["news_result"])
        st.caption(t("common.ai_disclaimer"))
    else:
        st.info(t("news_chat.select_skill"))
