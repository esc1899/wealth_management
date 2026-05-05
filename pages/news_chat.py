"""
News Chat — conversational news digest for portfolio positions using Claude + web search.
"""

import asyncio

import streamlit as st

from core.i18n import t
from core.ui.verdicts import cloud_notice
from state import get_news_agent, get_news_repo, get_positions_repo, get_skills_repo

st.set_page_config(page_title="News Digest", page_icon="📰", layout="wide")
st.title(f"📰 {t('news_chat.title')}")
st.caption(t("news_chat.subtitle"))
agent = get_news_agent()
cloud_notice(agent.model, "claude")
news_repo = get_news_repo()
positions_repo = get_positions_repo()

portfolio = positions_repo.get_portfolio()
_NEWS_ASSET_CLASSES = {"Aktie", "Aktienfonds", "Kryptowährung"}  # only asset classes with company/project news
ticker_map: dict[str, str] = {
    p.ticker: p.name for p in portfolio
    if p.ticker and p.asset_class in _NEWS_ASSET_CLASSES
}
tickers = list(ticker_map.keys())

if "nc_run_id" not in st.session_state:
    st.session_state.nc_run_id = None

# ------------------------------------------------------------------
# Helper: render digest as expandable sections
# ------------------------------------------------------------------

def _render_digest(result: str):
    """Split markdown digest by ## sections and render each as an expander."""
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
        st.markdown(result)
        return

    for section in sections:
        lines = section.strip().splitlines()
        if not lines:
            continue
        header = lines[0].lstrip("# ").strip()
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
# Helper: delete run helper function (für Inline-History Delete)
# ------------------------------------------------------------------

def _delete_run_and_rerun(run_id: int):
    """Delete a news run and reset session state if needed."""
    news_repo.delete_run(run_id)
    if st.session_state.nc_run_id == run_id:
        st.session_state.nc_run_id = None
    st.rerun()

# ------------------------------------------------------------------
# Layout: left narrow | right wide
# ------------------------------------------------------------------

col_left, col_right = st.columns([0.8, 2.2], gap="medium")

# ------------------------------------------------------------------
# Left: new digest form + compact past runs list
# ------------------------------------------------------------------

with col_left:
    st.subheader(t("news_chat.new_run"))

    if not tickers:
        st.warning(t("news_chat.empty_portfolio"))
    else:
        st.caption(f"{len(tickers)} {t('news_chat.history_tickers')}")

        news_skills = get_skills_repo().get_by_area("news")

        with st.form("new_digest_form"):
            if news_skills:
                skill_names = [s.name for s in news_skills]
                _skill_map = {s.name: s for s in news_skills}
                skill_choice = st.selectbox(t("news_chat.skill_label"), skill_names)
            else:
                st.warning(t("news_chat.no_skill"))
                skill_choice = None

            focus_input = st.text_input(
                t("news_chat.focus_label"),
                placeholder=t("news_chat.focus_placeholder"),
            ).strip()

            submitted = st.form_submit_button(
                t("news_chat.start_button"), use_container_width=True
            )

        if submitted and skill_choice:
            selected_skill = _skill_map[skill_choice]
            with st.spinner(t("news_chat.thinking")):
                try:
                    run, _ = asyncio.run(
                        agent.start_run(
                            tickers=tickers,
                            ticker_names=ticker_map,
                            skill_name=selected_skill.name,
                            skill_prompt=selected_skill.prompt,
                            user_context=focus_input,
                            repo=news_repo,
                        )
                    )
                    st.session_state.nc_run_id = run.id
                except Exception as exc:
                    st.error(f"⚠️ {t('common.agent_error')}: {exc}")
            st.rerun()

    st.divider()
    st.subheader(t("news_chat.past_runs"))

    past_runs = news_repo.list_runs(limit=30)
    if not past_runs:
        st.info(t("news_chat.no_runs"))
    else:
        for run in past_runs:
            date_str = run.created_at.strftime("%d.%m.%Y")
            ticker_count = len(run.tickers.split(", ")) if run.tickers else 0
            active = st.session_state.nc_run_id == run.id
            col_btn, col_del = st.columns([5, 1])
            label = f"{date_str} · {run.skill_name} · {ticker_count}"
            if col_btn.button(
                label,
                key=f"nc_run_{run.id}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state.nc_run_id = run.id
                st.rerun()
            if col_del.button("🗑", key=f"nc_del_{run.id}"):
                _delete_run_and_rerun(run.id)

# ------------------------------------------------------------------
# Right: current result (digest + history) + follow-up chat
# ------------------------------------------------------------------

with col_right:
    run_id = st.session_state.nc_run_id

    if run_id is None:
        st.info(t("news_chat.select_or_start"))
    else:
        run = news_repo.get_run(run_id)
        if run is None:
            st.warning(t("news_chat.run_not_found"))
            st.session_state.nc_run_id = None
        else:
            ticker_count = len(run.tickers.split(", ")) if run.tickers else 0

            # Header
            st.markdown(f"### 📰 {run.skill_name}")
            st.caption(
                f"{run.created_at.strftime('%d.%m.%Y %H:%M')} · "
                f"{ticker_count} {t('news_chat.history_tickers')}"
            )

            messages = news_repo.get_messages(run_id)

            # Full-Text Digest (from messages[1], analog to agent_messages pattern)
            digest_text = messages[1].content if len(messages) > 1 else run.result
            with st.expander("▼ " + t("storychecker.full_analysis"), expanded=True):
                _render_digest(digest_text)

            # Older runs (inline history)
            all_runs = news_repo.list_runs(limit=30)
            older_runs = [r for r in all_runs if r.id != run_id]
            if older_runs:
                with st.expander(
                    f"{t('storychecker.verdict_history')} ({len(older_runs)})",
                    expanded=False,
                ):
                    for older_run in older_runs:
                        older_ticker_count = (
                            len(older_run.tickers.split(", "))
                            if older_run.tickers
                            else 0
                        )
                        older_date = older_run.created_at.strftime("%d.%m.%Y")
                        col_btn, col_del = st.columns([5, 1])
                        if col_btn.button(
                            f"{older_date} · {older_run.skill_name} · {older_ticker_count}",
                            key=f"nc_older_{older_run.id}",
                            use_container_width=True,
                        ):
                            st.session_state.nc_run_id = older_run.id
                            st.rerun()
                        if col_del.button(
                            "🗑", key=f"nc_del_older_{older_run.id}"
                        ):
                            _delete_run_and_rerun(older_run.id)

            st.divider()

            # Follow-up chat (skip initial user message + digest)
            followup_messages = messages[2:] if len(messages) > 2 else []
            for msg in followup_messages:
                role = "user" if msg.role == "user" else "assistant"
                with st.chat_message(role):
                    st.markdown(msg.content)
                    if role == "assistant":
                        st.caption(t("common.ai_disclaimer"))

            if prompt := st.chat_input(t("news_chat.chat_placeholder")):
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    with st.spinner(t("news_chat.thinking")):
                        try:
                            response = asyncio.run(
                                agent.chat(run_id, prompt, news_repo)
                            )
                        except Exception as exc:
                            response = f"⚠️ {t('common.agent_error')}: {exc}"
                    st.markdown(response)
                    st.caption(t("common.ai_disclaimer"))
                st.rerun()
