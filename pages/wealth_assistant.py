"""
Wealth Assistant — manage portfolio snapshots and view history.
Create, preview, edit, and delete wealth snapshots with asset class breakdown.
"""

from datetime import date
import streamlit as st
from core.currency import fmt, symbol
from core.i18n import t
from state import get_wealth_snapshot_agent

st.set_page_config(page_title="Wealth Assistant", page_icon="💰", layout="wide")
st.title(f"💰 {t('wealth_assistant.title')}")

wealth_agent = get_wealth_snapshot_agent()

# ------------------------------------------------------------------
# Header: Latest snapshot summary
# ------------------------------------------------------------------
latest = wealth_agent.get_latest_snapshot()

col1, col2, col3, col4 = st.columns(4)
with col1:
    if latest:
        st.metric(
            t("wealth_assistant.latest_snapshot"),
            latest.date,
        )
    else:
        st.metric(
            t("wealth_assistant.latest_snapshot"),
            "—",
        )

with col2:
    if latest:
        st.metric(
            t("dashboard.total_wealth"),
            fmt(latest.total_eur, 0),
        )
    else:
        st.metric(
            t("dashboard.total_wealth"),
            "—",
        )

with col3:
    if latest:
        st.metric(
            t("wealth_assistant.coverage"),
            f"{latest.coverage_pct:.0f}%",
        )
    else:
        st.metric(
            t("wealth_assistant.coverage"),
            "—",
        )

with col4:
    if latest:
        st.metric(
            t("wealth_assistant.is_manual"),
            "✓" if latest.is_manual else "—",
        )
    else:
        st.metric(
            t("wealth_assistant.is_manual"),
            "—",
        )

st.divider()

# ------------------------------------------------------------------
# Action buttons: Prepare & Snapshot
# ------------------------------------------------------------------
col_prep, col_snap, col_space = st.columns([2, 2, 4])

with col_prep:
    if st.button(
        f"🔄 {t('wealth_assistant.prepare')}",
        use_container_width=True,
        help=t("wealth_assistant.prepare_help"),
    ):
        st.session_state["_prepare_preview"] = None
        try:
            preview = wealth_agent.prepare_snapshot()
            st.session_state["_prepare_preview"] = preview
            st.success(t("wealth_assistant.prepare_success"))
        except Exception as exc:
            st.error(f"⚠️ {t('common.agent_error')}: {exc}")

with col_snap:
    if st.button(
        f"📸 {t('wealth_assistant.take_snapshot')}",
        use_container_width=True,
        help=t("wealth_assistant.take_snapshot_help"),
    ):
        today = date.today().isoformat()
        existing = wealth_agent.get_snapshot_for_date(today)
        if existing:
            st.session_state["_overwrite_pending"] = True
            st.rerun()
        else:
            try:
                snapshot = wealth_agent.take_snapshot(is_manual=False)
                st.success(
                    t("wealth_assistant.snapshot_success")
                    + f"\n€ {snapshot.total_eur:,.0f} | {snapshot.coverage_pct:.0f}% Coverage"
                )
                st.rerun()
            except Exception as exc:
                st.error(f"⚠️ {t('common.agent_error')}: {exc}")

# Show prepare preview if available
if st.session_state.get("_prepare_preview"):
    preview = st.session_state["_prepare_preview"]
    with st.expander(t("wealth_assistant.preview_title"), expanded=True):
        st.write(f"**{t('dashboard.total_wealth')}**: {fmt(preview.total_eur, 0)}")
        st.write(f"**{t('wealth_assistant.coverage')}**: {preview.coverage_pct:.0f}%")

        if preview.stale_positions:
            st.warning(
                f"**{t('wealth_assistant.stale_positions')}** ({len(preview.stale_positions)}):"
            )
            for pos in preview.stale_positions:
                value_str = f"{fmt(pos['value'], 0)}" if pos['value'] is not None else "—"
                st.write(
                    f"  • {pos['name']}: {value_str} ({pos['days_old']} Tage alt)"
                )

        if preview.warnings:
            st.info("\n".join(preview.warnings))

