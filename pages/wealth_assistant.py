"""
Wealth Assistant — manage portfolio snapshots, view history, and discuss wealth trends.
Private agent using local Ollama LLM.
"""

import asyncio
from datetime import date
import streamlit as st
from config import config
from core.i18n import t
from core.llm.local import OllamaProvider
from core.llm.base import Message, Role
from state import get_wealth_snapshot_agent, get_market_agent

st.set_page_config(page_title="Wealth Assistant", page_icon="💰", layout="wide")
st.title(f"💰 {t('wealth_assistant.title')}")

wealth_agent = get_wealth_snapshot_agent()
market_agent = get_market_agent()

# ------------------------------------------------------------------
# Header: Latest snapshot summary
# ------------------------------------------------------------------
latest = wealth_agent.get_latest_snapshot()

col1, col2, col3, col4 = st.columns(4)
with col1:
    if latest:
        st.metric(
            t("wealth_assistant.latest_snapshot"),
            latest.date,
        )
    else:
        st.metric(
            t("wealth_assistant.latest_snapshot"),
            "—",
        )

with col2:
    if latest:
        st.metric(
            t("dashboard.total_wealth"),
            f"€ {latest.total_eur:,.0f}",
        )
    else:
        st.metric(
            t("dashboard.total_wealth"),
            "—",
        )

with col3:
    if latest:
        st.metric(
            t("wealth_assistant.coverage"),
            f"{latest.coverage_pct:.0f}%",
        )
    else:
        st.metric(
            t("wealth_assistant.coverage"),
            "—",
        )

with col4:
    if latest:
        st.metric(
            t("wealth_assistant.is_manual"),
            "✓" if latest.is_manual else "—",
        )
    else:
        st.metric(
            t("wealth_assistant.is_manual"),
            "—",
        )

st.divider()

# ------------------------------------------------------------------
# Action buttons: Prepare & Snapshot
# ------------------------------------------------------------------
col_prep, col_snap, col_space = st.columns([2, 2, 4])

prepare_clicked = False
snapshot_clicked = False

with col_prep:
    if st.button(
        f"🔄 {t('wealth_assistant.prepare')}",
        use_container_width=True,
        help=t("wealth_assistant.prepare_help"),
    ):
        prepare_clicked = True

with col_snap:
    if st.button(
        f"📸 {t('wealth_assistant.take_snapshot')}",
        use_container_width=True,
        help=t("wealth_assistant.take_snapshot_help"),
    ):
        snapshot_clicked = True

# Handle prepare action
if prepare_clicked:
    st.session_state["_prepare_preview"] = None
    try:
        preview = wealth_agent.prepare_snapshot()
        st.session_state["_prepare_preview"] = preview
        st.success(
            t("wealth_assistant.prepare_success")
        )
    except Exception as exc:
        st.error(f"⚠️ {t('common.agent_error')}: {exc}")

# Handle snapshot action
if snapshot_clicked:
    try:
        snapshot = wealth_agent.take_snapshot(is_manual=False)
        st.success(
            t("wealth_assistant.snapshot_success")
            + f"\n€ {snapshot.total_eur:,.0f} | {snapshot.coverage_pct:.0f}% Coverage"
        )
        st.rerun()
    except ValueError as exc:
        st.warning(f"⚠️ {str(exc)}")
    except Exception as exc:
        st.error(f"⚠️ {t('common.agent_error')}: {exc}")

# Show prepare preview if available
if st.session_state.get("_prepare_preview"):
    preview = st.session_state["_prepare_preview"]
    with st.expander(
        t("wealth_assistant.preview_title"),
        open=True,
    ):
        st.write(f"**{t('dashboard.total_wealth')}**: € {preview.total_eur:,.0f}")
        st.write(f"**{t('wealth_assistant.coverage')}**: {preview.coverage_pct:.0f}%")

        if preview.stale_positions:
            st.warning(
                f"**{t('wealth_assistant.stale_positions')}** ({len(preview.stale_positions)}):"
            )
            for pos in preview.stale_positions:
                st.write(
                    f"  • {pos['name']}: € {pos['value']:,.0f} ({pos['days_old']} Tage alt)"
                )

        if preview.warnings:
            st.info("\n".join(preview.warnings))

st.divider()

# ------------------------------------------------------------------
# LLM Chat: questions, corrections, analysis
# ------------------------------------------------------------------
st.subheader(t("wealth_assistant.chat_title"))
st.caption(t("wealth_assistant.chat_help"))

# Initialize chat state
if "_wealth_session_id" not in st.session_state:
    st.session_state["_wealth_session_id"] = None
    st.session_state["_wealth_messages"] = []
    st.session_state["_wealth_error"] = None

# Create or load session
if st.session_state["_wealth_session_id"] is None:
    try:
        # Initialize Ollama LLM (local) — reuse config from app settings
        llm = OllamaProvider(
            host=config.OLLAMA_HOST,
            model=config.OLLAMA_MODEL,
        )
        st.session_state["_wealth_llm"] = llm
        st.session_state["_wealth_session_id"] = "wealth_chat"
    except Exception as exc:
        st.error(f"⚠️ {t('common.agent_error')}: {exc}")
        st.stop()

# Display chat history
for msg in st.session_state["_wealth_messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Display any error from previous run
if st.session_state.get("_wealth_error"):
    st.error(f"⚠️ {st.session_state['_wealth_error']}")
    st.session_state["_wealth_error"] = None

# Chat input
user_input = st.chat_input(
    t("wealth_assistant.input_placeholder")
)

if user_input:
    # Add user message to history
    st.session_state["_wealth_messages"].append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    # Build context for LLM
    context = ""
    snapshots = wealth_agent.list_snapshots(days=365)
    if snapshots:
        context += f"**Letzte Snapshots (365 Tage):**\n"
        for snap in snapshots[-10:]:  # Last 10 snapshots
            context += f"- {snap.date}: € {snap.total_eur:,.0f} ({snap.coverage_pct:.0f}% Coverage)\n"

    if latest:
        context += f"\n**Letzter Snapshot Details:**\n"
        context += f"- Datum: {latest.date}\n"
        context += f"- Gesamtwert: € {latest.total_eur:,.0f}\n"
        context += f"- Aufschlüsselung: {', '.join(f'{k}: € {v:,.0f}' for k, v in latest.breakdown.items())}\n"
        context += f"- Coverage: {latest.coverage_pct:.0f}%\n"
        if latest.missing_pos:
            context += f"- Fehlende Werte: {', '.join(latest.missing_pos)}\n"

    # Prepare prompt
    system_prompt = f"""Du bist ein hilfsbereiter Vermögens-Assistent.
Du antwortest auf Fragen zum Portfolio-Vermögen und seiner Entwicklung.

{context}

Sei sachlich und konkret. Wenn Snapshots fehlen oder Daten unvollständig sind, weise darauf hin.
Wenn der Nutzer einen Snapshot korrigieren möchte, bestätige die neue Information.
"""

    # Call Ollama
    try:
        with st.spinner(t("common.thinking")):
            messages = [
                Message(Role.SYSTEM, system_prompt),
                Message(Role.USER, user_input),
            ]
            assistant_message = asyncio.run(
                st.session_state["_wealth_llm"].chat(messages, max_tokens=1024)
            )

        # Add response to history
        st.session_state["_wealth_messages"].append(
            {"role": "assistant", "content": assistant_message}
        )

        with st.chat_message("assistant"):
            st.markdown(assistant_message)

    except Exception as exc:
        st.session_state["_wealth_error"] = f"{t('common.agent_error')}: {exc}"
        st.rerun()
