"""
Cowork Research Importer.

Handles the full lifecycle of a research file:
  parse → validate → store ResearchEntry → process candidates based on status

Status routing:
  draft            → store as ResearchEntry only, no candidate actions
  ready_for_import → full import: dedup, add/queue/skip candidates
  imported         → skip entirely (already processed)
  failed           → store with failure_reason, no candidate actions

Filesystem:
  On success: move file to <outbox>/archive/
  On parse failure: move file to <outbox>/.invalid/
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.cowork.parser import ParseError, ParsedResearch, parse_research_file
from core.storage.cowork import CoworkRepository, ResearchEntry, WatchlistSuggestion

logger = logging.getLogger(__name__)


class ImportResult:
    def __init__(
        self,
        research_id: str,
        success: bool,
        action: str,
        failure_reason: Optional[str] = None,
        candidates_added: int = 0,
        candidates_queued: int = 0,
        candidates_skipped: int = 0,
        candidates_deduped: int = 0,
        candidates_review: int = 0,
    ):
        self.research_id = research_id
        self.success = success
        self.action = action
        self.failure_reason = failure_reason
        self.candidates_added = candidates_added
        self.candidates_queued = candidates_queued
        self.candidates_skipped = candidates_skipped
        self.candidates_deduped = candidates_deduped
        self.candidates_review = candidates_review

    def __repr__(self) -> str:
        return (
            f"ImportResult(id={self.research_id!r}, success={self.success}, "
            f"action={self.action!r}, added={self.candidates_added}, "
            f"queued={self.candidates_queued})"
        )


class CoworkImporter:
    """
    Stateless importer — call process_file() per file.
    Requires a CoworkRepository and a PositionsRepository for watchlist dedup.
    """

    def __init__(
        self,
        cowork_repo: CoworkRepository,
        positions_repo,  # PositionsRepository — avoid circular import
        outbox_path: str,
        archive_subfolder: str = "archive",
        auto_import_ready: bool = True,  # kept for backward compat, no longer used
    ):
        self._cowork = cowork_repo
        self._positions = positions_repo
        self._outbox = Path(outbox_path).expanduser()
        self._archive_subfolder = archive_subfolder

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    _MAX_FILE_BYTES = 1 * 1024 * 1024  # 1 MB

    def process_file(self, file_path: str) -> ImportResult:
        """Parse, store, and process a single .md research file."""
        path = Path(file_path)
        logger.info("Processing research file: %s", path.name)

        # Reject oversized files before reading into RAM
        try:
            file_size = path.stat().st_size
        except OSError as exc:
            return self._handle_parse_failure(path, f"Cannot stat file: {exc}")
        if file_size > self._MAX_FILE_BYTES:
            return self._handle_parse_failure(
                path,
                f"File too large ({file_size:,} bytes > {self._MAX_FILE_BYTES:,} bytes limit)",
            )

        # Idempotency: check if already processed by research_id (need to parse first)
        # We handle this after parse below.

        # Parse
        try:
            parsed = parse_research_file(str(path))
        except ParseError as exc:
            logger.warning("Parse error in %s: %s", path.name, exc)
            return self._handle_parse_failure(path, str(exc))

        # Idempotency check — skip if already stored with candidates or fully imported
        existing = self._cowork.get_by_research_id(parsed.research_id)
        if existing is not None:
            if existing.status in ("imported", "ready_for_import"):
                # ready_for_import: candidates already stored, UI awaits confirmation
                # imported: fully done — either way, don't re-process
                logger.info("Already stored (%s), skipping: %s", existing.status, parsed.research_id)
                return ImportResult(
                    research_id=parsed.research_id,
                    success=True,
                    action="skipped_duplicate",
                )
            # Status may have changed (e.g. draft → ready_for_import): sync DB and re-process
            if existing.status != parsed.status:
                self._cowork.update_status_by_research_id(parsed.research_id, parsed.status)
            entry = existing
        elif parsed.status == "imported":
            logger.info("File status=imported, skipping: %s", parsed.research_id)
            return ImportResult(
                research_id=parsed.research_id,
                success=True,
                action="skipped_already_imported",
            )
        else:
            entry = None  # will be created below

        if entry is None:
            entry = self._cowork.create_entry(
                research_id=parsed.research_id,
                type=parsed.type,
                date=parsed.date,
                model=parsed.model,
                status=parsed.status,
                primary_ticker=parsed.primary.ticker if parsed.primary else None,
                primary_name=parsed.primary.name if parsed.primary else None,
                primary_exchange=parsed.primary.exchange if parsed.primary else None,
                primary_sentiment=parsed.primary.sentiment if parsed.primary else None,
                primary_confidence=parsed.primary.confidence if parsed.primary else None,
                body_markdown=parsed.body_markdown,
                sources=parsed.sources,
                disclaimer=parsed.disclaimer,
                file_path=str(path),
            )

        if parsed.status == "failed":
            logger.info("Research %s has status=failed, stored without processing.", parsed.research_id)
            return ImportResult(
                research_id=parsed.research_id,
                success=True,
                action="stored_failed",
            )

        if parsed.status == "draft":
            logger.info("Research %s is draft, stored for display only.", parsed.research_id)
            return ImportResult(
                research_id=parsed.research_id,
                success=True,
                action="stored_draft",
            )

        # ready_for_import → store candidates as pending, archive file, wait for UI confirmation
        result = self._process_candidates(entry, parsed)
        self._move_to_archive(path)
        logger.info(
            "Stored pending review %s: pending_add=%d pending_watch=%d skipped=%d deduped=%d",
            parsed.research_id,
            result.candidates_added,
            result.candidates_queued,
            result.candidates_skipped,
            result.candidates_deduped,
        )
        return result

    def scan_outbox(self) -> list[ImportResult]:
        """Full scan of outbox directory for .md files not yet in DB."""
        if not self._outbox.exists():
            logger.info("Outbox path %s does not exist, skipping scan.", self._outbox)
            return []
        results = []
        archive_path = self._outbox / self._archive_subfolder
        invalid_path = self._outbox / ".invalid"
        for md_file in sorted(self._outbox.glob("*.md")):
            # Skip files inside subdirectories (handled separately)
            if md_file.parent != self._outbox:
                continue
            results.append(self.process_file(str(md_file)))
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _process_candidates(self, entry: ResearchEntry, parsed: ParsedResearch) -> ImportResult:
        added = queued = skipped = deduped = review = 0
        existing_watchlist = self._get_existing_watchlist_tickers()

        for cand in parsed.watchlist_candidates:
            dedup_key = (cand.ticker.upper(), cand.exchange.upper())
            if dedup_key in existing_watchlist:
                logger.debug("Dedup: %s already in watchlist", cand.ticker)
                deduped += 1
                continue

            # Store suggestion regardless of action (for audit trail)
            suggestion = self._cowork.create_suggestion(
                research_id=parsed.research_id,
                ticker=cand.ticker,
                exchange=cand.exchange,
                name=cand.name,
                isin=cand.isin,
                category=cand.category,
                rationale=cand.rationale,
                conviction=cand.conviction,
                suggested_action=cand.suggested_action,
                price_at_research=cand.price_at_research,
                currency=cand.currency,
                target_price=cand.target_price,
                triggers=cand.triggers,
            )

            if cand.suggested_action == "add":
                # Add directly to watchlist — status pending (user must confirm via UI)
                self._cowork.update_suggestion_status(suggestion.id, "pending")
                added += 1
            elif cand.suggested_action == "watch":
                self._cowork.update_suggestion_status(suggestion.id, "pending")
                queued += 1
            else:  # skip
                self._cowork.update_suggestion_status(suggestion.id, "rejected")
                skipped += 1

        return ImportResult(
            research_id=parsed.research_id,
            success=True,
            action="stored_pending_review",
            candidates_added=added,
            candidates_queued=queued,
            candidates_skipped=skipped,
            candidates_deduped=deduped,
            candidates_review=review,
        )

    def _get_existing_watchlist_tickers(self) -> set:
        try:
            positions = self._positions.get_watchlist()
            return {
                (p.ticker.upper(), (p.extra_data or {}).get("exchange", "").upper())
                for p in positions
                if p.ticker
            }
        except Exception:
            logger.warning("Could not load watchlist for dedup check", exc_info=True)
            return set()

    def _handle_parse_failure(self, path: Path, reason: str) -> ImportResult:
        invalid_dir = self._outbox / ".invalid"
        try:
            invalid_dir.mkdir(parents=True, exist_ok=True)
            dest = invalid_dir / path.name
            # atomic rename (same filesystem)
            path.rename(dest)
        except OSError as exc:
            logger.error("Could not move invalid file %s to .invalid/: %s", path.name, exc)

        # Try to extract research_id from filename for the DB record
        research_id = path.stem  # fallback: use filename without extension
        try:
            self._cowork.create_entry(
                research_id=research_id,
                type="stock_analysis",
                date=datetime.now(timezone.utc).date(),
                model="unknown",
                status="failed",
                body_markdown="",
                sources=[],
                disclaimer="",
                file_path=str(path),
                failure_reason=reason,
            )
        except Exception as exc:
            logger.error("Could not store failed ResearchEntry for %s: %s", path.name, exc)

        return ImportResult(
            research_id=research_id,
            success=False,
            action="parse_failed",
            failure_reason=reason,
        )

    def _move_to_archive(self, path: Path) -> None:
        archive_dir = self._outbox / self._archive_subfolder
        try:
            archive_dir.mkdir(parents=True, exist_ok=True)
            dest = archive_dir / path.name
            # atomic on same filesystem; falls back to copy+delete across filesystems
            os.replace(str(path), str(dest))
        except OSError as exc:
            logger.error("Could not archive %s: %s", path.name, exc)
