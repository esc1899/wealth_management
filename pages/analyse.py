"""
Analysis — performance charts, historical prices, allocation.
"""

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from core.currency import symbol
from core.i18n import t, fmt_dt
from core.macro_context import load_or_refresh_macro
from core.monthly_attribution import compute_monthly_attribution
from core.monthly_digest_generator import generate_monthly_digest
from core.yearly_attribution import compute_yearly_attribution
from core.yearly_digest_generator import generate_yearly_digest
from state import (
    get_market_agent, get_market_repo, get_portfolio_service,
    get_app_config_repo, get_analyses_repo, get_monthly_digest_repo,
    get_yearly_digest_repo,
)

st.set_page_config(page_title="Analyse", page_icon="🔍", layout="wide")
st.title(f"🔍 {t('analysis.title')}")

agent = get_market_agent()

# ------------------------------------------------------------------
# Auto-fetch: refresh prices if last fetch is older than 1 hour
# ------------------------------------------------------------------

if "analyse_auto_fetched" not in st.session_state:
    st.session_state.analyse_auto_fetched = False

if not st.session_state.analyse_auto_fetched:
    valuations_check = agent.get_portfolio_valuation()
    prices_fresh = any(
        v.fetched_at is not None
        and (datetime.now(timezone.utc) - v.fetched_at.replace(tzinfo=timezone.utc)).total_seconds() < 3600
        for v in valuations_check
        if v.fetched_at is not None
    )
    if not prices_fresh:
        with st.spinner(t("analysis.auto_fetch_notice")):
            agent.fetch_all_now(fetch_history=True)
    st.session_state.analyse_auto_fetched = True

col_title, col_refresh = st.columns([5, 1])
with col_refresh:
    if st.button(f"🔄 {t('common.refresh')}"):
        with st.spinner(t("analysis.auto_fetch_notice")):
            agent.fetch_all_now(fetch_history=True)
        st.session_state.analyse_auto_fetched = True
        st.rerun()

valuations = agent.get_portfolio_valuation()

_excluded_count = sum(
    1 for v in valuations
    if v.in_portfolio and getattr(v, "analysis_excluded", False)
    and v.current_value_eur and v.current_value_eur > 0
)

# ------------------------------------------------------------------
# FEAT-35: Makro-Kontext Chips
# ------------------------------------------------------------------
_app_config_repo = get_app_config_repo()
_macro = load_or_refresh_macro(_app_config_repo)

with st.container():
    m1, m2, m3, m4 = st.columns(4)
    if _macro:
        m1.metric(
            "VIX",
            f"{_macro.vix:.1f}" if _macro.vix is not None else "—",
            help="CBOE Volatility Index — Maß für Markt-Unsicherheit",
        )
        m2.metric(
            "EUR/USD",
            f"{_macro.eur_usd:.3f}" if _macro.eur_usd is not None else "—",
        )
        m3.metric(
            "Gold (€/oz)",
            f"{_macro.gold_eur:,.0f}" if _macro.gold_eur is not None else "—",
        )
        if _macro.dax_change_pct is not None:
            m4.metric(
                "DAX (heute)",
                f"{_macro.dax_change_pct:+.1f}%",
                delta=_macro.dax_change_pct,
                delta_color="normal",
            )
        else:
            m4.metric("DAX (heute)", "—")
        try:
            _ts = datetime.fromisoformat(_macro.fetched_at)
            st.caption(f"{t('analysis.macro_timestamp')} {fmt_dt(_ts)} UTC")
        except Exception:
            pass
    else:
        m1.metric("VIX", "—")
        m2.metric("EUR/USD", "—")
        m3.metric("Gold (€/oz)", "—")
        m4.metric("DAX (heute)", "—")

if not valuations:
    st.info(t("analysis.portfolio_empty"))
    st.stop()

has_prices = any(v.current_value_eur is not None for v in valuations)

if not has_prices:
    st.warning(t("analysis.no_price_data"))

# ------------------------------------------------------------------
# Today's performance (daily P&L)
# ------------------------------------------------------------------
st.subheader(t("analysis.day_pnl_header"))

