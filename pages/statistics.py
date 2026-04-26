"""
Statistics — LLM token usage and costs per agent/skill/model.
"""

import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import datetime

from core.cost_alert import check_alerts, get_period_costs
from core.i18n import t
from core.storage.usage import compute_cost
from state import get_app_config_repo, get_positions_repo, get_scheduled_jobs_repo, get_usage_repo

st.set_page_config(page_title="Statistics", page_icon="📊", layout="wide")
st.title(f"📊 {t('statistics.title')}")
st.caption(t("statistics.subtitle"))

repo = get_usage_repo()
config_repo = get_app_config_repo()
positions_repo = get_positions_repo()
model_prices = config_repo.get_model_prices()

# ------------------------------------------------------------------
# Cost alerts
# ------------------------------------------------------------------
_limits = config_repo.get_cost_alert()
if _limits.get("daily", 0) > 0 or _limits.get("monthly", 0) > 0:
    _period_costs = get_period_costs(repo, model_prices)
    for _alert in check_alerts(_period_costs, _limits):
        if _alert["period"] == "daily":
            st.error(
                t("statistics.alert_daily_exceeded").format(cost=_alert["cost"], limit=_alert["limit"]),
                icon=":material/warning:",
            )
        else:
            st.error(
                t("statistics.alert_monthly_exceeded").format(cost=_alert["cost"], limit=_alert["limit"]),
                icon=":material/warning:",
            )

# ------------------------------------------------------------------
# Source filter (applies to both tabs)
# ------------------------------------------------------------------

_SOURCE_OPTIONS = {"all": "Alle", "manual": "Manuell", "scheduled": "Geplant (Auto)"}
_sel_source = st.radio(
    "Quelle",
    options=list(_SOURCE_OPTIONS.keys()),
    format_func=lambda k: _SOURCE_OPTIONS[k],
    key="_stats_source",
    horizontal=True,
    label_visibility="collapsed",
)

# ------------------------------------------------------------------
# Tab structure
# ------------------------------------------------------------------

tab_summary, tab_recent = st.tabs(["Übersicht", "Letzte Calls"])

# ------------------------------------------------------------------
# Tab 1: Today vs. all-time totals
# ------------------------------------------------------------------

