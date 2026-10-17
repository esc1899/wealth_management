"""
Statistics — was Wealth die Sprachmodelle kostet, je Monat und je Agent.

Seit 12.10.2026 nur noch, was der Maschinenraum nicht zeigt: Er summiert den laufenden Monat
des ganzen Hauses je Anbieter, Zweck und Programm; hier stehen der Verlauf ueber die Monate und
die Kosten je Agent seit dem letzten Reset. Seit 17.10.2026 vorn die letzten Laeufe mit ihren
Kosten (``core/laeufe.py``): Die App soll ohne das Haus sagen, was wann Geld gekostet hat. Tokens, Tageskurve, letzte Aufrufe und der Knopf
zum Abgleich mit OpenRouter sind entfallen -- den Abgleich macht der Job ``kosten``.
"""

from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from core import preise
from core.i18n import t
from core.storage.usage import compute_cost
from state import get_app_config_repo, get_usage_repo

st.set_page_config(page_title="Statistics", page_icon="📊", layout="wide")
st.title(f"📊 {t('statistics.title')}")
st.markdown(t("statistics.satz"))

repo = get_usage_repo()
# Preise und Anbieter aus core/preise.py: Katalog des Hauses, OpenRouter-Liste, lokal kostenlos.
_preisliste = preise.preisliste(get_app_config_repo())

# Provider display names (brand names — language-neutral).
_PROVIDER_LABELS = {
    "claude": "Anthropic",
    "openrouter": "OpenRouter",
    "deepseek": "DeepSeek (direkt, alt)",
    "ollama": "Ollama",
}

alltime_rows = repo.total_all_time()
monthly_rows = repo.monthly_totals_by_model()


def _row_cost(r: dict) -> float:
    """Listenpreis einer Zeile; ein Modell ohne Preis zaehlt 0 und wird unten genannt."""
    return compute_cost(
        r["input_tokens"],
        r["output_tokens"],
        r["model"],
        {r["model"]: preise.preis(r["model"], _preisliste) or {}},
        r.get("cache_read_tokens"),
        r.get("cache_write_tokens"),
        r.get("web_search_requests"),
        batch=r.get("source") == "batch",
    )


# ------------------------------------------------------------------
# Dieser und letzter Monat
# ------------------------------------------------------------------

today = date.today()
current_month = today.strftime("%Y-%m")
last_month = f"{today.year - 1}-12" if today.month == 1 else f"{today.year}-{today.month - 1:02d}"

this_month_rows = [r for r in monthly_rows if r["month"] == current_month]
last_month_rows = [r for r in monthly_rows if r["month"] == last_month]

m1, m2 = st.columns(2)
m1.metric(t("statistics.this_month"), f"${sum(_row_cost(r) for r in this_month_rows):.2f}",
          delta=f"{sum(r.get('calls', 0) for r in this_month_rows)} Calls", delta_color="off")
m2.metric(t("statistics.last_month"), f"${sum(_row_cost(r) for r in last_month_rows):.2f}",
          delta=f"{sum(r.get('calls', 0) for r in last_month_rows)} Calls", delta_color="off")

# Je Anbieter (dieser Monat): die Summe geht ueber Anthropic, OpenRouter und Ollama.
_provider_month: dict[str, float] = {}
for r in this_month_rows:
    p = preise.anbieter(r["model"])
    _provider_month[p] = _provider_month.get(p, 0.0) + _row_cost(r)

if _provider_month:
    st.caption(t("statistics.by_provider_header"))
    _ordered = [p for p in ("claude", "openrouter", "deepseek", "ollama") if p in _provider_month]
    for _col, _p in zip(st.columns(len(_ordered)), _ordered):
        _col.metric(_PROVIDER_LABELS.get(_p, _p), f"${_provider_month[_p]:.2f}")

# Blindzeit ist eine Aussage: Ein Modell ohne Preis ist in den Summen 0 -- das sagt die Seite.
_offen = sorted({r["model"] for r in monthly_rows if preise.preis(r["model"], _preisliste) is None})
if _offen:
    st.caption(t("statistics.ohne_preis").format(modelle=", ".join(_offen)))