col_day_eur = t("analysis.day_pnl_col")
col_day_pct = t("analysis.day_pnl_pct_col")

day_rows = [
    {
        "Symbol": v.symbol,
        col_day_eur: v.day_pnl_eur,
        col_day_pct: v.day_pnl_pct,
    }
    for v in valuations
    if v.day_pnl_eur is not None
]

if day_rows:
    df_day = pd.DataFrame(day_rows).sort_values(col_day_eur)
    total_day = df_day[col_day_eur].sum()
    total_sign = "+" if total_day >= 0 else ""
    _total_prev = sum(
        (v.current_value_eur - v.day_pnl_eur)
        for v in valuations
        if v.day_pnl_eur is not None and v.current_value_eur is not None
    )
    _day_pct_str = f"{total_day / _total_prev * 100:+.2f}% " if _total_prev else ""
    st.caption(
        f"**Gesamt heute: {_day_pct_str}({total_sign}{symbol()}{total_day:,.2f})**"
        .replace(",", "X").replace(".", ",").replace("X", ".")
    )

    fig_day = px.bar(
        df_day, x="Symbol", y=col_day_eur,
        color=col_day_eur,
        color_continuous_scale=["red", "lightgrey", "green"],
        color_continuous_midpoint=0,
        text=[
            f"{row[col_day_pct]:+.2f}% ({'+' if row[col_day_eur] >= 0 else ''}{symbol()}{row[col_day_eur]:,.0f})"
            .replace(",", "X").replace(".", ",").replace("X", ".")
            if row[col_day_pct] is not None else ""
            for _, row in df_day.iterrows()
        ],
    )
    fig_day.update_traces(textposition="outside")
    fig_day.update_layout(coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig_day, use_container_width=True)
else:
    st.info(t("analysis.no_day_pnl"))

st.divider()

# ------------------------------------------------------------------
# FEAT-34: Monatsanalyse — Performance-Attribution
# ------------------------------------------------------------------
_today = date.today()
_month_options = []
for _i in range(12):
    _y = _today.year if _today.month - _i > 0 else _today.year - 1
    _m = (_today.month - _i - 1) % 12 + 1
    _month_options.append((_y, _m))

_MONTH_NAMES_DE = {
    1: "Januar", 2: "Februar", 3: "März", 4: "April",
    5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}
_month_labels = [
    f"{_MONTH_NAMES_DE[m]} {y}{' (laufend)' if (y, m) == (_today.year, _today.month) else ''}"
    for y, m in _month_options
]
_sel_idx = st.selectbox(
    "Monatsanalyse",
    range(len(_month_options)),
    format_func=lambda i: _month_labels[i],
    key="monthly_analysis_month",
    label_visibility="collapsed",
)
_sel_year, _sel_month = _month_options[_sel_idx]
_is_current_month = (_sel_year, _sel_month) == (_today.year, _today.month)
_month_label = f"{_MONTH_NAMES_DE[_sel_month]} {_sel_year}"

st.subheader(f"📅 Monatsanalyse {_month_label}")
if _is_current_month:
    st.caption(f"Monat-bisher (MTD) — Vergleich {_MONTH_NAMES_DE[_sel_month]} 1 bis heute")
if _excluded_count:
    st.caption(f"ℹ️ {_excluded_count} Position{'en' if _excluded_count != 1 else ''} von der Analyse ausgeschlossen — Gesamtvermögen in der Vermögenshistorie kann abweichen.")

_market_repo = get_market_repo()
_attribution = compute_monthly_attribution(valuations, _market_repo, _sel_year, _sel_month)

