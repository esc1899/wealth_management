"""
Cowork Research Inbox — display, review, and act on AI-generated research files.

Sections:
  1. Inbox — list of ResearchEntries filtered by status
  2. Detail view — rendered Markdown body, disclaimer, proposal panel (checkbox-based)
  3. Suggestion Queue — already-imported entries, read-only history
"""

from __future__ import annotations

import re
import os
from datetime import date as _date

import streamlit as st

from core.i18n import t
from core.storage.cowork import ResearchEntry, WatchlistSuggestion
from core.storage.models import Position
from state import get_cowork_repo, get_cowork_watcher, get_positions_repo

st.set_page_config(page_title="Research Inbox", page_icon=":material/inbox:", layout="wide")

# Ensure watcher is running (idempotent via @st.cache_resource)
get_cowork_watcher()

cowork_repo = get_cowork_repo()
positions_repo = get_positions_repo()


# ---------------------------------------------------------------------------
# Helper functions (defined before page layout)
# ---------------------------------------------------------------------------

def _write_status_to_file(entry: ResearchEntry, new_status: str) -> None:
    """Atomically update the 'status' field in the .md frontmatter."""
    if not entry.file_path:
        return
    try:
        with open(entry.file_path, encoding="utf-8") as f:
            content = f.read()
        updated = re.sub(
            r"^(status:\s*)(\S+)",
            lambda m: m.group(1) + new_status,
            content,
            count=1,
            flags=re.MULTILINE,
        )
        tmp_path = entry.file_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(updated)
        os.replace(tmp_path, entry.file_path)
    except OSError:
        pass  # best-effort; DB status is source of truth


def _build_position(cand: WatchlistSuggestion) -> Position:
    from core.asset_class_config import get_asset_class_registry
    registry = get_asset_class_registry()
    category = cand.category or "Aktie"
    try:
        cfg = registry.require(category)
    except Exception:
        cfg = registry.require("Aktie")

    notes = cand.rationale
    if cand.isin:
        notes = f"ISIN: {cand.isin}\n\n{notes}"

    return Position(
        ticker=cand.ticker,
        name=cand.name,
        asset_class=cfg.asset_class,
        investment_type=cfg.investment_type,
        unit=cfg.default_unit,
        notes=notes,
        added_date=_date.today(),
        in_portfolio=False,
        in_watchlist=True,
        recommendation_source="cowork_research",
        isin=cand.isin,
    )


def _render_proposal_panel(entry: ResearchEntry, candidates: list[WatchlistSuggestion]) -> None:
    """Checkbox-based proposal panel — same UX pattern as Search Chat."""
    pending = [c for c in candidates if c.status == "pending"]
    if not pending:
        return

    st.subheader(f"📋 Watchlist-Vorschläge ({len(pending)})")
    st.caption(
        "KI-Empfehlungen aus dem Research — wähle aus, welche du zur Watchlist hinzufügen möchtest:"
    )

    for cand in pending:
        conviction_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(cand.conviction, "⚪")
        action_label = "➕ Add" if cand.suggested_action == "add" else "👁 Watch"
        # pre-check 'add' candidates; 'watch' candidates unchecked by default
        default_checked = cand.suggested_action == "add"

        st.checkbox(
            f"**{cand.ticker}** · {cand.name} · `{cand.exchange}` "
            f"{conviction_icon} {cand.conviction.title()} · {action_label}",
            value=default_checked,
            key=f"cand_check_{entry.id}_{cand.id}",
        )
        if cand.rationale:
            st.caption(cand.rationale)
        price_parts = []
        if cand.price_at_research:
            curr = cand.currency or ""
            price_parts.append(f"Kurs: {cand.price_at_research} {curr}".strip())
        if cand.target_price:
            curr = cand.currency or ""
            price_parts.append(f"Ziel: {cand.target_price} {curr}".strip())
        if price_parts:
            st.caption(" → ".join(price_parts))
        if cand.triggers:
            st.caption("Trigger: " + " · ".join(cand.triggers))

    st.divider()
    col_btn, col_skip = st.columns([2, 1])
    with col_btn:
        if st.button("✅ Zur Watchlist hinzufügen", type="primary", key=f"confirm_{entry.id}",
                     use_container_width=True):
            selected = [
                c for c in pending
                if st.session_state.get(f"cand_check_{entry.id}_{c.id}", False)
            ]
            added_count = 0
            for cand in pending:
                if cand in selected:
                    try:
                        positions_repo.add(_build_position(cand))
                        cowork_repo.update_suggestion_status(cand.id, "accepted")
                        added_count += 1
                    except Exception as exc:
                        st.error(f"Fehler bei {cand.ticker}: {exc}")
                else:
                    cowork_repo.update_suggestion_status(cand.id, "rejected")
            cowork_repo.update_status(entry.id, "imported")
            st.success(f"✅ {added_count} Position(en) hinzugefügt, Entry als importiert markiert.")
            st.rerun()
    with col_skip:
        if st.button("⏭ Alle überspringen", key=f"skip_all_{entry.id}", use_container_width=True):
            for cand in pending:
                cowork_repo.update_suggestion_status(cand.id, "rejected")
            cowork_repo.update_status(entry.id, "imported")
            st.rerun()


