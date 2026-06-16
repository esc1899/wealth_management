"""Verdict Hindsight — did the price-directed verdicts age well? (FEAT-59)

Read-only feedback loop: realized forward price change after each Consensus-Gap,
Devil's-Advocate and Fundamental-Analyzer (valuation) verdict, grouped by verdict label.
Framed as a journal/directional signal, never a hit rate (see core.verdict_hindsight).
"""

import pandas as pd
import streamlit as st

from core.i18n import t
from core.ui.verdicts import VERDICT_CONFIGS, verdict_badge
from core.verdict_hindsight import DIRECTIONAL_AGENTS, HORIZONS, compute_hindsight
from state import (
    get_analyses_repo,
    get_app_config_repo,
    get_market_agent,
    get_market_repo,
    get_wealth_snapshot_repo,
)

_BENCHMARK_SYMBOL_KEY = "hindsight_benchmark_symbol"
_DEFAULT_BENCHMARK_SYMBOL = "EUNL.DE"  # iShares Core MSCI World (EUR)

st.set_page_config(page_title="Verdict Hindsight", page_icon="🔭", layout="wide")
st.title(f"🔭 {t('verdict_hindsight.title')}")
st.caption(t("verdict_hindsight.subtitle"))

analyses_repo = get_analyses_repo()
market_repo = get_market_repo()

agents = list(DIRECTIONAL_AGENTS)
verdict_rows = analyses_repo.get_verdicts_with_ticker(agents)
total_emitted = analyses_repo.count_directional_verdicts(agents)
report = compute_hindsight(
    verdict_rows,
    price_fn=market_repo.get_price_near_date,
    total_emitted=total_emitted,
)

# --- Framing: this is a journal, not a statistics claim --------------------------
st.info(t("verdict_hindsight.framing"))

with st.expander(t("verdict_hindsight.methodology_header")):
    st.markdown(t("verdict_hindsight.methodology_body"))

# Headline metrics describe the whole corpus (scope-independent).
m1, m2, m3, m4 = st.columns(4)
m1.metric(t("verdict_hindsight.metric_total"), report.total_emitted)
m2.metric(t("verdict_hindsight.metric_evaluated"), report.evaluated_verdicts)
m3.metric(t("verdict_hindsight.metric_survivorship"), report.excluded_survivorship)
m4.metric(t("verdict_hindsight.metric_excluded"), report.excluded_no_price)

if report.excluded_survivorship > report.evaluated_verdicts:
    st.warning(t("verdict_hindsight.survivorship_warning"))

if report.is_empty:
    st.warning(t("verdict_hindsight.empty"))
    st.stop()

# --- Filters: scope (Portfolio/Watchlist) + benchmark (raw / excess return) -------
left, right = st.columns(2)
with left:
    SCOPES = {
        t("verdict_hindsight.scope_all"): None,
        t("verdict_hindsight.scope_portfolio"): "portfolio",
        t("verdict_hindsight.scope_watchlist"): "watchlist",
    }
    scope = SCOPES[st.radio(t("verdict_hindsight.scope_label"), list(SCOPES), horizontal=True)]
with right:
    BENCHMARKS = {
        t("verdict_hindsight.bench_raw"): "raw",
        t("verdict_hindsight.bench_portfolio"): "portfolio",
        t("verdict_hindsight.bench_index"): "index",
    }
    bench_mode = BENCHMARKS[st.radio(t("verdict_hindsight.bench_label"), list(BENCHMARKS), horizontal=True)]

# Build the benchmark level function (date → level), memoised. None = raw returns.
benchmark_fn = None
if bench_mode == "portfolio":
    wealth_repo = get_wealth_snapshot_repo()
    _cache: dict = {}
    def benchmark_fn(d, _c=_cache, _r=wealth_repo):  # noqa: E731
        if d not in _c:
            _c[d] = _r.value_near_date(d)
        return _c[d]
