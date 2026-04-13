"""
Investment Kompass — Portfolio-wide investment analysis with full context.
Permanent "under construction" state for transparency about AI limitations.
"""

import asyncio
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="🧭 Investment Kompass", layout="wide")

from state import (
    get_investment_compass_agent,
    get_skills_repo,
    get_agent_runs_repo,
    get_app_config_repo,
    get_portfolio_comment_service,
)

# ─────────────────────────────────────────────────────────────────────

st.title("🧭 Investment Kompass")

# Baustellenschild — permanent (Humor)
st.warning(
    """**🚧 UNDER CONSTRUCTION**

Dieser Agent ist dauerhaft im Bau. KI-Investmentberatung wäre sowieso illegal —
wir nennen das lieber "strukturierte Gedankenexperimente".
"""
)

# ─────────────────────────────────────────────────────────────────────
# Section 1: Strategie-Auswahl
# ─────────────────────────────────────────────────────────────────────

st.subheader("1️⃣ Strategie wählen")

skills_repo = get_skills_repo()
rebalance_skills = skills_repo.get_by_area("rebalance") or []

if not rebalance_skills:
    st.warning("⚠️ Keine Strategien definiert. Bitte zuerst Settings überprüfen.")
    st.stop()

skill_options = {s.name: s for s in rebalance_skills}
selected_skill_name = st.selectbox(
    "Welche Strategie möchtest du verwenden?",
    options=list(skill_options.keys()),
    key="compass_strategy_select",
)
selected_skill = skill_options[selected_skill_name]

# ─────────────────────────────────────────────────────────────────────
# Section 2: User Input
# ─────────────────────────────────────────────────────────────────────

st.subheader("2️⃣ Deine Frage / Kontext")

user_query = st.text_area(
    "Was möchtest du zum Portfolio wissen?",
    placeholder="Beispiele:\n- Soll ich meine Tech-Position reduzieren?\n- Passt Gold noch zu meiner Story?\n- Wie robust ist mein Portfolio gegen Inflation?",
    height=120,
    key="compass_query_input",
)

# ─────────────────────────────────────────────────────────────────────
# Section 3: Run Analysis
# ─────────────────────────────────────────────────────────────────────

if st.button("▶️ Analysieren", key="compass_analyze_btn", use_container_width=True, type="primary"):
    if not user_query.strip():
        st.warning("⚠️ Bitte gib deine Frage ein.")
    else:
        with st.spinner("Kontext wird aufgebaut..."):
            try:
                agent = get_investment_compass_agent()
                agent_runs_repo = get_agent_runs_repo()

                # Run analysis
                result = asyncio.run(
                    agent.analyze(
                        user_query=user_query,
                        skill_name=selected_skill.name,
                        skill_prompt=selected_skill.prompt,
                    )
                )

                # Log to agent_runs
                agent_runs_repo.log_run(
                    agent_name="investment_kompass",
                    model=agent.model,
                    skills_used=[selected_skill.name],
                    agent_deps=result.lineage.get("agents_used", []),
                    output_summary=result.response[:200] if result.response else "No response",
                    context_summary=f"Context from: {', '.join(result.lineage.get('agents_used', []))}",
                )

                st.session_state["_compass_result"] = result
                st.success("✅ Analyse abgeschlossen!")

            except Exception as e:
                st.error(f"❌ Fehler: {e}")
                import traceback
                st.text(traceback.format_exc())

# ─────────────────────────────────────────────────────────────────────
# Section 4: Display Results
# ─────────────────────────────────────────────────────────────────────

if st.session_state.get("_compass_result"):
    st.divider()
    st.subheader("📊 Analyse")

    result = st.session_state["_compass_result"]

    with st.container(border=True):
        st.markdown(result.response)

    # --- Kontext-Details (aufklappbar) ---

    with st.expander("🔍 Kontext-Details"):
        lineage = result.lineage

        st.markdown("**Wie wurde dieser Kontext aufgebaut:**")
        st.caption("Die folgenden Datenquellen wurden für die Analyse verwendet:")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Modell",
                lineage.get("model", "unknown").split(":")[-1][:20],  # Shorten model name
            )

        with col2:
            st.metric(
                "Kontext-Ebenen",
                len(lineage.get("agents_used", [])),
            )

        with col3:
            st.metric(
                "Skills",
                len(lineage.get("skills_used", [])),
            )

        st.markdown("**Verwendete Datenquellen:**")
        for agent in lineage.get("agents_used", []):
            st.caption(f"✓ {agent}")

        if lineage.get("skills_used"):
            st.markdown("**Skills:**")
            for skill in lineage.get("skills_used", []):
                st.caption(f"→ {skill}")

        # Timestamp
        timestamp = lineage.get("timestamp", "unknown")
        st.caption(f"**Zeitstempel:** {timestamp}")

    # --- Optionen ---

    col_clear, col_history = st.columns([1, 1])

    with col_clear:
        if st.button("🔄 Neue Analyse", key="compass_clear_btn"):
            del st.session_state["_compass_result"]
            del st.session_state["compass_query_input"]
            st.rerun()

    with col_history:
        # Show recent runs
        agent_runs_repo = get_agent_runs_repo()
        recent_runs = agent_runs_repo.get_recent_runs(limit=5)
        if recent_runs:
            st.caption(f"**Letzte {len(recent_runs)} Analysen:**")
            for run in recent_runs:
                if run["agent_name"] == "investment_kompass":
                    date_str = run["created_at"][:10]
                    st.caption(f"- {date_str}")

st.divider()

# Footer
st.caption("💡 **Tipp:** Der Investment Kompass nutzt die gesamte Portfolio-Historie und bezieht bereits durchgeführte Analysen ein (Watchlist Checker, Story Analysis, Verdicts).")