if _attribution:
    _rows_with_data = [r for r in _attribution if r.delta_pct is not None]

    # Summary metric
    _total_contrib = sum(r.contribution_eur for r in _attribution)
    _total_start = sum(
        (r.start_price_eur * r.quantity)
        for r in _attribution
        if r.start_price_eur and r.quantity
    )
    _total_pct = (_total_contrib / _total_start * 100) if _total_start > 0 else None
    _sign = "+" if _total_contrib >= 0 else ""
    _pct_str = f"{_total_pct:+.1f}%" if _total_pct is not None else "n/a"
    st.caption(
        f"**Portfolio gesamt {_month_label}: {_pct_str} ({_sign}{symbol()}{_total_contrib:,.0f})**"
        .replace(",", "X").replace(".", ",").replace("X", ".")
    )

    if _rows_with_data:
        _df_attr = pd.DataFrame([
            {"Symbol": r.symbol, "Beitrag (€)": r.contribution_eur}
            for r in _rows_with_data
        ]).sort_values("Beitrag (€)")
        _fig_attr = px.bar(
            _df_attr, x="Symbol", y="Beitrag (€)",
            color="Beitrag (€)",
            color_continuous_scale=["red", "lightgrey", "green"],
            color_continuous_midpoint=0,
            text=_df_attr["Beitrag (€)"].apply(lambda v: f"{v:+,.0f}€".replace(",", "X").replace(".", ",").replace("X", ".")),
        )
        _fig_attr.update_traces(textposition="outside")
        _fig_attr.update_layout(coloraxis_showscale=False, margin=dict(t=20))
        st.plotly_chart(_fig_attr, use_container_width=True)

    # Table
    _table_rows = []
    _has_dividends_month = any(r.dividend_contribution_eur > 0 for r in _attribution)
    for r in _attribution:
        row = {
            "Symbol": r.symbol,
            "Klasse": t(f"investment_types.{r.investment_type}") if r.investment_type else r.investment_type,
            "Monatsstart (€)": f"{r.start_price_eur:,.2f}" if r.start_price_eur else "—",
            "Aktuell (€)": f"{r.end_price_eur:,.2f}" if r.end_price_eur else "—",
            "∆ Monat": f"{r.delta_pct:+.1f}%" if r.delta_pct is not None else "—",
            "Gewichtung": f"{r.weight_pct:.1f}%",
            "Beitrag (€)": f"{r.contribution_eur:+,.0f}" if r.contribution_eur != 0 else "0",
        }
        if _has_dividends_month:
            row["Div. (€)*"] = f"+{r.dividend_contribution_eur:,.0f}" if r.dividend_contribution_eur > 0 else "—"
        _table_rows.append(row)
    st.dataframe(pd.DataFrame(_table_rows), use_container_width=True, hide_index=True)
    _month_captions = ["Start = letzter Schlusskurs des Vormonats, Ende = letzter Schlusskurs des Monats (laufender Monat: aktueller Kurs)."]
    if _has_dividends_month:
        _month_captions.append("* Div. = geschätzte Dividende (Jahresdividende ÷ 12, aktuelle Rate — keine tatsächlichen Zahlungen).")
    st.caption(" ".join(_month_captions))
else:
    st.info(f"Keine historischen Preisdaten für {_month_label} verfügbar. Preishistorie muss geladen sein.")

st.divider()

# ------------------------------------------------------------------
# FEAT-36: Monatsdigest
# ------------------------------------------------------------------
_digest_repo = get_monthly_digest_repo()
_analyses_repo = get_analyses_repo()
_digest_key = f"{_sel_year:04d}-{_sel_month:02d}"

with st.expander(f"📋 Monatsdigest {_month_label}", expanded=False):
    _digest = _digest_repo.get(_digest_key)
    if _digest:
        st.markdown(_digest.body_markdown)
        st.caption(f"{t('common.generated_at')} {fmt_dt(_digest.generated_at)} UTC")
        if st.button("🔄 Digest neu generieren", key="regen_digest"):
            _md = generate_monthly_digest(
                valuations, _analyses_repo, _app_config_repo,
                _sel_year, _sel_month, market_repo=_market_repo,
            )
            _digest_repo.save(_digest_key, _md)
            st.rerun()
    else:
        if _is_current_month:
            st.info(
                f"Kein Digest für {_month_label} (laufender Monat). "
                "Der Scheduler generiert den Digest automatisch am Monatsende. "
                "Jetzt generieren zeigt den Stand von heute."
            )
        else:
            st.info(f"Noch kein Digest für {_month_label}.")
        if st.button("✨ Digest jetzt generieren", key="gen_digest"):
            with st.spinner("Generiere Digest..."):
                _md = generate_monthly_digest(
                    valuations, _analyses_repo, _app_config_repo,
                    _sel_year, _sel_month, market_repo=_market_repo,
                )
            _digest_repo.save(_digest_key, _md)
            st.rerun()