def _render_imported_candidates(candidates: list[WatchlistSuggestion]) -> None:
    """Read-only view of already-reviewed candidates."""
    if not candidates:
        return
    st.subheader(f"📋 Kandidaten ({len(candidates)})")
    for cand in candidates:
        status_icon = {"accepted": "✅", "rejected": "❌", "pending": "⏳"}.get(cand.status, "•")
        conviction_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(cand.conviction, "⚪")
        st.markdown(
            f"{status_icon} **{cand.ticker}** · {cand.name} · `{cand.exchange}` "
            f"{conviction_icon} {cand.conviction.title()} · `{cand.status}`"
        )
        if cand.rationale:
            st.caption(cand.rationale)


def _render_entry_detail(entry: ResearchEntry) -> None:
    # AI Research badge + disclaimer
    st.warning(
        f"🤖 **AI Research** · Modell: `{entry.model}` · Datum: {entry.date}\n\n"
        f"{entry.disclaimer}",
        icon=":material/smart_toy:",
    )

    st.markdown(f"### {entry.research_id}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Typ", entry.type.replace("_", " ").title())
    col2.metric("Status", entry.status)
    col3.metric("Modell", entry.model)

    if entry.primary_ticker:
        parts = [
            f"**Primary:** `{entry.primary_ticker}`",
            entry.primary_name or "",
            f"({entry.primary_exchange or ''})",
        ]
        if entry.primary_sentiment:
            parts.append(f"Sentiment: {entry.primary_sentiment}")
        if entry.primary_confidence:
            parts.append(f"Confidence: {entry.primary_confidence}")
        st.markdown(" · ".join(p for p in parts if p.strip("()")))

    candidates = cowork_repo.list_suggestions(research_id=entry.research_id)

    if entry.status == "draft":
        st.info("📝 Draft — noch nicht bereit für Import. Status im Research-File auf `ready_for_import` setzen.")
    elif entry.status == "ready_for_import":
        st.divider()
        _render_proposal_panel(entry, candidates)
    elif entry.status == "imported":
        st.divider()
        _render_imported_candidates(candidates)
    elif entry.status == "failed":
        st.error(f"**Fehler:** {entry.failure_reason}")

    if entry.body_markdown:
        st.divider()
        with st.expander("📄 Research-Text", expanded=(entry.status == "draft")):
            st.markdown(entry.body_markdown)

    if entry.sources:
        st.divider()
        st.markdown("**Quellen:**")
        for src in entry.sources:
            st.markdown(f"- [{src}]({src})")


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

st.title(":material/inbox: Research Inbox")
st.caption(
    "KI-generiertes Research aus dem Cowork-Outbox-Ordner. "
    "Alle Einträge sind **AI Research** — keine Anlageberatung."
)

tab_inbox, tab_history = st.tabs(["📥 Inbox", "📦 Importiert"])

# ===========================================================================
# TAB 1: INBOX — draft + ready_for_import entries
# ===========================================================================

with tab_inbox:
    col_list, col_detail = st.columns([1, 2], gap="large")

    with col_list:
        st.subheader("Einträge")
        status_filter = st.selectbox(
            "Filter",
            ["Offen", "draft", "ready_for_import", "Alle"],
            key="inbox_status_filter",
        )
        if status_filter == "Offen":
            entries = cowork_repo.list_entries(status="draft", limit=50) + \
                      cowork_repo.list_entries(status="ready_for_import", limit=50)
            entries.sort(key=lambda e: e.date, reverse=True)
        elif status_filter == "Alle":
            entries = cowork_repo.list_entries(limit=100)
        else:
            entries = cowork_repo.list_entries(status=status_filter, limit=100)

        if not entries:
            st.info("Keine Research-Einträge vorhanden.")
        else:
            for entry in entries:
                status_icon = {
                    "draft": "📝",
                    "ready_for_import": "🟡",
                    "imported": "✅",
                    "failed": "❌",
                }.get(entry.status, "•")
                label = f"{status_icon} {entry.date} — {entry.research_id}"
                if entry.primary_ticker:
                    label += f" [{entry.primary_ticker}]"
                if st.button(label, key=f"entry_{entry.id}", use_container_width=True):
                    st.session_state["cowork_selected_id"] = entry.id

    with col_detail:
        selected_id = st.session_state.get("cowork_selected_id")
        if not selected_id:
            st.info("← Einen Eintrag auswählen.")
        else:
            entry = cowork_repo.get_entry(selected_id)
            if not entry:
                st.warning("Eintrag nicht gefunden.")
            else:
                _render_entry_detail(entry)

# ===========================================================================
# TAB 2: HISTORY — imported entries
# ===========================================================================

with tab_history:
    st.subheader("Importierte Research-Einträge")
    imported_entries = cowork_repo.list_entries(status="imported", limit=100)

    if not imported_entries:
        st.info("Noch keine importierten Einträge.")
    else:
        for entry in imported_entries:
            with st.expander(f"✅ {entry.date} — {entry.research_id}", expanded=False):
                st.caption(f"Modell: {entry.model} · Typ: {entry.type}")
                candidates = cowork_repo.list_suggestions(research_id=entry.research_id)
                accepted = [c for c in candidates if c.status == "accepted"]
                rejected = [c for c in candidates if c.status == "rejected"]
                if accepted:
                    st.markdown("**Hinzugefügt:** " + ", ".join(f"`{c.ticker}`" for c in accepted))
                if rejected:
                    st.markdown("**Übersprungen:** " + ", ".join(f"`{c.ticker}`" for c in rejected))