st.divider()

# ------------------------------------------------------------------
# Overwrite confirmation dialog
# ------------------------------------------------------------------
@st.dialog(t("wealth_assistant.overwrite_title"), width="large")
def _overwrite_confirm_dialog(date_str: str):
    """Dialog to confirm overwriting an existing snapshot."""
    existing = wealth_agent.get_snapshot_for_date(date_str)
    st.write(f"**{t('wealth_assistant.overwrite_message')}**")
    st.write(f"{date_str}: {fmt(existing.total_eur, 0)}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button(t("wealth_assistant.overwrite_confirm"), type="primary"):
            try:
                wealth_agent.take_snapshot(date_str=date_str, overwrite=True, is_manual=True)
                st.session_state.pop("_overwrite_pending", None)
                st.success(t("wealth_assistant.snapshot_success"))
                st.rerun()
            except Exception as exc:
                st.error(f"⚠️ {t('common.agent_error')}: {exc}")
    with col2:
        if st.button(t("wealth_assistant.overwrite_cancel")):
            st.session_state.pop("_overwrite_pending", None)
            st.rerun()


# Show overwrite dialog if pending
if st.session_state.get("_overwrite_pending"):
    _overwrite_confirm_dialog(date.today().isoformat())

st.divider()

# ------------------------------------------------------------------
# Snapshot list with edit/delete
# ------------------------------------------------------------------
st.subheader("📋 Letzte Snapshots")

try:
    snapshots = wealth_agent.list_snapshots(days=None)
    if snapshots:
        # Show last 10 snapshots
        for snapshot in snapshots[-10:]:
            col_info, col_actions = st.columns([4, 1])
            with col_info:
                st.write(f"**{snapshot.date}** — € {snapshot.total_eur:,.0f} ({snapshot.coverage_pct:.0f}% Coverage) {'✓ Manuell' if snapshot.is_manual else ''}")
            with col_actions:
                if st.button(f"✏️ Bearbeiten", key=f"edit_{snapshot.id}"):
                    st.session_state["_edit_snapshot_id"] = snapshot.id
                    st.rerun()

        # Edit dialog
        @st.dialog("Snapshot bearbeiten", width="large")
        def _edit_snapshot_dialog(snapshot):
            st.write(f"**{snapshot.date}**")

            # Editable inputs for each asset class
            new_breakdown = {}
            for asset_class, value in sorted(snapshot.breakdown.items()):
                new_breakdown[asset_class] = st.number_input(
                    asset_class,
                    value=float(value),
                    min_value=0.0,
                    step=1000.0,
                    format="%.2f",
                    key=f"_edit_{asset_class}_{snapshot.date}",
                )

            # Auto-calculated total
            new_total = sum(new_breakdown.values())
            st.metric("Gesamtwert", fmt(new_total, 0))

            # Note field
            new_note = st.text_input(
                "Notiz",
                value=snapshot.note or "",
                key=f"_edit_note_{snapshot.date}",
            )

            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Speichern", type="primary", key=f"_save_{snapshot.date}"):
                    try:
                        wealth_agent.edit_snapshot(
                            snapshot.date,
                            new_breakdown,
                            new_note or None,
                        )
                        st.session_state.pop("_edit_snapshot_id", None)
                        st.success("Snapshot gespeichert!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"⚠️ {t('common.agent_error')}: {exc}")
            with col2:
                if st.button("Löschen", key=f"_del_{snapshot.date}"):
                    try:
                        wealth_agent.delete_snapshot(snapshot.date)
                        st.session_state.pop("_edit_snapshot_id", None)
                        st.success("Snapshot gelöscht!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"⚠️ {t('common.agent_error')}: {exc}")

        # Show edit dialog if selected
        if st.session_state.get("_edit_snapshot_id"):
            for snap in snapshots:
                if snap.id == st.session_state["_edit_snapshot_id"]:
                    _edit_snapshot_dialog(snap)
                    break

    else:
        st.info(t("dashboard.no_snapshots"))

except Exception as exc:
    st.warning(f"⚠️ {t('common.agent_error')}: {exc}")
