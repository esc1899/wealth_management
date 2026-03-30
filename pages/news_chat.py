"""
News Chat — conversational news digest for portfolio positions using Claude + web search.
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

portfolio = positions_repo.get_portfolio()
ticker_map: dict[str, str] = {p.ticker: p.name for p in portfolio if p.ticker}
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
# Layout: left sidebar | right chat
# ------------------------------------------------------------------

col_sidebar, col_chat = st.columns([1, 2])

# ------------------------------------------------------------------
# Left: new digest form + past runs
# ------------------------------------------------------------------

with col_sidebar:
    st.subheader(t("news_chat.new_run"))

    if not tickers:
        st.warning(t("news_chat.empty_portfolio"))
    else:
        st.caption(f"{t('news_chat.positions_found')}: {', '.join(tickers)}")

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
            date_str = run.created_at.strftime("%d.%m.%Y %H:%M")
            ticker_count = len(run.tickers.split(", ")) if run.tickers else 0
            label = f"**{run.skill_name}**  \n{date_str} · {ticker_count} {t('news_chat.history_tickers')}"
            active = st.session_state.nc_run_id == run.id
            col_btn, col_del = st.columns([5, 1])
            if col_btn.button(
                label,
                key=f"nc_run_{run.id}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state.nc_run_id = run.id
                st.rerun()
            if col_del.button("🗑", key=f"nc_del_{run.id}"):
                news_repo.delete_run(run.id)
                if st.session_state.nc_run_id == run.id:
                    st.session_state.nc_run_id = None
                st.rerun()

# ------------------------------------------------------------------
# Right: chat interface
# ------------------------------------------------------------------

with col_chat:
    run_id = st.session_state.nc_run_id

    if run_id is None:
        st.info(t("news_chat.select_or_start"))
    else:
        run = news_repo.get_run(run_id)
        if run is None:
            st.warning(t("news_chat.run_not_found"))
            st.session_state.nc_run_id = None
        else:
            st.markdown(f"### {run.skill_name}")
            st.caption(
                f"{run.created_at.strftime('%d.%m.%Y %H:%M')} · "
                f"{run.tickers}"
            )

            messages = news_repo.get_messages(run_id)

            for i, msg in enumerate(messages):
                role = "user" if msg.role == "user" else "assistant"
                with st.chat_message(role):
                    # First assistant message = the digest → render with expanders
                    if role == "assistant" and i == 1:
                        _render_digest(msg.content)
                    else:
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
