#!/usr/bin/env python3
# run_history_test.py — mocked-only tests for the persistent run-history
# ledger: pc/shared/run_history.py (the writer, called from pc/run.py) and
# pc/run_history.py (the read-only summarizer). No hardware, no `pio`, no
# real serial port, and -- critically -- no write to the real repo's
# data/run_history.jsonl (every test redirects rh.LEDGER_PATH to a scratch
# file first).
#
# ไม่ใช้ pytest (รูปแบบเดียวกับ pc/run_test.py) รันด้วย:
#   .venv/bin/python pc/run_history_test.py

import contextlib
import csv
import io
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))

import run as run_mod  # noqa: E402
from shared import run_history as rh  # noqa: E402
from shared import paths as sp  # noqa: E402
import run_history as rh_cli  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((name, status))
    print(f"[{status}] {name}  {detail}")


@contextlib.contextmanager
def captured_stdout():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


class RecordingSubprocess:
    def __init__(self, returncode=0):
        self.returncode = returncode
        self.calls = []

    def __call__(self, argv, *args, **kwargs):
        self.calls.append(list(argv) if isinstance(argv, (list, tuple)) else argv)

        class _Result:
            pass
        r = _Result()
        r.returncode = self.returncode
        r.stdout = ""
        r.stderr = ""
        return r


def _redirect(scratch: Path):
    """Redirect the ledger AND paths.py/run.py's REPO_ROOT into one scratch
    tree -- point_counts_by_status() needs sp.REPO_ROOT redirected too, since
    it reads the same memory_wall.csv the sweep scripts would have written."""
    ledger_path = scratch / "data" / "run_history.jsonl"
    saved = (rh.LEDGER_PATH, run_mod.REPO_ROOT, sp.REPO_ROOT)
    rh.LEDGER_PATH = ledger_path
    run_mod.REPO_ROOT = scratch
    sp.REPO_ROOT = scratch
    return saved


def _restore(saved):
    rh.LEDGER_PATH, run_mod.REPO_ROOT, sp.REPO_ROOT = saved


def _write_fake_terminal_records(scratch: Path):
    """Fake memory_wall.csv for uno/h_all/phase2/no_ref, so point_counts_by_status
    has something real to read after a mocked "completed" run."""
    path = sp.memory_wall_csv_path("uno", "h_all", phase=2, ref=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "status"])
        w.writerow(["uno", "h_all", 2, "ok"])
        w.writerow(["uno", "h_all", 3, "ok"])
        w.writerow(["uno", "h_all", 4, "build_overflow"])


def test_dry_run_writes_only_a_dry_run_line(scratch_root: Path):
    scratch = scratch_root / "dry_run"
    scratch.mkdir(parents=True)
    saved = _redirect(scratch)
    try:
        with captured_stdout():
            code = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                                  "--port", "/dev/cu.FAKE", "--dry-run"])
        check("dry-run exits 0", code == 0, code)

        events = rh.read_events()
        check("dry-run writes exactly 2 lines (started + dry_run)", len(events) == 2, len(events))
        check("first line is 'started'", events[0]["event"] == "started", events[0])
        check("first line has dry_run=True", events[0]["dry_run"] is True, events[0]["dry_run"])
        check("second line is 'dry_run'", events[1]["event"] == "dry_run", events[1])
        check("both lines share the same invocation_id",
              events[0]["invocation_id"] == events[1]["invocation_id"])
    finally:
        _restore(saved)