st.divider()

# ------------------------------------------------------------------
# FEAT-37: Jahresanalyse — Performance-Attribution
# ------------------------------------------------------------------
_year_options = list(range(_today.year, _today.year - 5, -1))
_year_labels = [
    f"{y}{' (laufend)' if y == _today.year else ''}"
    for y in _year_options
]
_sel_year_idx = st.selectbox(
    "Jahresanalyse",
    range(len(_year_options)),
    format_func=lambda i: _year_labels[i],
    key="yearly_analysis_year",
    label_visibility="collapsed",
)
_sel_year_val = _year_options[_sel_year_idx]
_is_current_year = _sel_year_val == _today.year
_year_label = str(_sel_year_val)

st.subheader(f"📆 Jahresanalyse {_year_label}")
if _is_current_year:
    st.caption(f"Jahr-bisher (YTD) — Vergleich 1. Januar bis heute")
if _excluded_count:
    st.caption(f"ℹ️ {_excluded_count} Position{'en' if _excluded_count != 1 else ''} von der Analyse ausgeschlossen — Gesamtvermögen in der Vermögenshistorie kann abweichen.")

_year_attribution = compute_yearly_attribution(valuations, _market_repo, _sel_year_val)

if _year_attribution:
    _year_rows_with_data = [r for r in _year_attribution if r.delta_pct is not None]

    _year_total_contrib = sum(r.contribution_eur for r in _year_attribution)
    _year_rows_for_pct = [r for r in _year_rows_with_data if r.delta_pct]
    _year_total_start = sum(
        r.contribution_eur / (r.delta_pct / 100)
        for r in _year_rows_for_pct
        if r.delta_pct != 0
    )
    _year_total_pct = (_year_total_contrib / _year_total_start * 100) if _year_total_start > 0 else None
    _year_sign = "+" if _year_total_contrib >= 0 else ""
    _year_pct_str = f"{_year_total_pct:+.1f}%" if _year_total_pct is not None else "n/a"
    st.caption(
        f"**Portfolio gesamt {_year_label}: {_year_pct_str} ({_year_sign}{symbol()}{_year_total_contrib:,.0f})**"
        .replace(",", "X").replace(".", ",").replace("X", ".")
    )

    if _year_rows_with_data:
        _df_year_attr = pd.DataFrame([
            {"Symbol": r.symbol, "Beitrag (€)": r.contribution_eur}
            for r in _year_rows_with_data
        ]).sort_values("Beitrag (€)")
        _fig_year_attr = px.bar(
            _df_year_attr, x="Symbol", y="Beitrag (€)",
            color="Beitrag (€)",
            color_continuous_scale=["red", "lightgrey", "green"],
            color_continuous_midpoint=0,
            text=_df_year_attr["Beitrag (€)"].apply(lambda v: f"{v:+,.0f}€".replace(",", "X").replace(".", ",").replace("X", ".")),
        )
        _fig_year_attr.update_traces(textposition="outside")
        _fig_year_attr.update_layout(coloraxis_showscale=False, margin=dict(t=20))
        st.plotly_chart(_fig_year_attr, use_container_width=True)

    _year_table_rows = []
    _has_dividends_year = any(r.dividend_contribution_eur > 0 for r in _year_attribution)
    for r in _year_attribution:
        row = {
            "Symbol": r.symbol,
            "Klasse": t(f"investment_types.{r.investment_type}") if r.investment_type else r.investment_type,
            "Jahresstart (€)": f"{r.start_price_eur:,.2f}" if r.start_price_eur else "—",
            "Aktuell (€)": f"{r.end_price_eur:,.2f}" if r.end_price_eur else "—",
            "∆ Jahr": f"{r.delta_pct:+.1f}%" if r.delta_pct is not None else "—",
            "Gewichtung": f"{r.weight_pct:.1f}%",
            "Beitrag (€)": f"{r.contribution_eur:+,.0f}" if r.contribution_eur != 0 else "0",
        }
        if _has_dividends_year:
            row["Div. (€)*"] = f"+{r.dividend_contribution_eur:,.0f}" if r.dividend_contribution_eur > 0 else "—"
        _year_table_rows.append(row)
    st.dataframe(pd.DataFrame(_year_table_rows), use_container_width=True, hide_index=True)
    _year_captions = ["Start = letzter Schlusskurs des Vorjahres (31. Dez), Ende = letzter Schlusskurs des Jahres (laufendes Jahr: aktueller Kurs)."]
    if _has_dividends_year:
        _year_captions.append("* Div. = geschätzte Jahresdividende (aktuelle Rate — keine tatsächlichen Zahlungen).")
    st.caption(" ".join(_year_captions))
