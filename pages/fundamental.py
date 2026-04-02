"""
Fundamentalwert-Analyse — Über-/Unterbewertung von Portfolio-Positionen.

Bewertet Aktien und Fonds anhand von KGV, KBV, EV/EBITDA und vereinfachtem DCF.
"""

import asyncio

import streamlit as st

from core.i18n import t
from state import (
    get_analyses_repo,
    get_fundamental_agent,
    get_positions_repo,
    get_skills_repo,
)

st.set_page_config(
    page_title="Fundamentalwert",
    page_icon="📐",
    layout="wide",
)
st.title(f"📐 {t('fundamental.title')}")
st.caption(t("fundamental.subtitle"))

_agent = get_fundamental_agent()
_positions_repo = get_positions_repo()
_analyses_repo = get_analyses_repo()
_skills = get_skills_repo().get_by_area("fundamental")

# ------------------------------------------------------------------
# Verdict display
# ------------------------------------------------------------------

_VERDICT_CONFIG = {
    "unterbewertet": ("🟢", t("fundamental.verdict_unter")),
    "fair":          ("🟡", t("fundamental.verdict_fair")),
    "überbewertet":  ("🔴", t("fundamental.verdict_ueber")),
    "unbekannt":     ("⚪", t("fundamental.verdict_unbekannt")),
}


def _verdict_badge(verdict: str) -> str:
    icon, label = _VERDICT_CONFIG.get(verdict, ("⚪", verdict))
    return f"{icon} {label}"


# ------------------------------------------------------------------
# Load positions
# ------------------------------------------------------------------

_all_positions = _positions_repo.get_portfolio()
_eligible = [p for p in _all_positions if p.ticker]

if not _eligible:
    st.info(t("fundamental.no_eligible"))
    st.stop()

_all_ids = [p.id for p in _eligible if p.id]
_current_verdicts = _analyses_repo.get_latest_bulk(_all_ids, agent="fundamental")

# ------------------------------------------------------------------
# Run analysis
# ------------------------------------------------------------------

if not _skills:
    st.warning(t("fundamental.no_skills"))
else:
    _skill_options = {s.name: s for s in _skills}
    col_skill, col_btn = st.columns([3, 1])
    with col_skill:
        _sel_skill_name = st.selectbox(
            t("fundamental.skill_label"),
            options=list(_skill_options.keys()),
            key="_fund_skill",
        )
    with col_btn:
        st.write("")
        st.write("")
        if st.button(
            t("fundamental.run_button"),
            type="primary",
            key="_fund_run",
            use_container_width=True,
        ):
            _sel_skill = _skill_options[_sel_skill_name]
            with st.spinner(t("fundamental.running")):
                results = asyncio.run(
                    _agent.analyze_portfolio(
                        positions=_eligible,
                        skill_name=_sel_skill.name,
                        skill_prompt=_sel_skill.prompt,
                        analyses_repo=_analyses_repo,
                    )
                )
            st.success(
                f"✅ {len(results)} {t('fundamental.analysis_done')}",
                icon=":material/check_circle:",
            )
            st.rerun()

st.divider()

# ------------------------------------------------------------------
# Summary bar
# ------------------------------------------------------------------

_analysed = {pid: a for pid, a in _current_verdicts.items()}
if _analysed:
    _counts = {"unterbewertet": 0, "fair": 0, "überbewertet": 0, "unbekannt": 0}
    for a in _analysed.values():
        if a.verdict in _counts:
            _counts[a.verdict] += 1

    _sc1, _sc2, _sc3, _sc4 = st.columns(4)
    _sc1.metric("🟢 " + t("fundamental.verdict_unter"), _counts["unterbewertet"])
    _sc2.metric("🟡 " + t("fundamental.verdict_fair"),  _counts["fair"])
    _sc3.metric("🔴 " + t("fundamental.verdict_ueber"), _counts["überbewertet"])
    _sc4.metric("⚪ " + t("fundamental.verdict_unbekannt"), _counts["unbekannt"])
    st.divider()

# ------------------------------------------------------------------
# Position cards
# ------------------------------------------------------------------

st.subheader(t("fundamental.positions_header"))

_eligible_sorted = sorted(_eligible, key=lambda p: p.name.lower())

for _pos in _eligible_sorted:
    _analysis = _current_verdicts.get(_pos.id)
    _verdict = _analysis.verdict if _analysis else None
    _icon = _VERDICT_CONFIG.get(_verdict, ("⚪", ""))[0] if _verdict else "⚪"

    with st.container(border=True):
        _hc1, _hc2 = st.columns([5, 2])
        with _hc1:
            st.markdown(f"**{_icon} {_pos.name}** · `{_pos.ticker}`")
            st.caption(f"{_pos.asset_class}" + (f" · {_pos.anlageart}" if _pos.anlageart else ""))
        with _hc2:
            if _verdict:
                st.markdown(_verdict_badge(_verdict))
                if _analysis and _analysis.created_at:
                    st.caption(_analysis.created_at.strftime("%d.%m.%Y"))
            else:
                st.caption(t("fundamental.not_yet_analyzed"))

        if _analysis and _analysis.summary:
            st.markdown(f"_{_analysis.summary}_")

st.divider()

# ------------------------------------------------------------------
# Legend
# ------------------------------------------------------------------

with st.expander(t("fundamental.legend_header")):
    for verdict, (icon, label) in _VERDICT_CONFIG.items():
        st.markdown(f"**{icon} {label}** — {t(f'fundamental.legend_{verdict}')}")