def test_full_run_writes_started_then_completed_with_matching_counts(scratch_root: Path):
    scratch = scratch_root / "full_run"
    scratch.mkdir(parents=True)
    saved = _redirect(scratch)
    rec = RecordingSubprocess(returncode=0)
    saved_subprocess = run_mod.subprocess.run
    run_mod.subprocess.run = rec
    saved_port_checks = (run_mod.port_exists, run_mod.port_matches_board, run_mod.port_holder_pids)
    run_mod.port_exists = lambda port: True
    run_mod.port_matches_board = lambda board, port: True
    run_mod.port_holder_pids = lambda port: []
    try:
        # the mocked subprocess never actually writes memory_wall.csv (it's
        # not a real sweep script) -- write it ourselves, simulating what a
        # real successful sweep would have left behind for run.py to read
        # back afterward
        _write_fake_terminal_records(scratch)

        with captured_stdout():
            code = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                                  "--port", "/dev/cu.FAKE", "--yes"])
        check("full run exits 0", code == 0, code)
        check("the delegated sweep script was actually invoked (mocked)",
              any("uno_sweep.py" in str(c) for c in rec.calls), rec.calls)

        events = rh.read_events()
        check("full run writes exactly 2 lines (started + completed)", len(events) == 2, len(events))
        check("first line is 'started'", events[0]["event"] == "started", events[0])
        check("second line is 'completed'", events[1]["event"] == "completed", events[1])
        check("completed line's point_counts matches the real file (2 ok, 1 build_overflow)",
              events[1]["point_counts"] == {"ok": 2, "build_overflow": 1}, events[1]["point_counts"])
        check("completed line's returncode is 0", events[1]["returncode"] == 0, events[1])
        check("completed line's duration_s is a non-negative number",
              isinstance(events[1]["duration_s"], (int, float)) and events[1]["duration_s"] >= 0,
              events[1]["duration_s"])
    finally:
        run_mod.subprocess.run = saved_subprocess
        (run_mod.port_exists, run_mod.port_matches_board,
         run_mod.port_holder_pids) = saved_port_checks
        _restore(saved)


def test_failure_writes_started_then_failed_with_error(scratch_root: Path):
    scratch = scratch_root / "failure"
    scratch.mkdir(parents=True)
    saved = _redirect(scratch)
    rec = RecordingSubprocess(returncode=1)  # delegated script failed
    saved_subprocess = run_mod.subprocess.run
    run_mod.subprocess.run = rec
    saved_port_checks = (run_mod.port_exists, run_mod.port_matches_board, run_mod.port_holder_pids)
    run_mod.port_exists = lambda port: True
    run_mod.port_matches_board = lambda board, port: True
    run_mod.port_holder_pids = lambda port: []
    try:
        with captured_stdout():
            code = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                                  "--port", "/dev/cu.FAKE", "--yes"])
        check("a failing delegated script's returncode is propagated", code == 1, code)

        events = rh.read_events()
        check("failure writes exactly 2 lines (started + failed)", len(events) == 2, len(events))
        check("second line is 'failed'", events[1]["event"] == "failed", events[1])
        check("failed line's returncode is 1", events[1]["returncode"] == 1, events[1])
        check("failed line has a non-empty error message",
              bool(events[1].get("error")), events[1].get("error"))
    finally:
        run_mod.subprocess.run = saved_subprocess
        (run_mod.port_exists, run_mod.port_matches_board,
         run_mod.port_holder_pids) = saved_port_checks
        _restore(saved)


def test_busy_port_refusal_also_writes_started_then_failed(scratch_root: Path):
    """A refused run (busy port) never reaches the subprocess, but per the
    ledger's own design it must still get a started+failed pair, not silence
    -- see pc/shared/run_history.py's module docstring."""
    scratch = scratch_root / "busy_port"
    scratch.mkdir(parents=True)
    saved = _redirect(scratch)
    saved_port_checks = (run_mod.port_exists, run_mod.port_matches_board, run_mod.port_holder_pids)
    run_mod.port_exists = lambda port: True
    run_mod.port_matches_board = lambda board, port: True
    run_mod.port_holder_pids = lambda port: ["12345"]
    try:
        with captured_stdout():
            code = run_mod.main(["--board", "uno", "--algorithm", "h_all", "--phase", "2",
                                  "--port", "/dev/cu.FAKE", "--yes"])
        check("busy-port run is refused (non-zero exit)", code != 0, code)

        events = rh.read_events()
        check("busy-port refusal writes exactly 2 lines (started + failed)",
              len(events) == 2, len(events))
        check("second line is 'failed'", events[1]["event"] == "failed", events[1])
        check("failed line's error mentions the port refusal",
              "port" in (events[1].get("error") or "").lower(), events[1].get("error"))
    finally:
        (run_mod.port_exists, run_mod.port_matches_board,
         run_mod.port_holder_pids) = saved_port_checks
        _restore(saved)