else:
    st.info(f"Keine historischen Preisdaten für {_year_label} verfügbar. Preishistorie muss geladen sein.")

st.divider()

# ------------------------------------------------------------------
# FEAT-37: Jahresdigest
# ------------------------------------------------------------------
_yearly_digest_repo = get_yearly_digest_repo()
_year_digest_key = _year_label  # "2026"

with st.expander(f"📋 Jahresdigest {_year_label}", expanded=False):
    _year_digest = _yearly_digest_repo.get(_year_digest_key)
    if _year_digest:
        st.markdown(_year_digest.body_markdown)
        st.caption(f"{t('common.generated_at')} {fmt_dt(_year_digest.generated_at)} UTC")
        if st.button("🔄 Digest neu generieren", key="regen_year_digest"):
            _year_md = generate_yearly_digest(
                valuations, _analyses_repo, _app_config_repo,
                _sel_year_val, market_repo=_market_repo,
                monthly_digest_repo=_digest_repo,
            )
            _yearly_digest_repo.save(_year_digest_key, _year_md)
            st.rerun()
    else:
        if _is_current_year:
            st.info(
                f"Kein Digest für {_year_label} (laufendes Jahr). "
                "Der Scheduler generiert den Digest automatisch am Jahresende. "
                "Jetzt generieren zeigt den Stand von heute."
            )
        else:
            st.info(f"Noch kein Digest für {_year_label}.")
        if st.button("✨ Digest jetzt generieren", key="gen_year_digest"):
            with st.spinner("Generiere Jahresdigest..."):
                _year_md = generate_yearly_digest(
                    valuations, _analyses_repo, _app_config_repo,
                    _sel_year_val, market_repo=_market_repo,
                    monthly_digest_repo=_digest_repo,
                )
            _yearly_digest_repo.save(_year_digest_key, _year_md)
            st.rerun()

st.divider()

# ------------------------------------------------------------------
# P&L per position (total, vs. cost basis)
# ------------------------------------------------------------------
st.subheader(t("analysis.pnl_chart"))

col_pnl_eur = t("common.pnl_eur")
col_pnl_pct = t("common.pnl_pct")
col_value = t("common.value")

pnl_rows = [
    {"Symbol": v.symbol, col_pnl_eur: v.pnl_eur, col_pnl_pct: v.pnl_pct, col_value: v.current_value_eur}
    for v in valuations if v.pnl_eur is not None
]

if pnl_rows:
    df_pnl = pd.DataFrame(pnl_rows).sort_values(col_pnl_eur)
    fig_pnl = px.bar(
        df_pnl, x="Symbol", y=col_pnl_eur,
        color=col_pnl_eur,
        color_continuous_scale=["red", "lightgrey", "green"],
        color_continuous_midpoint=0,
        text=df_pnl[col_pnl_pct].apply(lambda x: f"{x:+.1f}%"),
    )
    fig_pnl.update_traces(textposition="outside")
    fig_pnl.update_layout(coloraxis_showscale=False, margin=dict(t=20))
    st.plotly_chart(fig_pnl, use_container_width=True)
