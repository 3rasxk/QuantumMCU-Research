# run_history.py — the persistent, append-only, invocation-level audit trail
# for pc/run.py (2026-09-22, see run_log.md "persistent run history ledger").
#
# Why this exists, and why it's not sessions.csv: sessions.csv (see
# telemetry.py) already records one row per COMPLETED sweep-script session,
# per (board, circuit, phase, ref) directory -- but it is written by the
# DELEGATED sweep script, only for a session that ran long enough to reach
# its own `with session:` block, and it's scattered across dozens of
# directories with no single place to ask "every command anyone has run,
# ever, across every board." This ledger fixes both gaps:
#   - written by pc/run.py itself, BEFORE delegating -- captures a dry-run,
#     a validation refusal (unknown board, unsupported --la, busy port), and
#     an interrupted (Ctrl+C) run, none of which ever reach a delegated
#     script's own SessionRecorder.
#   - one file, invocation-level, phase/board/algorithm-agnostic -- an
#     operator (or a later Claude Code session) can answer "what has been
#     run so far" without knowing which of dozens of sessions.csv files to
#     open.
#
# Design decision -- single file, not per-board (data/run_history.jsonl, not
# data/run_history/<board>.jsonl): the whole point is "one place for a full
# audit trail" (see the task this was written for) -- an operator asking "did
# anything run today" should not have to open 3 files and merge them by
# timestamp. A single small JSONL file has no real cost here: see
# _SIZE_ESTIMATE_NOTE below for the arithmetic. Kept outside data/raw/ and
# the --fresh archive tree on purpose -- it is not raw measurement data and
# no --fresh run should ever move or touch it (pc/run.py's own archive-source
# discovery has no reference to this module at all).
#
# Format: one JSON object per line (JSONL), append-only, UTF-8, never
# rewritten or deleted by any script -- exactly one write per event, always
# via open(..., "a") + a single f.write(json.dumps(...) + "\n") + flush.
# Every invocation gets exactly one "started" line (written by
# start_invocation(), before any validation/preflight/confirmation/subprocess
# call) and, IF the process didn't crash/get SIGKILLed, exactly one terminal
# line sharing the same invocation_id: "completed", "failed", "interrupted",
# or "dry_run". A "started" line with no matching terminal line means the
# process died without one -- crash detection, see find_dangling_started()
# and pc/run_history.py's summary output.
#
# _SIZE_ESTIMATE_NOTE: one line is ~400-700 bytes (argv + a few fields; a
# "completed" line with point_counts adds maybe 150 bytes more). Even at an
# optimistic 20 invocations/day sustained for the remaining months of this
# project's data collection (a few hundred points across 3 boards x 6
# circuits x 2 phases x 2 la-buckets, each needing at most a handful of
# invocations -- resume means re-running the same command doesn't multiply
# this), total invocation count for the rest of the project is expected in
# the low hundreds, not thousands -- call it 500 lines x 700 bytes ~= 350 KB
# worst case. Trivial for git.

import json
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LEDGER_PATH = REPO_ROOT / "data" / "run_history.jsonl"

SCHEMA_VERSION = 1

EVENTS = ("started", "completed", "failed", "interrupted", "dry_run")


def _git_commit_and_tag():
    """Read-only, best-effort -- mirrors pc/run.py's own git_state()/
    git_commit_hash() but kept independent (this module must not import
    pc/run.py, the dependency runs the other way)."""
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                                 capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        commit = ""
    try:
        tag = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"],
                              cwd=REPO_ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        tag = ""
    return commit, tag


def _append(record: dict):
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
        f.flush()


class Invocation:
    """Returned by start_invocation(); pass to finish_invocation() to write
    the matching terminal line. Holds nothing but what's needed to compute
    duration_s and to stamp the terminal line with the same invocation_id --
    deliberately not a context manager (pc/run.py's own control flow has
    several early-return points that each need a different terminal event,
    a plain function call at each one is clearer than forcing them all
    through one __exit__)."""

    def __init__(self, invocation_id: str, start_monotonic: float):
        self.invocation_id = invocation_id
        self.start_monotonic = start_monotonic


def start_invocation(argv, board, algorithm, phase, ref=False, fresh=False, dry_run=False) -> Invocation:
    """Writes the "started" line immediately -- call this as the very first
    thing in pc/run.py's main(), before argument validation, so a refused
    run (unknown board, unsupported --la, busy port) still gets a "started"
    line followed by its own "failed" terminal line, not silence."""
    invocation_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}-{uuid.uuid4().hex[:8]}"
    commit, tag = _git_commit_and_tag()
    _append({
        "schema_version": SCHEMA_VERSION,
        "invocation_id": invocation_id,
        "event": "started",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "argv": list(argv),
        "board": board, "algorithm": algorithm, "phase": phase,
        "ref": bool(ref), "fresh": bool(fresh), "dry_run": bool(dry_run),
        "git_commit": commit, "git_tag": tag,
        "host": platform.node() or "",
        "source": "live",
    })
    return Invocation(invocation_id, time.monotonic())


def finish_invocation(inv: Invocation, event: str, *, returncode=None,
                       point_counts=None, archive_dest=None, error=None):
    """Writes the terminal line for `inv`. `event` must be one of completed/
    failed/interrupted/dry_run (never "started" again -- that would just be
    a second started line for the same invocation, not a terminal one)."""
    if event not in EVENTS or event == "started":
        raise ValueError(f"finish_invocation: event must be one of "
                          f"{[e for e in EVENTS if e != 'started']}, got {event!r}")
    _append({
        "schema_version": SCHEMA_VERSION,
        "invocation_id": inv.invocation_id,
        "event": event,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "duration_s": round(time.monotonic() - inv.start_monotonic, 3),
        "returncode": returncode,
        "point_counts": point_counts,
        "archive_dest": str(archive_dest) if archive_dest else None,
        "error": error,
        "source": "live",
    })


def read_events():
    """Every line, parsed, in file order. Malformed lines are skipped with a
    stderr warning rather than raising -- a reader must never crash the
    ledger it's trying to summarize."""
    if not LEDGER_PATH.exists():
        return []
    out = []
    with open(LEDGER_PATH, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"run_history: skipping malformed line {lineno} in {LEDGER_PATH}: {e}",
                      file=sys.stderr)
    return out


def group_by_invocation(events):
    """{invocation_id: {"started": {...}, "terminal": {...} or None}}"""
    out = {}
    for ev in events:
        iid = ev.get("invocation_id")
        if iid is None:
            continue
        slot = out.setdefault(iid, {"started": None, "terminal": None})
        if ev.get("event") == "started":
            slot["started"] = ev
        else:
            slot["terminal"] = ev
    return out


def find_dangling_started(events):
    """Invocation records with a "started" line and no terminal line --
    the process never wrote completed/failed/interrupted/dry_run, meaning it
    crashed, was SIGKILLed, or the host itself died mid-run. Returns a list
    of the "started" event dicts, oldest first."""
    grouped = group_by_invocation(events)
    dangling = [slot["started"] for slot in grouped.values()
                if slot["started"] is not None and slot["terminal"] is None]
    return sorted(dangling, key=lambda e: e.get("timestamp_utc", ""))