def test_simulated_kill_leaves_only_started_line_and_reader_flags_it(scratch_root: Path):
    """Simulates the run.py PROCESS itself dying mid-run (SIGKILL, host
    crash, or an exception escaping every handler) -- as opposed to a Ctrl+C
    that run.py's own KeyboardInterrupt handler catches and turns into a
    clean 'interrupted' terminal line (see test above via the try/except in
    main()). A real kill signal can't be delivered mid-test without actually
    killing the test process, so this drives pc/shared/run_history.py
    directly: call start_invocation() and deliberately never call
    finish_invocation() -- functionally identical to what the ledger sees
    when a real process vanishes between the two calls."""
    scratch = scratch_root / "simulated_kill"
    scratch.mkdir(parents=True)
    saved = _redirect(scratch)
    try:
        inv = rh.start_invocation(["pc/run.py", "--board", "esp8266", "--algorithm", "grover",
                                    "--phase", "2", "--port", "/dev/cu.FAKE"],
                                   "esp8266", "grover", 2, ref=False, fresh=False, dry_run=False)
        # (no finish_invocation call -- the simulated kill)

        events = rh.read_events()
        check("simulated kill: exactly 1 line in the ledger (the started line)",
              len(events) == 1, len(events))
        check("simulated kill: that line is 'started'", events[0]["event"] == "started")

        dangling = rh.find_dangling_started(events)
        check("find_dangling_started: flags exactly this one invocation",
              len(dangling) == 1 and dangling[0]["invocation_id"] == inv.invocation_id,
              dangling)

        with captured_stdout() as out:
            rh_cli.main(["--board", "esp8266"])
        text = out.getvalue()
        check("pc/run_history.py's CLI summary flags it as 'no completion recorded'",
              "no completion recorded" in text or "NO COMPLETION RECORDED" in text, text)
    finally:
        _restore(saved)


def test_reader_filters_by_board_algorithm_and_source(scratch_root: Path):
    scratch = scratch_root / "filters"
    scratch.mkdir(parents=True)
    saved = _redirect(scratch)
    try:
        inv1 = rh.start_invocation(["x"], "uno", "h_all", 2, ref=False, fresh=False, dry_run=False)
        rh.finish_invocation(inv1, "dry_run")
        inv2 = rh.start_invocation(["x"], "esp32", "qft", 2, ref=False, fresh=False, dry_run=False)
        rh.finish_invocation(inv2, "dry_run")

        # a "backfill" entry, written directly (this session does not run the
        # real backfill script against a scratch dir -- that's exercised
        # separately, see run_log.md / the backfill script's own dry-run)
        rh._append({
            "schema_version": rh.SCHEMA_VERSION, "invocation_id": "backfill-1",
            "event": "started", "timestamp_utc": "2026-09-20T00:00:00+00:00",
            "argv": [], "board": "uno", "algorithm": "bell_ghz", "phase": 2,
            "ref": False, "fresh": False, "dry_run": False,
            "git_commit": "", "git_tag": "", "host": "", "source": "backfill",
        })
        rh._append({
            "schema_version": rh.SCHEMA_VERSION, "invocation_id": "backfill-1",
            "event": "completed", "timestamp_utc": "2026-09-20T00:01:00+00:00",
            "duration_s": 60.0, "returncode": 0, "point_counts": {"ok": 6},
            "archive_dest": None, "error": None, "source": "backfill",
        })

        events = rh.read_events()
        grouped = rh.group_by_invocation(events)
        check("3 invocations total in the ledger", len(grouped) == 3, len(grouped))

        uno_only = rh_cli.filter_invocations(grouped, board="uno")
        check("filter by board=uno matches 2 of 3", len(uno_only) == 2, len(uno_only))

        live_only = rh_cli.filter_invocations(grouped, source="live")
        check("filter by source=live matches 2 of 3", len(live_only) == 2, len(live_only))

        backfill_only = rh_cli.filter_invocations(grouped, source="backfill")
        check("filter by source=backfill matches exactly the backfilled one",
              len(backfill_only) == 1 and backfill_only[0][0] == "backfill-1", backfill_only)
    finally:
        _restore(saved)


def main():
    scratch_root = Path(tempfile.mkdtemp(prefix="run_history_test_"))
    real_ledger = REPO_ROOT / "data" / "run_history.jsonl"
    real_ledger_before = real_ledger.read_bytes() if real_ledger.exists() else None
    try:
        test_dry_run_writes_only_a_dry_run_line(scratch_root)
        test_full_run_writes_started_then_completed_with_matching_counts(scratch_root)
        test_failure_writes_started_then_failed_with_error(scratch_root)
        test_busy_port_refusal_also_writes_started_then_failed(scratch_root)
        test_simulated_kill_leaves_only_started_line_and_reader_flags_it(scratch_root)
        test_reader_filters_by_board_algorithm_and_source(scratch_root)
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)

    check("no test run touched the real data/run_history.jsonl ledger",
          (real_ledger.read_bytes() if real_ledger.exists() else None) == real_ledger_before)

    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\n{len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