elif bench_mode == "index":
    cfg_repo = get_app_config_repo()
    symbol = (cfg_repo.get(_BENCHMARK_SYMBOL_KEY) or _DEFAULT_BENCHMARK_SYMBOL).upper()
    bcol1, bcol2 = st.columns([2, 1])
    new_symbol = bcol1.text_input(t("verdict_hindsight.bench_symbol_label"), value=symbol).strip().upper()
    if new_symbol and new_symbol != symbol:
        cfg_repo.set(_BENCHMARK_SYMBOL_KEY, new_symbol)
        symbol = new_symbol
    has_history = bool(market_repo.get_historical(symbol, days=800))
    if not has_history:
        st.warning(t("verdict_hindsight.bench_no_history").format(symbol=symbol))
        if bcol2.button(t("verdict_hindsight.bench_load"), use_container_width=True):
            with st.spinner(t("verdict_hindsight.bench_loading").format(symbol=symbol)):
                n = get_market_agent().fetch_historical_for_symbol(symbol)
            st.success(t("verdict_hindsight.bench_loaded").format(n=n, symbol=symbol))
            st.rerun()
        st.stop()
    _icache: dict = {}
    def benchmark_fn(d, _c=_icache, _r=market_repo, _s=symbol):  # noqa: E731
        if d not in _c:
            _c[d] = _r.get_price_near_date(_s, d)
        return _c[d]

# Scope + benchmark only affect the per-agent tables below (headline metrics stay raw).
scoped_rows = verdict_rows if scope is None else [r for r in verdict_rows if r["scope"] == scope]
if scope is None and benchmark_fn is None:
    scoped_report = report
else:
    scoped_report = compute_hindsight(
        scoped_rows, price_fn=market_repo.get_price_near_date, benchmark_fn=benchmark_fn
    )
st.caption(t("verdict_hindsight.scope_hint"))


def _fmt_pct(value) -> str:
    if value is None:
        return "—"
    return f"{value:+.1f} %"


def _color_pct(value: str) -> str:
    if not isinstance(value, str) or value == "—":
        return "color: grey"
    if value.startswith("+") and not value.startswith("+0.0"):
        return "color: #1a7f37"  # green
    if value.startswith("-"):
        return "color: #cf222e"  # red
    return "color: grey"


# In excess mode the headline columns show out-/underperformance vs the benchmark.
_median_key = "col_excess" if benchmark_fn is not None else "col_median"
median_cols = [t(f"verdict_hindsight.{_median_key}").format(h=h) for h, _ in HORIZONS]

if not scoped_report.by_agent:
    st.info(t("verdict_hindsight.scope_empty"))
    st.stop()

for agent, rows in scoped_report.by_agent.items():
    config = VERDICT_CONFIGS.get(agent, {})
    st.subheader(t(f"verdict_hindsight.agent_{agent}"))

    table = []
    for row in rows:
        record = {
            t("verdict_hindsight.col_verdict"): verdict_badge(row.verdict, config),
            t("verdict_hindsight.col_count"): row.total_verdicts,
            t("verdict_hindsight.col_positions"): row.distinct_positions,
        }
        for horizon_key, _days in HORIZONS:
            stat = row.horizons[horizon_key]
            record[t(f"verdict_hindsight.{_median_key}").format(h=horizon_key)] = _fmt_pct(stat.median_pct)
            record[t("verdict_hindsight.col_n").format(h=horizon_key)] = stat.n
        table.append(record)

    df = pd.DataFrame(table)
    styled = df.style.map(_color_pct, subset=median_cols)
    st.dataframe(styled, hide_index=True, use_container_width=True)

    # Mean / best / worst live in a detail expander to keep the main table calm.
    with st.expander(t("verdict_hindsight.details")):
        detail = []
        for row in rows:
            for horizon_key, _days in HORIZONS:
                stat = row.horizons[horizon_key]
                if stat.n == 0:
                    continue
                detail.append({
                    t("verdict_hindsight.col_verdict"): verdict_badge(row.verdict, config),
                    t("verdict_hindsight.col_horizon"): horizon_key,
                    t("verdict_hindsight.col_n_plain"): stat.n,
                    t("verdict_hindsight.col_median_plain"): _fmt_pct(stat.median_pct),
                    t("verdict_hindsight.col_mean_plain"): _fmt_pct(stat.mean_pct),
                    t("verdict_hindsight.col_best"): _fmt_pct(stat.best_pct),
                    t("verdict_hindsight.col_worst"): _fmt_pct(stat.worst_pct),
                })
        if detail:
            st.dataframe(pd.DataFrame(detail), hide_index=True, use_container_width=True)
        else:
            st.caption(t("verdict_hindsight.details_empty"))

st.caption(t("verdict_hindsight.read_hint"))