else:
    st.info(t("analysis.no_pnl"))

st.divider()

# ------------------------------------------------------------------
# Portfolio allocation — Sunburst with positions outer ring
# ------------------------------------------------------------------
st.subheader(t("analysis.weight_by_position"))

# Sector grouping for 3-level sunburst (Sektor → Anlageklasse → Position)
_SEKTOR_MAP = {
    "Wertpapiere": "Wertpapiere",
    "Renten": "Geldwerte",
    "Geld": "Geldwerte",
    "Bargeld": "Geldwerte",
    "Immobilien": "Sachwerte",
    "Rohstoffe": "Sachwerte",
    "Krypto": "Krypto",
}

rows = [
    {
        "sektor": _SEKTOR_MAP.get(v.investment_type, v.investment_type),
        "anlageklasse": t(f"investment_types.{v.investment_type}"),
        "position": v.symbol,
        "wert": v.current_value_eur
    }
    for v in valuations
    if v.current_value_eur
]
if rows:
    df = pd.DataFrame(rows).groupby(["sektor", "anlageklasse", "position"])["wert"].sum().reset_index()
    fig = px.sunburst(
        df,
        path=["sektor", "anlageklasse", "position"],
        values="wert",
        color="sektor"
    )
    fig.update_layout(margin=dict(t=0, b=0, l=0, r=0))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info(t("analysis.no_weight_data"))

st.divider()

# ------------------------------------------------------------------
# Bargeldcheck — deterministisch
# ------------------------------------------------------------------
st.subheader("💰 Bargeldcheck")

from state import get_skills_repo

skills_repo = get_skills_repo()
cash_skills = skills_repo.get_by_area("portfolio_cash_rule")
cash_skill = next((s for s in cash_skills if not s.hidden), None)

if cash_skill:
    # Parse skill prompt for min/max cash percentages (simple string parsing, not YAML to avoid injection)
    try:
        min_pct = 5.0
        max_pct = 15.0
        if cash_skill.prompt:
            # Extract min_pct and max_pct from skill prompt (supports "min_pct: 5" format)
            lines = cash_skill.prompt.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('min_pct:'):
                    try:
                        min_pct = float(line.split(':', 1)[1].strip())
                    except (ValueError, IndexError):
                        pass
                elif line.startswith('max_pct:'):
                    try:
                        max_pct = float(line.split(':', 1)[1].strip())
                    except (ValueError, IndexError):
                        pass
        # Validate ranges
        min_pct = max(0, min(100, min_pct))
        max_pct = max(0, min(100, max_pct))
        if min_pct > max_pct:
            min_pct, max_pct = 5.0, 15.0
    except Exception:
        min_pct, max_pct = 5.0, 15.0

    total_eur = sum(v.current_value_eur for v in valuations if v.current_value_eur)
    cash_eur = sum(
        v.current_value_eur
        for v in valuations
        if v.current_value_eur and v.investment_type == "Bargeld"
    )
    cash_pct = (cash_eur / total_eur * 100) if total_eur > 0 else 0

    if cash_pct < min_pct:
        status, icon = "🔴 Zu niedrig", "error"
    elif cash_pct > max_pct:
        status, icon = "🟡 Zu hoch", "warning"
    else:
        status, icon = "🟢 OK", "success"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Bargeld-Anteil", f"{cash_pct:.1f}%", delta=None)
    with col2:
        st.metric("Ziel-Range", f"{min_pct:.0f}–{max_pct:.0f}%")
    with col3:
        st.metric("Status", status.replace(" ", "\n"))

    st.info(f"Regel: {cash_skill.name}")
else:
    st.info("Keine Bargeldcheck-Regel aktiviert")

st.divider()

# ------------------------------------------------------------------
# Stabilitätscheck (Josef's Regel) — deterministisch
# ------------------------------------------------------------------
st.subheader("🏛️ Stabilitätscheck (Josef's Regel)")

