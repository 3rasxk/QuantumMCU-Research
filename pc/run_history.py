#!/usr/bin/env python3
# run_history.py — read-only human-readable summary over the append-only
# ledger at data/run_history.jsonl (pc/shared/run_history.py). Never writes
# to the ledger itself (only pc/run.py does that, see its module docstring)
# -- this is purely a viewer/reporter, with an explicit crash-detection pass
# (a "started" line with no matching terminal line).
#
# ใช้:
#   .venv/bin/python pc/run_history.py
#   .venv/bin/python pc/run_history.py --board uno
#   .venv/bin/python pc/run_history.py --algorithm h_all --since 2026-09-20
#   .venv/bin/python pc/run_history.py --source backfill

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))

from shared import run_history as rh  # noqa: E402


def _parse_date(s):
    """--since/--until take a bare YYYY-MM-DD or a full ISO timestamp."""
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def filter_invocations(grouped, board=None, algorithm=None, phase=None,
                        source=None, since=None, until=None):
    """grouped: {invocation_id: {"started": {...}, "terminal": {...}|None}}
    from rh.group_by_invocation(). Filters are applied against the "started"
    record (board/algorithm/phase/source/timestamp all live there -- the
    terminal record only repeats invocation_id/event/timestamp/outcome
    detail). Returns a list of (invocation_id, slot), oldest first."""
    out = []
    for iid, slot in grouped.items():
        started = slot["started"]
        if started is None:
            continue  # a terminal line with no started line shouldn't happen, skip defensively
        if board and started.get("board") != board:
            continue
        if algorithm and started.get("algorithm") != algorithm:
            continue
        if phase is not None and started.get("phase") != phase:
            continue
        if source and started.get("source") != source:
            continue
        ts = started.get("timestamp_utc", "")
        if since or until:
            try:
                ts_dt = datetime.fromisoformat(ts)
            except ValueError:
                ts_dt = None
            if ts_dt is not None:
                if since and ts_dt < since:
                    continue
                if until and ts_dt > until:
                    continue
        out.append((iid, slot))
    out.sort(key=lambda pair: pair[1]["started"].get("timestamp_utc", ""))
    return out


def format_invocation(iid, slot):
    started = slot["started"]
    terminal = slot["terminal"]
    la_str = "with_la" if started.get("la") else "no_la"
    head = (f"{started.get('timestamp_utc', '?')}  "
            f"{started.get('board', '?')}/{started.get('algorithm', '?')}"
            f"/phase{started.get('phase', '?')}/{la_str}"
            f"  [{started.get('source', 'live')}]")
    if terminal is None:
        return head + "  -- STARTED, NO COMPLETION RECORDED (crash/kill suspected)"
    event = terminal.get("event", "?")
    bits = [f"event={event}"]
    if terminal.get("duration_s") is not None:
        bits.append(f"duration={terminal['duration_s']:.1f}s")
    if terminal.get("returncode") is not None:
        bits.append(f"returncode={terminal['returncode']}")
    counts = terminal.get("point_counts")
    if counts:
        bits.append("counts=" + ",".join(f"{k}={v}" for k, v in sorted(counts.items())))
    if terminal.get("archive_dest"):
        bits.append(f"archived_to={terminal['archive_dest']}")
    if terminal.get("error"):
        bits.append(f"error={terminal['error']!r}")
    return head + "  -- " + "  ".join(bits)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--board", default=None)
    ap.add_argument("--algorithm", default=None)
    ap.add_argument("--phase", type=int, default=None)
    ap.add_argument("--source", choices=("live", "backfill"), default=None)
    ap.add_argument("--since", type=_parse_date, default=None,
                     help="YYYY-MM-DD or full ISO timestamp, inclusive")
    ap.add_argument("--until", type=_parse_date, default=None,
                     help="YYYY-MM-DD or full ISO timestamp, inclusive")
    args = ap.parse_args(argv)

    events = rh.read_events()
    if not events:
        print(f"no ledger found (or empty) at {rh.LEDGER_PATH}")
        return 0

    grouped = rh.group_by_invocation(events)
    filtered = filter_invocations(grouped, board=args.board, algorithm=args.algorithm,
                                   phase=args.phase, source=args.source,
                                   since=args.since, until=args.until)

    print(f"--- run history ({rh.LEDGER_PATH}) ---")
    print(f"{len(filtered)} invocation(s) matching filters "
          f"({len(grouped)} total in ledger)\n")
    for iid, slot in filtered:
        print(format_invocation(iid, slot))

    dangling = [s for iid, s in filtered if s["terminal"] is None]
    print(f"\n{len(dangling)} invocation(s) with no completion recorded "
          f"(within this filtered view)")
    if dangling:
        print("These 'started' with no matching completed/failed/interrupted/dry_run "
              "line -- cross-check against sessions.csv for the same window to confirm "
              "whether the process actually crashed or the ledger write itself failed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