with tab_summary:
    today_rows_raw = repo.total_today()
    alltime_rows_raw = repo.total_all_time()

    def _filter_source(rows, source):
        if source == "all":
            return rows
        return [r for r in rows if r.get("source") == source]

    today_rows = _filter_source(today_rows_raw, _sel_source)
    alltime_rows = _filter_source(alltime_rows_raw, _sel_source)

    col_today, col_alltime = st.columns(2)

    with col_today:
        st.subheader(t("statistics.today"))
        if today_rows:
            df_today = pd.DataFrame(today_rows)
            df_today["total"] = df_today["input_tokens"] + df_today["output_tokens"]
            df_today["cost"] = df_today.apply(
                lambda r: compute_cost(r["input_tokens"], r["output_tokens"], r["model"], model_prices,
                                      r.get("cache_read_tokens"), r.get("cache_write_tokens")),
                axis=1,
            ).round(4)
            # Cache savings % = (cache_read_tokens × 0.9 × input_price) / total_cost × 100
            def _cache_savings_pct(r):
                if r.get("cache_read_tokens", 0) == 0:
                    return 0.0
                cache_read = r.get("cache_read_tokens", 0)
                model = r.get("model", "")
                price = model_prices.get(model, {})
                input_price = price.get("input", 0.0)
                total_cost = r["cost"] * 1_000_000
                savings = cache_read * input_price * 0.9
                return (savings / total_cost * 100) if total_cost > 0 else 0.0
            df_today["cache_savings_pct"] = df_today.apply(_cache_savings_pct, axis=1).round(1)
            df_today = df_today.rename(columns={
                "agent":         t("statistics.col_agent"),
                "skill":         t("statistics.col_skill"),
                "model":         t("statistics.col_model"),
                "source":        "Quelle",
                "input_tokens":  t("statistics.col_input"),
                "output_tokens": t("statistics.col_output"),
                "total":         t("statistics.col_total"),
                "cost":          t("statistics.col_cost"),
                "cache_savings_pct": "Cache Savings %",
            })
            st.dataframe(df_today, use_container_width=True, hide_index=True)
            total_today = sum(r["input_tokens"] + r["output_tokens"] for r in today_rows)
            cost_today = sum(
                compute_cost(r["input_tokens"], r["output_tokens"], r["model"], model_prices)
                for r in today_rows
            )
            m1, m2 = st.columns(2)
            m1.metric(t("statistics.total_tokens"), f"{total_today:,}")
            m2.metric(t("statistics.total_cost"), f"${cost_today:.4f}")
        else:
            st.info(t("statistics.no_data_today"))

    with col_alltime:
        st.subheader(t("statistics.all_time"))
        if alltime_rows:
            df_all = pd.DataFrame(alltime_rows)
            df_all["total"] = df_all["input_tokens"] + df_all["output_tokens"]
            df_all["avg_per_call"] = (df_all["total"] / df_all["calls"]).round(0).astype(int)
            df_all["cost"] = df_all.apply(
                lambda r: compute_cost(r["input_tokens"], r["output_tokens"], r["model"], model_prices),
                axis=1,
            ).round(4)
            df_all["avg_cost"] = (df_all["cost"] / df_all["calls"]).round(6)
            df_all["avg_duration_s"] = pd.to_numeric(df_all["avg_duration_ms"], errors="coerce").div(1000).round(1)
            df_all = df_all.drop(columns=["avg_duration_ms"], errors="ignore")
            df_all = df_all.rename(columns={
                "agent":          t("statistics.col_agent"),
                "skill":          t("statistics.col_skill"),
                "model":          t("statistics.col_model"),
                "source":         "Quelle",
                "input_tokens":   t("statistics.col_input"),
                "output_tokens":  t("statistics.col_output"),
                "calls":          t("statistics.col_calls"),
                "total":          t("statistics.col_total"),
                "avg_per_call":   t("statistics.col_avg"),
                "cost":           t("statistics.col_cost"),
                "avg_cost":       t("statistics.col_avg_cost"),
                "avg_duration_s": "Ø Dauer (s)",
            })
            st.dataframe(df_all, use_container_width=True, hide_index=True)
            total_all = sum(r["input_tokens"] + r["output_tokens"] for r in alltime_rows)
            total_calls = sum(r["calls"] for r in alltime_rows)
            cost_all = sum(
                compute_cost(r["input_tokens"], r["output_tokens"], r["model"], model_prices)
                for r in alltime_rows
            )
            m1, m2, m3 = st.columns(3)
            m1.metric(t("statistics.total_tokens"), f"{total_all:,}")
            m2.metric(t("statistics.total_calls"), f"{total_calls:,}")
            m3.metric(t("statistics.total_cost"), f"${cost_all:.4f}")
        else:
            st.info(t("statistics.no_data"))

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    st.divider()
    st.subheader(t("statistics.reset_header"))

    if alltime_rows:
        reset_cols = st.columns([3, 1])
        with reset_cols[1]:
            if st.button(t("statistics.reset_all_button"), type="secondary", use_container_width=True):
                repo.reset()
                st.success(t("statistics.reset_all_confirm"))
                st.rerun()

        # Per-row reset
        with reset_cols[0]:
            st.caption("Reset per Agent/Skill/Modell:")
        for row in alltime_rows_raw:  # always show all rows in reset section
            label = f"{row['agent']} / {row['skill'] or '—'} / {row['model']} / {row.get('source','manual')}"
            rc1, rc2 = st.columns([5, 1])
            rc1.markdown(f"`{label}`")
            if rc2.button(
                t("statistics.reset_row_button"),
                key=f"_reset_{row['agent']}_{row['skill']}_{row['model']}_{row.get('source','')}",
                use_container_width=True,
            ):
                repo.reset(agent=row["agent"], model=row["model"], skill=row["skill"])
                st.success(t("statistics.reset_row_confirm"))
                st.rerun()

    st.caption(t("statistics.prices_note"))

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

    # ------------------------------------------------------------------
    # Monthly cost estimate
    # ------------------------------------------------------------------

    st.divider()
    st.subheader(t("statistics.monthly_header"))
    st.caption(t("statistics.monthly_caption"))

    jobs_repo = get_scheduled_jobs_repo()
    all_jobs = jobs_repo.get_all()
    active_jobs = [j for j in all_jobs if j.enabled]

    if not active_jobs:
        st.info(t("statistics.monthly_no_jobs"))
    else:
        monthly_rows = repo.monthly_estimate(active_jobs, model_prices, positions_repo)
        if monthly_rows:
            df_monthly = pd.DataFrame(monthly_rows)
            df_monthly = df_monthly.rename(columns={
                "agent":             t("statistics.col_agent"),
                "skill_name":        t("statistics.col_skill"),
                "model":             t("statistics.col_model"),
                "calls_per_month":   t("statistics.col_monthly_calls"),
                "avg_cost_eur":      t("statistics.col_monthly_avg"),
                "monthly_cost_eur":  t("statistics.col_monthly_total"),
            })
            st.dataframe(df_monthly, use_container_width=True, hide_index=True)
            total_monthly = sum(r["monthly_cost_eur"] for r in monthly_rows)
            st.metric(t("statistics.monthly_total"), f"${total_monthly:.4f}")
        else:
            st.info(t("statistics.monthly_no_jobs"))

# ------------------------------------------------------------------
# Tab 2: Recent calls
# ------------------------------------------------------------------

with tab_recent:
    st.caption("Letzte 50 LLM-Aufrufe (chronologisch, neueste zuerst)")

    recent_calls = repo.get_recent_calls(limit=50)

    if recent_calls:
        df_recent = pd.DataFrame(recent_calls)
        df_recent["created_at"] = pd.to_datetime(df_recent["created_at"]).dt.strftime("%d.%m %H:%M:%S")

        def _duration_color(duration_ms):
            if duration_ms is None:
                return "—"
            if duration_ms < 1000:
                return f"🟢 {duration_ms:.0f}"
            elif duration_ms < 3000:
                return f"🟡 {duration_ms:.0f}"
            else:
                return f"🔴 {duration_ms:.0f}"

        df_recent["duration_ms"] = df_recent["duration_ms"].apply(_duration_color)

        df_recent = df_recent.rename(columns={
            "created_at":      "Zeit",
            "agent":           t("statistics.col_agent"),
            "skill":           t("statistics.col_skill"),
            "model":           t("statistics.col_model"),
            "source":          "Quelle",
            "input_tokens":    t("statistics.col_input"),
            "output_tokens":   t("statistics.col_output"),
            "duration_ms":     "Dauer (ms)",
        })

        st.dataframe(df_recent, use_container_width=True, hide_index=True)
    else:
        st.info("Noch keine Aufrufe aufgezeichnet.")