from core.portfolio_stability import compute_josef_allocation

stability_skills = skills_repo.get_by_area("portfolio_stability")
stability_skill = next((s for s in stability_skills if not s.hidden), None)

if stability_skills:
    # Use correct Josef allocation calculation
    josef = compute_josef_allocation(valuations)
    aktien_pct = josef["Aktien"]
    renten_pct = josef["Renten/Geld"]
    rohstoffe_pct = josef["Rohstoffe"]

    ziel_pct = 33.33
    def _dev(pct: float) -> str:
        d = pct - ziel_pct
        return f"{d:+.0f}pp"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Aktien", f"{aktien_pct:.1f}%", delta=_dev(aktien_pct))
    with col2:
        st.metric("Renten/Geld", f"{renten_pct:.1f}%", delta=_dev(renten_pct))
    with col3:
        st.metric("Rohstoffe+Immo", f"{rohstoffe_pct:.1f}%", delta=_dev(rohstoffe_pct))

    max_dev = max(abs(aktien_pct - ziel_pct), abs(renten_pct - ziel_pct), abs(rohstoffe_pct - ziel_pct))
    if max_dev <= 5:
        status = "🟢 Stabil"
    elif max_dev <= 15:
        status = "🟡 Achtung"
    else:
        status = "🔴 Instabil"

    st.info(f"**Stabilitätsstatus:** {status} (max. Abweichung: {max_dev:.0f}pp von Ziel 33%)")
else:
    st.info("Keine Stabilitätscheck-Regeln aktiviert")

st.divider()

# ------------------------------------------------------------------
# Dividendencheck — deterministisch
# ------------------------------------------------------------------
st.subheader("💰 Portfolio-Dividenden")

total_dividend = sum(
    v.annual_dividend_eur
    for v in valuations
    if v.annual_dividend_eur
)
total_eur = sum(v.current_value_eur for v in valuations if v.current_value_eur)
dividend_yield = (total_dividend / total_eur * 100) if total_eur > 0 else 0

col1, col2 = st.columns(2)
with col1:
    st.metric("Jährliche Gesamtdividende", f"{total_dividend:.0f}€")
with col2:
    st.metric("Dividend Yield", f"{dividend_yield:.2f}%")

st.divider()

# ------------------------------------------------------------------
# Empfehler-Attribution
# ------------------------------------------------------------------

@dataclass
class AttributionRow:
    """Performance metrics aggregated by recommendation source."""
    source: Optional[str]
    count: int
    cost_basis_eur: float
    current_value_eur: float
    pnl_eur: float
    hit_rate_pct: float
    cagr_pct: Optional[float]
    cagr_with_dividend_pct: Optional[float]


