"""
Statistics — LLM token usage per agent and over time.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from core.i18n import t
from state import get_usage_repo

st.set_page_config(page_title="Statistics", page_icon="📊", layout="wide")
st.title(f"📊 {t('statistics.title')}")
st.caption(t("statistics.subtitle"))

repo = get_usage_repo()

# ------------------------------------------------------------------
# Today vs. all-time totals
# ------------------------------------------------------------------

today_rows = repo.total_today()
alltime_rows = repo.total_all_time()

col_today, col_alltime = st.columns(2)

with col_today:
    st.subheader(t("statistics.today"))
    if today_rows:
        df_today = pd.DataFrame(today_rows)
        df_today["total"] = df_today["input_tokens"] + df_today["output_tokens"]
        df_today = df_today.rename(columns={
            "agent":         t("statistics.col_agent"),
            "model":         t("statistics.col_model"),
            "input_tokens":  t("statistics.col_input"),
            "output_tokens": t("statistics.col_output"),
            "total":         t("statistics.col_total"),
        })
        st.dataframe(df_today, use_container_width=True, hide_index=True)
        total_today = sum(r["input_tokens"] + r["output_tokens"] for r in today_rows)
        st.metric(t("statistics.total_tokens"), f"{total_today:,}")
    else:
        st.info(t("statistics.no_data_today"))

with col_alltime:
    st.subheader(t("statistics.all_time"))
    if alltime_rows:
        df_all = pd.DataFrame(alltime_rows)
        df_all["total"] = df_all["input_tokens"] + df_all["output_tokens"]
        df_all["avg_per_call"] = (df_all["total"] / df_all["calls"]).round(0).astype(int)
        df_all = df_all.rename(columns={
            "agent":         t("statistics.col_agent"),
            "model":         t("statistics.col_model"),
            "input_tokens":  t("statistics.col_input"),
            "output_tokens": t("statistics.col_output"),
            "calls":         t("statistics.col_calls"),
            "total":         t("statistics.col_total"),
            "avg_per_call":  t("statistics.col_avg"),
        })
        st.dataframe(df_all, use_container_width=True, hide_index=True)
        total_all = sum(r["input_tokens"] + r["output_tokens"] for r in alltime_rows)
        total_calls = sum(r["calls"] for r in alltime_rows)
        m1, m2, m3 = st.columns(3)
        m1.metric(t("statistics.total_tokens"), f"{total_all:,}")
        m2.metric(t("statistics.total_calls"), f"{total_calls:,}")
        m3.metric(t("statistics.avg_per_call"), f"{total_all // total_calls:,}" if total_calls else "—")
    else:
        st.info(t("statistics.no_data"))

# ------------------------------------------------------------------
# Daily trend chart
# ------------------------------------------------------------------

st.divider()
st.subheader(t("statistics.daily_chart"))

daily_rows = repo.daily_totals(limit=30)
if daily_rows:
    df_daily = pd.DataFrame(daily_rows)
    df_daily["total"] = df_daily["input_tokens"] + df_daily["output_tokens"]
    df_daily = df_daily.sort_values("day")
    fig = px.bar(
        df_daily,
        x="day",
        y=["input_tokens", "output_tokens"],
        labels={
            "day":           t("statistics.col_day"),
            "value":         t("statistics.col_tokens"),
            "variable":      t("statistics.col_type"),
            "input_tokens":  t("statistics.col_input"),
            "output_tokens": t("statistics.col_output"),
        },
        color_discrete_map={
            "input_tokens":  "#4C9BE8",
            "output_tokens": "#E8834C",
        },
    )
    fig.update_layout(legend_title_text="", xaxis_title="", yaxis_title=t("statistics.col_tokens"))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info(t("statistics.no_data"))

# ------------------------------------------------------------------
# Per-agent breakdown (all time) as pie
# ------------------------------------------------------------------

if alltime_rows:
    st.subheader(t("statistics.by_agent"))
    df_pie = pd.DataFrame(alltime_rows)
    df_pie["total"] = df_pie["input_tokens"] + df_pie["output_tokens"]
    fig2 = px.pie(
        df_pie,
        names="agent",
        values="total",
        hole=0.4,
    )
    fig2.update_traces(textinfo="label+percent")
    st.plotly_chart(fig2, use_container_width=True)
