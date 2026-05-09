"""
File watcher for the Cowork Research outbox directory.

Uses watchdog (OS-native events) with a 500ms debounce so half-written files
are not processed prematurely. Ignores files inside .tmp/ subdirectories.

Usage:
    watcher = CoworkWatcher(importer, outbox_path)
    watcher.start()   # spawns background thread, performs initial scan
    watcher.stop()    # clean shutdown
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from typing import Optional

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileMovedEvent
from watchdog.observers import Observer

from core.cowork.importer import CoworkImporter

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 0.5


class _ResearchEventHandler(FileSystemEventHandler):

    def __init__(self, importer: CoworkImporter) -> None:
        self._importer = importer
        self._pending: dict = {}  # path → scheduled_time
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None

    def on_created(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._schedule(event.src_path)

    def on_moved(self, event):
        # Catches atomic rename from .tmp/ into outbox/ (the prescribed write pattern)
        if not event.is_directory:
            self._schedule(event.dest_path)

    def _schedule(self, path: str) -> None:
        p = Path(path)
        # Ignore .tmp directories and non-.md files
        if ".tmp" in p.parts or p.suffix.lower() != ".md":
            return
        # Ignore files inside subdirectories of outbox (archive, .invalid, etc.)
        outbox = Path(self._importer._outbox)
        try:
            rel = p.relative_to(outbox)
        except ValueError:
            return
        if len(rel.parts) > 1:  # inside a subdirectory
            return

        with self._lock:
            self._pending[str(p)] = time.monotonic() + _DEBOUNCE_SECONDS
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(_DEBOUNCE_SECONDS + 0.05, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        now = time.monotonic()
        with self._lock:
            ready = [p for p, t in self._pending.items() if now >= t]
            for p in ready:
                del self._pending[p]
        for path in ready:
            try:
                self._importer.process_file(path)
            except Exception:
                logger.exception("Unhandled error processing %s", path)


class CoworkWatcher:
    """Manages the watchdog Observer and performs the initial outbox scan."""

    def __init__(self, importer: CoworkImporter) -> None:
        self._importer = importer
        self._observer: Optional[Observer] = None
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        # Initial scan (idempotent — skips already-processed research_ids)
        try:
            results = self._importer.scan_outbox()
            if results:
                logger.info("Initial outbox scan: processed %d file(s)", len(results))
        except Exception:
            logger.exception("Error during initial outbox scan")

        outbox = self._importer._outbox
        if not outbox.exists():
            logger.info(
                "Outbox %s does not exist — watcher will not start until directory is created.", outbox
            )
            return

        handler = _ResearchEventHandler(self._importer)
        self._observer = Observer()
        self._observer.schedule(handler, str(outbox), recursive=False)
        self._observer.daemon = True
        self._observer.start()
        logger.info("CoworkWatcher started, watching: %s", outbox)

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        self._started = False
        logger.info("CoworkWatcher stopped.")
