"""Book every LLM call into the shared ops-core run log.

Four side projects on this machine talk to the same three providers, and
until 2026-09-22 nobody kept the books: each project knew its own token
counts, none knew what the household spent. ops-core (in the
`heimnetzwerk` repo) defines a `metric` event for exactly this, and the
Home-Ops agent reads the log back and shows the running month per
provider, against a budget. This module is what makes this project
appear there.

Two rules carried over from ops-core, both non-negotiable:

* **A call must never fail because the log is unwritable.** Every write
  error is swallowed and noted on stderr. Nothing in here raises.
* **The contract is the file, not the code.** One NDJSON line per event,
  one file per day under `~/.ops-core/runs/`, fields as in the schema.
  Deliberately a copy of the writer rather than an import: no call in
  this app may depend on ops-core being installed.

Privacy: a booking carries provider, model, the agent that asked, token
counts, cost and duration -- no positions, no names, no prompt text. It
stays on this machine, in the same house as the app itself.

The amount is the list price at booking time. For OpenRouter the real,
billed amount only arrives later, when the cost sync asks
`/generation`; ``book_llm_cost_correction`` then books the difference,
so the household sum settles on what was actually billed without ever
counting the call twice.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT = "wealth_management"
METRIC_CALL = "llm_call"
METRIC_CORRECTION = "llm_call_cost"

# Crockford base32, as in the ULID spec and in ops_core.runlog.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _new_run_id() -> str:
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    chars = []
    for _ in range(26):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def runs_dir() -> Optional[Path]:
    """Where ops-core keeps its run log, or None if there is none.

    A missing directory means ops-core is not set up here (a fresh
    checkout, CI, the dev container) — then nothing is booked and nothing
    is created. ``OPS_CORE_HOME`` moves it, as it does for ops-core
    itself; the test suite points it at a tmp dir so no test ever writes
    into the real log.
    """
    home = os.environ.get("OPS_CORE_HOME")
    base = Path(home) if home else Path.home() / ".ops-core"
    runs = base / "runs"
    return runs if base.is_dir() else None


def _job(source: str) -> str:
    """Which job this call belongs to.

    Inside an `ops run` the runner passes ``OPS_JOB``. The app itself is a
    service, not a run: a call from a page is "interaktiv", one from the
    internal scheduler is "scheduler". Both get their own ULID, so
    `ops runs` does not mistake them for runs — it only folds events that
    have a ``run_start``.
    """
    if os.environ.get("OPS_JOB"):
        return os.environ["OPS_JOB"]
    return "interaktiv" if source == "manual" else "scheduler"


def _write(payload: dict, source: str) -> Optional[dict]:
    runs = runs_dir()
    if runs is None:
        return None
    ts = datetime.now().astimezone().isoformat(timespec="milliseconds")
    event = {
        "ts": ts,
        "project": PROJECT,
        "run_id": os.environ.get("OPS_RUN_ID") or _new_run_id(),
        "job": _job(source),
        "kind": "metric",
        "level": "info",
        "payload": payload,
    }
    try:
        line = (json.dumps(event, ensure_ascii=False, separators=(",", ":"),
                           default=str) + "\n").encode("utf-8")
        path = runs / f"{ts[:10]}.ndjson"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except Exception as exc:  # noqa: BLE001 — deliberately everything
        try:
            print(f"wealth_management: LLM call not booked "
                  f"({type(exc).__name__}: {exc})", file=sys.stderr, flush=True)
        except Exception:  # noqa: BLE001
            pass
    return event


def book_llm_call(
    *,
    provider: str,
    model: str,
    purpose: str,
    tokens_in: Optional[int],
    tokens_out: Optional[int],
    cost_usd: Optional[float],
    duration_ms: Optional[int] = None,
    source: str = "manual",
    generation_id: Optional[str] = None,
) -> Optional[dict]:
    """Book one finished call. ``cost_usd`` is the list price."""
    return _write({
        "metric": METRIC_CALL,
        "provider": provider,
        "model": model,
        "purpose": purpose,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "cost_source": "liste",
        "duration_ms": duration_ms,
        **({"generation_id": generation_id} if generation_id else {}),
    }, source)


def book_llm_cost_correction(
    *,
    provider: str,
    model: str,
    purpose: str,
    delta_usd: float,
    generation_id: Optional[str] = None,
    source: str = "scheduled",
) -> Optional[dict]:
    """Book the difference between list price and what was actually billed.

    A separate metric on purpose: the reader adds the amount to the month
    but must not count it as another call. The delta may be negative —
    OpenRouter often bills less than the list price.
    """
    return _write({
        "metric": METRIC_CORRECTION,
        "provider": provider,
        "model": model,
        "purpose": purpose,
        "cost_usd": round(delta_usd, 8),
        "cost_source": "gemessen",
        **({"generation_id": generation_id} if generation_id else {}),
    }, source)
