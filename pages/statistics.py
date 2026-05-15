"""
Statistics — LLM costs and usage per agent/month.
"""

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from core.i18n import t
from core.storage.usage import compute_cost
from state import get_app_config_repo, get_usage_repo

st.set_page_config(page_title="Statistics", page_icon="📊", layout="wide")
st.title(f"📊 {t('statistics.title')}")
st.caption(t("statistics.subtitle"))

repo = get_usage_repo()
config_repo = get_app_config_repo()
model_prices = config_repo.get_model_prices()

# ------------------------------------------------------------------
# Source filter
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
# Load data
# ------------------------------------------------------------------

today_rows_raw = repo.total_today()
alltime_rows_raw = repo.total_all_time()
monthly_rows_raw = repo.monthly_totals_by_model()
daily_rows_raw = repo.daily_totals_by_model(days=30)


def _filter_source(rows: list[dict]) -> list[dict]:
    if _sel_source == "all":
        return rows
    return [r for r in rows if r.get("source") == _sel_source]


today_rows = _filter_source(today_rows_raw)
alltime_rows = _filter_source(alltime_rows_raw)
monthly_rows = _filter_source(monthly_rows_raw)
daily_rows = _filter_source(daily_rows_raw)

# ------------------------------------------------------------------
# Cost helpers
# ------------------------------------------------------------------


def _row_cost(r: dict) -> float:
    return compute_cost(
        r["input_tokens"],
        r["output_tokens"],
        r["model"],
        model_prices,
        r.get("cache_read_tokens"),
        r.get("cache_write_tokens"),
        r.get("web_search_requests"),
    )



# ------------------------------------------------------------------
# KPI: this month / last month
# ------------------------------------------------------------------

today = date.today()
current_month = today.strftime("%Y-%m")
last_month = f"{today.year - 1}-12" if today.month == 1 else f"{today.year}-{today.month - 1:02d}"

this_month_rows = [r for r in monthly_rows if r["month"] == current_month]
last_month_rows = [r for r in monthly_rows if r["month"] == last_month]

today_cost = sum(_row_cost(r) for r in today_rows)
today_calls = sum(r.get("calls", 0) for r in today_rows)
this_month_cost = sum(_row_cost(r) for r in this_month_rows)
this_month_calls = sum(r.get("calls", 0) for r in this_month_rows)
last_month_cost = sum(_row_cost(r) for r in last_month_rows)
last_month_calls = sum(r.get("calls", 0) for r in last_month_rows)

# ------------------------------------------------------------------
# Header KPIs
# ------------------------------------------------------------------

m1, m2, m3 = st.columns(3)
m1.metric(t("statistics.today"), f"${today_cost:.4f}", delta=f"{today_calls} Calls", delta_color="off")
m2.metric(t("statistics.this_month"), f"${this_month_cost:.4f}", delta=f"{this_month_calls} Calls", delta_color="off")
m3.metric(t("statistics.last_month"), f"${last_month_cost:.4f}", delta=f"{last_month_calls} Calls", delta_color="off")

st.divider()

# ------------------------------------------------------------------
# Tabs
# ------------------------------------------------------------------

tab_trend, tab_agents, tab_calls = st.tabs([
    t("statistics.tab_trend"),
    t("statistics.tab_agents"),
    t("statistics.tab_calls"),
])

# ── Tab: Verlauf ───────────────────────────────────────────────────────────────