def _compute_attribution(positions, valuations) -> dict[str, AttributionRow]:
    """
    Compute performance attribution by recommendation_source.
    Only includes portfolio positions (excludes watchlist).

    Returns dict {source_name: AttributionRow}, sorted by absolute P&L descending.
    """
    from datetime import date as dateobj

    # Map valuations by symbol for quick lookup
    val_by_symbol = {v.symbol: v for v in valuations}

    # Filter: only portfolio positions (exclude watchlist and analysis_excluded)
    portfolio_positions = [p for p in positions if p.in_portfolio and not p.analysis_excluded]

    # Group positions by recommendation_source
    grouped = {}
    for pos in portfolio_positions:
        source = pos.recommendation_source or "(ohne Angabe)"
        if source not in grouped:
            grouped[source] = []
        grouped[source].append(pos)

    # Compute metrics per source
    results = {}
    for source, pos_list in grouped.items():
        count = len(pos_list)
        cost_basis_eur = 0.0
        current_value_eur = 0.0
        pnl_eur = 0.0
        profitable_count = 0

        cagr_sum_weighted = 0.0
        cagr_sum_weight = 0.0
        cagr_div_sum_weighted = 0.0

        for pos in pos_list:
            val = val_by_symbol.get(pos.ticker or pos.name)
            if not val:
                continue

            # Aggregates
            if val.cost_basis_eur:
                cost_basis_eur += val.cost_basis_eur
            if val.current_value_eur:
                current_value_eur += val.current_value_eur
            if val.pnl_eur is not None:
                pnl_eur += val.pnl_eur
                if val.pnl_eur > 0:
                    profitable_count += 1

            # CAGR calculation (only if purchase_date exists and is recent enough)
            if (pos.purchase_date and val.cost_basis_eur and val.cost_basis_eur > 0
                    and val.current_value_eur and val.current_value_eur > 0):
                years_held = (dateobj.today() - pos.purchase_date).days / 365.25

                # Only compute CAGR if held > 14 days (avoid extreme annualization)
                if years_held > 14 / 365.25:
                    try:
                        cagr = (pow(val.current_value_eur / val.cost_basis_eur, 1 / years_held) - 1) * 100
                        cagr_sum_weighted += cagr * val.cost_basis_eur
                        cagr_sum_weight += val.cost_basis_eur

                        # CAGR with estimated dividend
                        estimated_div = (val.annual_dividend_eur or 0) * years_held
                        total_gain = (val.pnl_eur or 0) + estimated_div
                        cagr_div = (pow((val.cost_basis_eur + total_gain) / val.cost_basis_eur, 1 / years_held) - 1) * 100
                        cagr_div_sum_weighted += cagr_div * val.cost_basis_eur
                    except (ValueError, ZeroDivisionError):
                        pass

        # Compute weighted averages (cagr already includes * 100 from formula)
        cagr = (cagr_sum_weighted / cagr_sum_weight if cagr_sum_weight > 0 else None)
        cagr_div = (cagr_div_sum_weighted / cagr_sum_weight if cagr_sum_weight > 0 else None)

        hit_rate = (profitable_count / count * 100) if count > 0 else 0

        results[source] = AttributionRow(
            source=source,
            count=count,
            cost_basis_eur=cost_basis_eur,
            current_value_eur=current_value_eur,
            pnl_eur=pnl_eur,
            hit_rate_pct=hit_rate,
            cagr_pct=cagr,
            cagr_with_dividend_pct=cagr_div,
        )

    # Sort by P&L descending
    return dict(sorted(results.items(), key=lambda x: x[1].pnl_eur, reverse=True))


# Render attribution expander
with st.expander("📊 Empfehler-Attribution", expanded=False):
    portfolio_service = get_portfolio_service()
    all_positions = portfolio_service.get_all_positions(include_portfolio=True, include_watchlist=True)

    if not all_positions:
        st.info("Keine Positionen vorhanden.")
    else:
        attribution = _compute_attribution(all_positions, valuations)

        if not attribution:
            st.info("Keine Empfehler-Daten verfügbar.")
        else:
            # Build dataframe for display
            rows = []
            for source, row in attribution.items():
                rows.append({
                    "Empfehler": row.source,
                    "Anzahl": row.count,
                    "Kapital (€)": f"{row.cost_basis_eur:,.0f}",
                    "Aktuell (€)": f"{row.current_value_eur:,.0f}",
                    "G/V (€)": f"{row.pnl_eur:+,.0f}",
                    "Hit Rate": f"{row.hit_rate_pct:.0f}%",
                    "CAGR": f"{row.cagr_pct:.1f}%" if row.cagr_pct is not None else "n/a",
                    "Total Return (~)": f"{row.cagr_with_dividend_pct:.1f}%" if row.cagr_with_dividend_pct is not None else "n/a",
                })

            df_attr = pd.DataFrame(rows)
            st.dataframe(df_attr, use_container_width=True, hide_index=True)

            # Explanation
            st.caption(
                "**CAGR**: Kapitalgewichtete annualisierte Rendite (nur Kursgewinne). "
                "**Total Return (~)**: geschätzte Rendite inklusive Dividenden (basiert auf aktuelle Jahresrate). "
                "Positionen ohne Kaufdatum oder Zeitraum < 2 Wochen werden ausgeklammert."
            )
