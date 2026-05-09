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
from pathlib import Path
from urllib.parse import urlparse

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
    path = Path(entry.file_path)
    if not path.exists():
        # File was archived — try outbox/archive/filename.md
        archive_path = path.parent / "archive" / path.name
        if archive_path.exists():
            path = archive_path
        else:
            return
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        updated = re.sub(
            r"^(status:\s*)(\S+)",
            lambda m: m.group(1) + new_status,
            content,
            count=1,
            flags=re.MULTILINE,
        )
        tmp_path = str(path) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(updated)
        os.replace(tmp_path, str(path))
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
        asset_class=cfg.name,
        investment_type=cfg.investment_type,
        unit=cfg.default_unit,
        notes=notes,
        story=cand.rationale or None,
        added_date=_date.today(),
        in_portfolio=False,
        in_watchlist=True,
        recommendation_source="cowork_research",
        isin=cand.isin,
        extra_data={"exchange": cand.exchange} if cand.exchange else None,
    )


def _render_proposal_panel(entry: ResearchEntry, candidates: list[WatchlistSuggestion]) -> None:
    """Checkbox-based proposal panel — same UX pattern as Search Chat."""
    pending = [c for c in candidates if c.status == "pending"]
    if not pending:
        return

    existing_tickers = {
        (p.ticker.upper(), (p.extra_data or {}).get("exchange", "").upper())
        for p in positions_repo.get_watchlist()
        if p.ticker
    }

    importable = [c for c in pending if (c.ticker.upper(), (c.exchange or "").upper()) not in existing_tickers]
    already_present = [c for c in pending if (c.ticker.upper(), (c.exchange or "").upper()) in existing_tickers]

    st.subheader(f"📋 Watchlist-Vorschläge ({len(pending)})")
    st.caption(
        "KI-Empfehlungen aus dem Research — wähle aus, welche du zur Watchlist hinzufügen möchtest:"
    )

    for cand in already_present:
        conviction_icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(cand.conviction, "⚪")
        st.markdown(
            f"✅ ~~**{cand.ticker}** · {cand.name} · `{cand.exchange}` "
            f"{conviction_icon} {cand.conviction.title()}~~ · *bereits in Watchlist*"
        )

    for cand in importable:
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
            existing_tickers = {
                (p.ticker.upper(), (p.extra_data or {}).get("exchange", "").upper())
                for p in positions_repo.get_watchlist()
                if p.ticker
            }
            added_count = 0
            skipped_count = 0
            error_count = 0
            saved_positions = []  # collect for post-loop storychecker
            for cand in pending:
                is_selected = st.session_state.get(f"cand_check_{entry.id}_{cand.id}", False)
                if not is_selected:
                    cowork_repo.update_suggestion_status(cand.id, "rejected")
                    continue
                dedup_key = (cand.ticker.upper(), (cand.exchange or "").upper())
                if dedup_key in existing_tickers:
                    cowork_repo.update_suggestion_status(cand.id, "accepted")
                    skipped_count += 1
                    continue
                try:
                    saved = positions_repo.add(_build_position(cand))
                    cowork_repo.update_suggestion_status(cand.id, "accepted")
                    added_count += 1
                    if saved.story and saved.id:
                        saved_positions.append(saved)
                except Exception as exc:
                    st.error(f"Fehler bei {cand.ticker}: {exc}")
                    error_count += 1
            # Run storychecker after all positions are added to avoid mid-loop rerenders
            for saved in saved_positions:
                try:
                    from state import get_storychecker_agent
                    with st.spinner(f"Storychecker für {saved.ticker} läuft…"):
                        get_storychecker_agent().start_session(position=saved)
                except Exception:
                    pass
            if error_count == 0:
                cowork_repo.update_status(entry.id, "imported")
                _write_status_to_file(entry, "imported")
                parts = []
                if added_count:
                    parts.append(f"{added_count} Position(en) hinzugefügt")
                if skipped_count:
                    parts.append(f"{skipped_count} bereits in Watchlist")
                st.toast("✅ " + (", ".join(parts) or "Keine Auswahl") + ".", icon="✅")
                st.rerun()
            else:
                st.warning(f"⚠️ {error_count} Fehler — Fehlermeldung oben prüfen. Bitte erneut versuchen.")
    with col_skip:
        if st.button("⏭ Alle überspringen", key=f"skip_all_{entry.id}", use_container_width=True):
            for cand in pending:
                cowork_repo.update_suggestion_status(cand.id, "rejected")
            cowork_repo.update_status(entry.id, "imported")
            st.toast("⏭ Alle Kandidaten übersprungen.")
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

    st.subheader(entry.research_id)

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

    # Warn if primary ticker is missing from candidates (system prompt rule 11)
    if entry.primary_ticker and entry.type == "stock_analysis":
        candidate_tickers = {c.ticker.upper() for c in candidates}
        if entry.primary_ticker.upper() not in candidate_tickers:
            col_warn, col_btn = st.columns([3, 1])
            col_warn.warning(
                f"⚠️ **{entry.primary_ticker}** ({entry.primary_name or 'Primary'}) "
                "ist nicht in den Watchlist-Kandidaten — die KI hat den Hauptkandidaten "
                "weggelassen (gegen Regel 11 des System Prompts)."
            )
            if col_btn.button(
                f"➕ {entry.primary_ticker} hinzufügen",
                key=f"add_primary_{entry.id}",
                use_container_width=True,
            ):
                from core.asset_class_config import get_asset_class_registry
                registry = get_asset_class_registry()
                cfg = registry.require("Aktie")
                primary_pos = Position(
                    ticker=entry.primary_ticker,
                    name=entry.primary_name or entry.primary_ticker,
                    asset_class=cfg.name,
                    investment_type=cfg.investment_type,
                    unit=cfg.default_unit,
                    added_date=_date.today(),
                    in_portfolio=False,
                    in_watchlist=True,
                    recommendation_source="cowork_research",
                    extra_data={"exchange": entry.primary_exchange} if entry.primary_exchange else None,
                )
                dedup_key = (entry.primary_ticker.upper(), (entry.primary_exchange or "").upper())
                existing = {
                    (p.ticker.upper(), (p.extra_data or {}).get("exchange", "").upper())
                    for p in positions_repo.get_watchlist() if p.ticker
                }
                if dedup_key in existing:
                    st.toast(f"✅ {entry.primary_ticker} ist bereits in der Watchlist.")
                else:
                    try:
                        positions_repo.add(primary_pos)
                        st.toast(f"✅ {entry.primary_ticker} zur Watchlist hinzugefügt.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Fehler: {exc}")

    if entry.status == "draft":
        st.info(
            "📝 **Draft** — Research noch unvollständig oder Quellen unsicher. "
            "Die KI hat diese Datei als unfertig markiert. "
            "Bitte das Claude-Projekt um eine vervollständigte Version "
            "oder öffne die Datei und ergänze die fehlenden Informationen."
        )
    elif entry.status == "ready_for_import":
        st.divider()
        _render_proposal_panel(entry, candidates)
    elif entry.status == "imported":
        st.divider()
        if any(c.status == "pending" for c in candidates):
            st.warning("⚠️ Einige Kandidaten konnten nicht hinzugefügt werden — bitte erneut versuchen.")
            _render_proposal_panel(entry, candidates)
        else:
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
            try:
                parsed = urlparse(str(src))
                if parsed.scheme in ("http", "https"):
                    st.markdown(f"- [{src}]({src})")
                else:
                    st.markdown(f"- `{src}` *(ungültiges Protokoll)*")
            except Exception:
                st.markdown(f"- `{src}` *(ungültige URL)*")


# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

col_title, col_scan = st.columns([5, 1])
col_title.title(":material/inbox: Research Inbox")
col_title.caption(
    "KI-generiertes Research aus dem Cowork-Outbox-Ordner. "
    "Dateien mit `ready_for_import` erscheinen hier zur Überprüfung. "
    "Alle Einträge sind **AI Research** — keine Anlageberatung."
)
col_title.caption("⚙️ Setup & System Prompt → **Cowork Setup** in der Navigation")
if col_scan.button("🔄 Jetzt scannen", help="Outbox manuell nach neuen .md-Dateien scannen"):
    watcher = get_cowork_watcher()
    if watcher is not None:
        from core.cowork.importer import CoworkImporter
        from state import get_positions_repo as _gpr
        from config import config as _cfg
        _importer = watcher._importer
        results = _importer.scan_outbox()
        new_count = sum(1 for r in results if r.action not in ("skipped_duplicate", "skipped_already_imported"))
        st.toast(f"🔄 Scan abgeschlossen — {new_count} neue Datei(en) verarbeitet.")
        st.rerun()
    else:
        st.warning("File Watcher ist deaktiviert (`COWORK_WATCH_ENABLED=false`).")

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
