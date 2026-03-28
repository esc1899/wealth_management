"""
Agentmonitor — zeigt LLM-Generierungen aus Langfuse.
"""

import pandas as pd
import streamlit as st

from config import config
from monitoring.agentmonitor_helpers import build_generation_rows, highlight_status
from state import get_langfuse_client

st.set_page_config(page_title="Agentmonitor", page_icon="🤖", layout="wide")
st.title("🤖 Agentmonitor")

col_title, col_refresh = st.columns([5, 1])
with col_refresh:
    if st.button("🔄 Aktualisieren"):
        st.rerun()

client = get_langfuse_client()

# ------------------------------------------------------------------
# Generierungen laden
# ------------------------------------------------------------------
try:
    result = client.api.observations.get_many(type="GENERATION", limit=50)
    generations = result.data
except Exception as e:
    st.error(f"Langfuse nicht erreichbar: {e}")
    st.info(f"Langfuse UI: [{config.LANGFUSE_HOST}]({config.LANGFUSE_HOST})")
    st.stop()

if not generations:
    st.info("Noch keine Generierungen aufgezeichnet. Starte den Portfolio-Chat um LLM-Calls zu erzeugen.")
    st.info(f"Langfuse UI: {config.LANGFUSE_HOST}")
    st.stop()

# ------------------------------------------------------------------
# Daten aufbereiten
# ------------------------------------------------------------------
rows = build_generation_rows(generations)
df = pd.DataFrame(rows)

# ------------------------------------------------------------------
# KPIs
# ------------------------------------------------------------------
total = len(df)
errors = len(df[df["Status"] == "ERROR"])
avg_dur = df["Dauer (ms)"].dropna().mean()
total_out_tokens = df["Out-Tokens"].dropna().sum()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Generierungen", total)
k2.metric("Fehler", errors, delta=None if errors == 0 else f"{errors}", delta_color="inverse")
k3.metric("Ø Dauer", f"{avg_dur:.0f} ms" if avg_dur == avg_dur else "—")
k4.metric("Output-Tokens gesamt", int(total_out_tokens) if total_out_tokens == total_out_tokens else "—")

st.divider()

# ------------------------------------------------------------------
# Tabelle
# ------------------------------------------------------------------
st.subheader("Letzte 50 Generierungen")

display_cols = ["Zeit", "Name", "Modell", "Dauer (ms)", "Status", "In-Tokens", "Out-Tokens"]
display_df = df[display_cols].copy()

styled = display_df.style.applymap(highlight_status, subset=["Status"])
st.dataframe(styled, use_container_width=True, hide_index=True)

st.divider()

# ------------------------------------------------------------------
# Detail-Ansicht
# ------------------------------------------------------------------
st.subheader("Detail")
idx = st.number_input("Zeile (0-basiert)", min_value=0, max_value=max(0, len(df) - 1), value=0, step=1)

if len(df) > 0:
    row = df.iloc[idx]
    col_in, col_out = st.columns(2)

    with col_in:
        st.markdown("**Input**")
        raw_in = row["_input"]
        if isinstance(raw_in, list):
            for msg in raw_in:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                st.markdown(f"**{role}:** {content}")
        elif raw_in:
            st.text(str(raw_in))
        else:
            st.text("—")

    with col_out:
        st.markdown("**Output**")
        raw_out = row["_output"]
        if isinstance(raw_out, str) and raw_out:
            st.text(raw_out)
        elif raw_out:
            st.text(str(raw_out))
        else:
            st.text("—")

st.divider()
st.markdown(f"[Vollständige Langfuse UI öffnen ↗]({config.LANGFUSE_HOST})")