st.divider()

tab_laeufe, tab_trend, tab_agents = st.tabs([t("statistics.tab_laeufe"), t("statistics.tab_trend"),
                                             t("statistics.tab_agents")])

# ── Tab: Letzte Läufe ──────────────────────────────────────────────────────────

with tab_laeufe:
    from core import laeufe as _laeufe

    _TAGE = 14
    st.markdown(t("statistics.laeufe_satz").format(tage=_TAGE))

    def _kosten_oder_offen(r: dict):
        return _row_cost(r) if preise.preis(r["model"], _preisliste) is not None else None

    def _wer(z: dict) -> str:
        if z["wie"] == _laeufe.BATCH:
            return t("statistics.laeufe_batch")
        if z["wie"] == _laeufe.HAND:
            return t("statistics.laeufe_hand")
        if z["job"] in (None, "scheduler"):
            return t("statistics.laeufe_app_job")
        return z["job"]

    _zeilen = _laeufe.laeufe(repo.aufrufe_seit(_TAGE), _kosten_oder_offen)
    if _zeilen:
        st.dataframe(pd.DataFrame([{
            t("statistics.col_wann"): z["wann"].strftime("%d.%m. %H:%M"),
            t("statistics.col_job"): _wer(z),
            t("statistics.col_was"): ", ".join(z["agenten"]),
            t("statistics.col_modell"): ", ".join(z["modelle"]),
            "Calls": z["aufrufe"],
            t("statistics.col_kosten"): (f"{z['kosten']:.3f}" + (t("statistics.laeufe_offen").format(n=z["offen"]) if z["offen"] else "")),
        } for z in _zeilen]), width="stretch", hide_index=True)
    else:
        st.info(t("statistics.laeufe_keine").format(tage=_TAGE))

# ── Tab: Verlauf ───────────────────────────────────────────────────────────────

with tab_trend:
    st.subheader(t("statistics.monthly_chart"))

    if monthly_rows:
        monthly_agg: dict[str, dict] = {}
        for r in monthly_rows:
            m = r["month"]
            if m not in monthly_agg:
                monthly_agg[m] = {"month": m, "cost": 0.0, "calls": 0}
            monthly_agg[m]["cost"] += _row_cost(r)
            monthly_agg[m]["calls"] += r.get("calls", 0)

        _MONTH_SHORT = {
            "01": "Jan", "02": "Feb", "03": "Mär", "04": "Apr", "05": "Mai", "06": "Jun",
            "07": "Jul", "08": "Aug", "09": "Sep", "10": "Okt", "11": "Nov", "12": "Dez",
        }

        def _month_label(m: str) -> str:
            year, mon = m.split("-")
            return f"{_MONTH_SHORT[mon]} '{year[2:]}"

        sorted_months = sorted(monthly_agg.keys())[-12:]
        df_monthly = pd.DataFrame([monthly_agg[m] for m in sorted_months])
        df_monthly["label"] = df_monthly["month"].apply(_month_label)

        fig = px.bar(
            df_monthly,
            x="label",
            y="cost",
            labels={"label": "", "cost": "Kosten ($)"},
            color_discrete_sequence=["#4C9BE8"],
            text=df_monthly["cost"].apply(lambda v: f"${v:.2f}"),
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            yaxis_title="Kosten ($)", showlegend=False, uniformtext_minsize=8,
            xaxis_type="category",
        )
        st.plotly_chart(fig)
    else:
        st.info(t("statistics.no_data"))

# ── Tab: Nach Agent ────────────────────────────────────────────────────────────

with tab_agents:
    if alltime_rows:
        agent_alltime: dict[str, dict] = {}
        for r in alltime_rows:
            a = r["agent"]
            if a not in agent_alltime:
                agent_alltime[a] = {"cost_total": 0.0, "calls_total": 0}
            agent_alltime[a]["cost_total"] += _row_cost(r)
            agent_alltime[a]["calls_total"] += r.get("calls", 0)

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

        st.dataframe(pd.DataFrame(rows_agent), width="stretch", hide_index=True)
    else:
        st.info(t("statistics.no_data"))
