#!/usr/bin/env python3
# backfill_run_history.py — one-time (well, re-runnable) reconstruction of
# run-history ledger entries (pc/shared/run_history.py) for every collection
# run that happened BEFORE the ledger existed (2026-09-22). Source of truth:
# the real, committed sessions.csv files under data/raw/ -- each row is one
# completed sweep-script invocation, with exact start/end timestamps,
# git_commit, and point/status counts already recorded by telemetry.py at
# the time. Cross-referenced with that session's own env/<session_id>.json
# for the serial port actually used (not recorded in sessions.csv itself).
#
# Every entry this script writes gets "source": "backfill" (see
# pc/shared/run_history.py's schema) -- never "live", and never overwrites a
# "live" entry. Idempotent: re-running skips any session_id it has already
# backfilled (checked against the ledger's own invocation_id, which this
# script sets to f"backfill-{session_id}").
#
# IMPORTANT — these predate pc/run.py (introduced 2026-09-21, one full day
# after every one of these sessions ran, see run_log.md and
# `git log --follow -- pc/run.py`): every one of them was a direct
# invocation of pc/phase2_sweep/uno_sweep.py, not pc/run.py. The
# reconstructed argv reflects that (the real script, port, and circuit --
# all recorded); it does NOT include --n-start/--n-max, which were never
# recorded anywhere before telemetry.py existed and cannot be honestly
# reconstructed -- guessing them would misrepresent history as more
# precisely known than it is.
#
# ใช้:
#   .venv/bin/python pc/backfill_run_history.py            # write
#   .venv/bin/python pc/backfill_run_history.py --dry-run   # preview only

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))

from shared import run_history as rh  # noqa: E402

SWEEP_SCRIPT_BY_PHASE_BOARD = {
    (2, "uno"): "pc/phase2_sweep/uno_sweep.py",
    (2, "esp8266"): "pc/phase2_sweep/esp8266_sweep.py",
    (2, "esp32"): "pc/phase2_sweep/esp32_sweep.py",
    (3, "uno"): "pc/phase3_offload/sweep.py",
    (3, "esp8266"): "pc/phase3_offload/sweep.py",
    (3, "esp32"): "pc/phase3_offload/sweep.py",
}

STATUS_COUNT_COLUMNS = {
    "n_points_ok": "ok",
    "n_points_failed": "failed",
    "n_points_skipped_resume": "skipped_resume",
    "n_points_skipped_known_wall": "skipped_known_wall",
    "n_points_skipped_compute_infeasible": "skipped_compute_infeasible",
    "n_points_skipped_sim_cost_infeasible": "skipped_sim_cost_infeasible",
}


def _tag_for_commit(commit: str) -> str:
    if not commit:
        return ""
    try:
        out = subprocess.run(["git", "describe", "--tags", "--always", commit],
                              cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def _la_bucket_from_path(sessions_csv_path: Path) -> bool:
    for part in sessions_csv_path.parts:
        if part == "with_la":
            return True
        if part == "no_la":
            return False
    raise ValueError(f"{sessions_csv_path}: no no_la/with_la segment in path")


def load_env_json(env_json_path: str):
    if not env_json_path:
        return {}
    path = Path(env_json_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def build_backfill_record_pair(row: dict, sessions_csv_path: Path):
    """One sessions.csv row -> (started_record, terminal_record), both with
    the same invocation_id (f"backfill-{session_id}") and source=backfill."""
    session_id = row["session_id"]
    phase = int(row["phase"])
    board = row["board"]
    circuit = row["circuits"].split(";")[0]  # every real row here is single-circuit
    la = _la_bucket_from_path(sessions_csv_path)
    env = load_env_json(row.get("env_json_path", ""))
    port = env.get("serial_port", "UNKNOWN -- not recorded pre-telemetry")
    git_commit = row.get("git_commit", "") or env.get("git_commit", "")
    git_tag = _tag_for_commit(git_commit)

    script = SWEEP_SCRIPT_BY_PHASE_BOARD.get((phase, board), "UNKNOWN")
    argv = [script, "--port", port, "--circuits", circuit]

    invocation_id = f"backfill-{session_id}"
    started = {
        "schema_version": rh.SCHEMA_VERSION,
        "invocation_id": invocation_id,
        "event": "started",
        "timestamp_utc": row["start_utc"],
        "argv": argv,
        "board": board, "algorithm": circuit, "phase": phase,
        "la": la, "fresh": False, "dry_run": False,
        "git_commit": git_commit, "git_tag": git_tag,
        "host": "",
        "source": "backfill",
        "backfill_note": ("predates pc/run.py (introduced 2026-09-21); direct "
                           "invocation of the sweep script, not pc/run.py -- "
                           "--n-start/--n-max were never recorded and are NOT "
                           "guessed here; reconstructed from "
                           f"{sessions_csv_path.relative_to(REPO_ROOT)} + "
                           f"{row.get('env_json_path', '(no env json)')}"),
    }

    counts = {}
    for col, status in STATUS_COUNT_COLUMNS.items():
        n = int(row.get(col) or 0)
        if n:
            counts[status] = n

    try:
        duration_s = float(row["wall_clock_s"])
    except (KeyError, ValueError):
        duration_s = None

    terminal = {
        "schema_version": rh.SCHEMA_VERSION,
        "invocation_id": invocation_id,
        "event": "completed",  # every backfilled session here ran to its own
        # natural end (wall found, or all n exhausted) -- none are known to
        # have crashed (a crash would have left an orphan raw.csv row,
        # purged by resume.purge_orphan_rows on the NEXT session, which none
        # of these five circuits ever had -- see their own memory_wall.csv)
        "timestamp_utc": row["end_utc"],
        "duration_s": duration_s,
        "returncode": 0,
        "point_counts": counts or None,
        "archive_dest": None,
        "error": None,
        "source": "backfill",
    }
    return started, terminal


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                     help="print what would be written, write nothing")
    args = ap.parse_args()

    sessions_files = sorted(REPO_ROOT.glob("data/raw/phase*/*/*/no_la/sessions.csv")) + \
        sorted(REPO_ROOT.glob("data/raw/phase*/*/*/with_la/sessions.csv"))
    if not sessions_files:
        print("no sessions.csv files found under data/raw/ -- nothing to backfill")
        return 0

    already = {ev["invocation_id"] for ev in rh.read_events()
               if ev.get("source") == "backfill"}

    written = 0
    skipped = 0
    for path in sessions_files:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                invocation_id = f"backfill-{row['session_id']}"
                if invocation_id in already:
                    skipped += 1
                    continue
                started, terminal = build_backfill_record_pair(row, path)
                print(f"{'[dry-run] ' if args.dry_run else ''}backfill: "
                      f"{started['board']}/{started['algorithm']}/phase{started['phase']}/"
                      f"{'with_la' if started['la'] else 'no_la'}  "
                      f"{started['timestamp_utc']} -> {terminal['timestamp_utc']}  "
                      f"counts={terminal['point_counts']}")
                if not args.dry_run:
                    rh._append(started)
                    rh._append(terminal)
                written += 1

    print(f"\n{written} session(s) {'would be ' if args.dry_run else ''}backfilled, "
          f"{skipped} already present (skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