with tab_trend:
    st.subheader(t("statistics.monthly_chart"))

    if monthly_rows:
        # Aggregate cost by month
        monthly_agg: dict[str, dict] = {}
        for r in monthly_rows:
            m = r["month"]
            if m not in monthly_agg:
                monthly_agg[m] = {"month": m, "cost": 0.0, "calls": 0}
            monthly_agg[m]["cost"] += _row_cost(r)
            monthly_agg[m]["calls"] += r.get("calls", 0)

        sorted_months = sorted(monthly_agg.keys())[-12:]
        df_monthly = pd.DataFrame([monthly_agg[m] for m in sorted_months])

        fig = px.bar(
            df_monthly,
            x="month",
            y="cost",
            labels={"month": "", "cost": "Kosten ($)"},
            color_discrete_sequence=["#4C9BE8"],
            text=df_monthly["cost"].apply(lambda v: f"${v:.3f}"),
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(yaxis_title="Kosten ($)", showlegend=False, uniformtext_minsize=8)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(t("statistics.no_data"))

    st.subheader(t("statistics.daily_costs"))

    if daily_rows:
        # Aggregate cost by day
        daily_agg: dict[str, float] = {}
        for r in daily_rows:
            d = r["day"]
            daily_agg[d] = daily_agg.get(d, 0.0) + _row_cost(r)

        df_daily = pd.DataFrame(
            [{"day": d, "cost": c} for d, c in sorted(daily_agg.items())],
        )
        fig2 = px.bar(
            df_daily,
            x="day",
            y="cost",
            labels={"day": "", "cost": "Kosten ($)"},
            color_discrete_sequence=["#4C9BE8"],
        )
        fig2.update_layout(yaxis_title="Kosten ($)", showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info(t("statistics.no_data"))

    with st.expander(t("statistics.today_detail")):
        if today_rows:
            df_today = pd.DataFrame(today_rows)
            df_today["cost"] = df_today.apply(_row_cost, axis=1).round(4)
            display_cols = [c for c in ["agent", "skill", "model", "source", "input_tokens", "output_tokens", "calls", "cost"] if c in df_today.columns]
            df_today = df_today[display_cols].rename(columns={
                "agent": t("statistics.col_agent"),
                "skill": t("statistics.col_skill"),
                "model": t("statistics.col_model"),
                "source": "Quelle",
                "input_tokens": t("statistics.col_input"),
                "output_tokens": t("statistics.col_output"),
                "calls": t("statistics.col_calls"),
                "cost": t("statistics.col_cost"),
            })
            st.dataframe(df_today, use_container_width=True, hide_index=True)
        else:
            st.info(t("statistics.no_data_today"))

    st.caption(t("statistics.prices_note"))

# ── Tab: Nach Agent ────────────────────────────────────────────────────────────

with tab_agents:
    if alltime_rows:
        # All-time per agent
        agent_alltime: dict[str, dict] = {}
        for r in alltime_rows:
            a = r["agent"]
            if a not in agent_alltime:
                agent_alltime[a] = {"agent": a, "cost_total": 0.0, "calls_total": 0}
            agent_alltime[a]["cost_total"] += _row_cost(r)
            agent_alltime[a]["calls_total"] += r.get("calls", 0)

        # This month per agent
        agent_month: dict[str, dict] = {}
        for r in this_month_rows:
            a = r["agent"]
            if a not in agent_month:
                agent_month[a] = {"cost_month": 0.0, "calls_month": 0}
            agent_month[a]["cost_month"] += _row_cost(r)
            agent_month[a]["calls_month"] += r.get("calls", 0)

        rows_agent = []
        for agent, data in sorted(agent_alltime.items()):
            month_data = agent_month.get(agent, {})
            cost_total = data["cost_total"]
            calls_total = data["calls_total"]
            rows_agent.append({
                t("statistics.col_agent"): agent,
                "Calls (Monat)": month_data.get("calls_month", 0),
                t("statistics.col_cost_month"): round(month_data.get("cost_month", 0.0), 4),
                "Calls (Gesamt)": calls_total,
                t("statistics.col_cost_total"): round(cost_total, 4),
                "Ø Kosten/Call": round(cost_total / calls_total, 6) if calls_total else 0.0,
            })

        df_agents = pd.DataFrame(rows_agent)
        st.dataframe(df_agents, use_container_width=True, hide_index=True)
    else:
        st.info(t("statistics.no_data"))

# ── Tab: Letzte Calls ──────────────────────────────────────────────────────────

with tab_calls:
    st.caption("Letzte 50 LLM-Aufrufe (neueste zuerst)")
    st.caption(
        "**Eff. Input** = reguläre Input-Tokens + Cache Write + Cache Read. "
        "**Cache Write** = neue Cache-Einträge (1.25×). "
        "**Cache Read** = aus Cache gelesen (0.1×, fast kostenlos)."
    )

    recent_calls = repo.get_recent_calls(limit=50)

    if recent_calls:
        df_recent = pd.DataFrame(recent_calls)
        df_recent["created_at"] = pd.to_datetime(df_recent["created_at"]).dt.strftime("%d.%m %H:%M:%S")

        def _duration_label(duration_ms):
            if duration_ms is None:
                return "—"
            if duration_ms < 1000:
                return f"🟢 {duration_ms:.0f}"
            elif duration_ms < 3000:
                return f"🟡 {duration_ms:.0f}"
            return f"🔴 {duration_ms:.0f}"

        df_recent["duration_ms"] = df_recent["duration_ms"].apply(_duration_label)
        df_recent["eff_input"] = (
            df_recent["input_tokens"].fillna(0).astype(int)
            + df_recent.get("cache_write_tokens", pd.Series(0, index=df_recent.index)).fillna(0).astype(int)
            + df_recent.get("cache_read_tokens", pd.Series(0, index=df_recent.index)).fillna(0).astype(int)
        )
        df_recent = df_recent.rename(columns={
            "created_at":         "Zeit",
            "agent":              t("statistics.col_agent"),
            "skill":              t("statistics.col_skill"),
            "model":              t("statistics.col_model"),
            "source":             "Quelle",
            "input_tokens":       t("statistics.col_input"),
            "output_tokens":      t("statistics.col_output"),
            "cache_write_tokens": "Cache Write (1.25×)",
            "cache_read_tokens":  "Cache Read (0.1×)",
            "eff_input":          "Eff. Input",
            "duration_ms":        "Dauer (ms)",
        })
        st.dataframe(df_recent, use_container_width=True, hide_index=True)
    else:
        st.info("Noch keine Aufrufe aufgezeichnet.")
