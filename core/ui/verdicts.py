"""
Shared verdict display components for agent result pages.

Centralizes VERDICT_CONFIG, badge rendering, and legend display
to avoid duplication across pages.
"""

import html
from typing import Dict, Tuple

import streamlit as st

from core.i18n import t


# Verdict configurations per agent area
VERDICT_CONFIGS: Dict[str, Dict[str, Tuple[str, str]]] = {
    "consensus_gap": {
        "wächst":    ("🟢", t("consensus_gap.verdict_waechst")),
        "stabil":    ("🟡", t("consensus_gap.verdict_stabil")),
        "schließt":  ("🔠", t("consensus_gap.verdict_schliesst")),
        "eingeholt": ("🔴", t("consensus_gap.verdict_eingeholt")),
    },
    "fundamental_analyzer": {
        "unterbewertet": ("🟢", t("fundamental_analyzer.verdict_unter") if t("fundamental_analyzer.verdict_unter") != "fundamental_analyzer.verdict_unter" else "Undervalued"),
        "fair":          ("🟡", t("fundamental_analyzer.verdict_fair") if t("fundamental_analyzer.verdict_fair") != "fundamental_analyzer.verdict_fair" else "Fair Value"),
        "überbewertet":  ("🔴", t("fundamental_analyzer.verdict_ueber") if t("fundamental_analyzer.verdict_ueber") != "fundamental_analyzer.verdict_ueber" else "Overvalued"),
    },
    "storychecker": {
        "intact":   ("🟢", "Intakt"),
        "gemischt": ("🟡", "Gemischt"),
        "gefährdet": ("🔴", "Gefährdet"),
    },
    "watchlist_checker": {
        "sehr_passend": ("🟢", "Sehr passend"),
        "passend":      ("🟡", "Passend"),
        "neutral":      ("⚪", "Neutral"),
        "nicht_passend": ("🔴", "Nicht passend"),
    },
    "portfolio_story": {
        "stärkt":   ("🟢", "Stärkt"),
        "neutral":  ("🟡", "Neutral"),
        "schwächt": ("🔴", "Schwächt"),
    },
    "capital_allocator": {
        "exzellent":  ("🟢", t("capital_allocator.verdict_exzellent")),
        "solide":     ("🟡", t("capital_allocator.verdict_solide")),
        "fragwürdig": ("🟠", t("capital_allocator.verdict_fragwuerdig")),
        "destruktiv": ("🔴", t("capital_allocator.verdict_destruktiv")),
    },
}


def verdict_badge(verdict: str, config: Dict[str, Tuple[str, str]]) -> str:
    """Render verdict as icon + label."""
    icon, label = config.get(verdict, ("⚪", html.escape(verdict)))
    return f"{icon} {label}"


def verdict_icon(verdict: str, config: Dict[str, Tuple[str, str]]) -> str:
    """Get icon only for verdict."""
    icon, _ = config.get(verdict, ("⚪", ""))
    return icon


def render_verdict_legend(config: Dict[str, Tuple[str, str]]) -> None:
    """Render expandable legend for verdicts."""
    with st.expander(t("common.legend_header")):
        for verdict, (icon, label) in config.items():
            st.markdown(f"**{icon} {label}** — {t(f'common.legend_{verdict}')}")


def fmt_verdict_matrix(verdict_obj, config_key: str) -> str:
    """Format a verdict object as 'icon verdict' text for dataframe matrix cells."""
    if verdict_obj and verdict_obj.verdict:
        icon = verdict_icon(verdict_obj.verdict, VERDICT_CONFIGS[config_key])
        return f"{icon} {verdict_obj.verdict}"
    return "⚪ —"


def cloud_notice(model: str, provider: str = "claude") -> None:
    """Render standardized cloud/local notice."""
    from config import config
    if provider != "ollama" and config.OPENAI_BASE_URL:
        provider = "openai"

    if provider == "ollama":
        location = "lokal"
        emoji = "🏠"
    elif provider == "openai":
        location = "Cloud (OpenAI-kompatibel)"
        emoji = "🌐"
    else:
        location = "Claude API (Cloud)"
        emoji = "☁️"

    st.info(
        f"{emoji} This analysis runs on **{model}** ({location})",
        icon="ℹ️"
    )
