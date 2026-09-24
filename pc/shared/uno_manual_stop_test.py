#!/usr/bin/env python3
# uno_manual_stop_test.py — self-contained tests for the 2026-09-22 standing
# decision that replaced Phase 2's timeout ceiling (pc/shared/timing_model.py's
# CEILING_S) with: no automatic per-point give-up, live ETA/progress printing,
# and an operator-controlled manual stop (Ctrl+C during read_serial_trials)
# whose partial reps are kept as a RESUMABLE point (status=stopped_by_operator,
# rep count embedded in the status string -- no new column/schema change) --
# append the remaining reps on the next invocation instead of the usual
# discard-and-redo-from-scratch orphan handling. See pc/shared/resume.py's
# module comment and pc/phase2_sweep/uno_sweep.py for the full design.
#
# Covers, as implemented in uno_sweep.py (esp8266_sweep.py/esp32_sweep.py
# mirror this exactly, same pattern, see their own test files for lighter
# coverage of the identical logic):
#   - timing_model: the ceiling no longer caps anything for Phase 2
#   - read_serial_trials itself: a KeyboardInterrupt raised inside the read
#     loop is caught THERE (not left to propagate) so partial rows aren't lost
#   - a mocked manual stop mid-point: partial rows written to raw.csv
#     (relabeled rep 0..N-1), memory_wall.csv gets a resumable
#     stopped_by_operator(reps_completed=N) row, the whole run stops
#     (OperatorStoppedError -> exit 130), never abandoning collected data
#   - resuming that same point: NOT skipped, remaining reps appended
#     (relabeled continuing from N), reaching status=ok once complete
#   - resuming a SECOND time (another manual stop mid-resume) continues to
#     accumulate correctly
#
# ไม่ใช้ pytest (รูปแบบเดียวกับ pc/shared/uno_upload_retry_test.py)
# รันด้วย: .venv/bin/python pc/shared/uno_manual_stop_test.py

import csv
import io
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
sys.path.insert(0, str(REPO_ROOT / "pc" / "phase2_sweep"))

RESULTS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((name, status))
    print(f"[{status}] {name}  {detail}")


def _fresh_uno_sweep(scratch: Path):
    import importlib
    import uno_sweep as us
    importlib.reload(us)
    from shared import telemetry as tel
    from shared import paths as sp
    from shared import resume as rs
    from shared import timing_model as tm

    scratch.mkdir(parents=True, exist_ok=True)
    sp.REPO_ROOT = scratch
    us.find_uno_port = lambda hint: "/dev/fake"
    us.port_still_enumerated = lambda: True
    us.build_and_upload = lambda circuit, n, port_hint, build_timeout_s=None: {
        "ok": True, "ram_pct": 12.0, "ram_bytes": 234, "log": "",
        "port": "/dev/fake", "compile_s": 0.5, "upload_s": 0.5, "stage": "upload",
        "timed_out": False}
    return us, tel, sp, rs, tm


def _run(us, circuits, n_start, n_max):
    sys.argv = ["uno_sweep.py", "--port", "/dev/fake",
                "--circuits", *circuits,
                "--n-start", str(n_start), "--n-max", str(n_max),
                "--upload-retry-settle-s", "0"]
    us.main()


def _wall_rows(sp, circuit):
    return list(csv.DictReader(open(sp.memory_wall_csv_path("uno", circuit))))


def _raw_rows(sp, circuit):
    return list(csv.DictReader(open(sp.raw_csv_path("uno", circuit))))


def test_ceiling_no_longer_caps_phase2():
    from shared import timing_model as tm
    # a deliberately absurd n (grover-like exponential blowup) that would have
    # been far past the old 14400s ceiling
    budget = tm.timeout_budget_s("esp8266", "grover", 14)
    check("timeout_budget_s is no longer clamped at the old 14400s ceiling for "
          "an absurdly expensive point", budget > 14400, budget)
    check("is_compute_infeasible always False for Phase 2 now",
          tm.is_compute_infeasible("esp8266", "grover", 14) is False)
    check("budget_is_capped always False for Phase 2 now",
          tm.budget_is_capped("esp8266", "grover", 14) is False)


def test_read_serial_trials_catches_keyboardinterrupt_keeps_rows():
    """Directly exercises read_serial_trials (not the whole sweep) -- a fake
    pyserial object that yields a few good lines then raises
    KeyboardInterrupt on read must come back as (None, rows-so-far,
    "operator_stop"), not propagate the exception and lose `rows`."""
    import uno_sweep as us
    import importlib
    importlib.reload(us)

    lines = [
        b"uno,h_all,2,0,100,1000,1000\r\n",
        b"uno,h_all,2,1,100,1000,1000\r\n",
        b"uno,h_all,2,2,100,1000,1000\r\n",
    ]

    class FakeSerialKeyboardInterrupt:
        def __init__(self, *a, **kw):
            self.is_open = True
            self._lines = list(lines)

        def readline(self):
            if self._lines:
                return self._lines.pop(0)
            raise KeyboardInterrupt()

        def close(self):
            self.is_open = False

    us.serial.Serial = FakeSerialKeyboardInterrupt
    done, rows, note = us.read_serial_trials("/dev/fake", "h_all", 2, 90)

    check("manual stop: done sentinel is None (not True/False)", done is None, done)
    check("manual stop: all 3 rows received before the interrupt are kept",
          len(rows) == 3, rows)
    check("manual stop: note says operator_stop", note == "operator_stop", note)


def test_manual_stop_writes_resumable_partial_point_and_stops_whole_run(scratch: Path):
    us, tel, sp, rs, tm = _fresh_uno_sweep(scratch)

    def fake_read_serial_trials(port, circuit, n, timeout_s, **kwargs):
        rows = [f"uno,{circuit},{n},{r},100,1000,1000" for r in range(43)]
        return None, rows, "operator_stop"
    us.read_serial_trials = fake_read_serial_trials

    stopped_code = None
    try:
        _run(us, ["h_all"], 2, 3)
    except SystemExit as e:
        stopped_code = e.code

    check("manual stop: process exits 130 (Ctrl+C convention)", stopped_code == 130, stopped_code)

    wall = _wall_rows(sp, "h_all")
    row = [r for r in wall if r["circuit"] == "h_all" and r["n"] == "2"][0]
    check("manual stop: status is stopped_by_operator with reps_completed=43",
          row["status"] == "stopped_by_operator(reps_completed=43)", row["status"])
    check("manual stop: resume.py correctly parses 43 back out",
          rs.parse_operator_stopped_reps(row["status"]) == 43)

    raw = _raw_rows(sp, "h_all")
    reps_in_raw = sorted(int(r["rep"]) for r in raw)
    check("manual stop: exactly 43 raw rows written, relabeled rep 0..42",
          reps_in_raw == list(range(43)), reps_in_raw)

    check("manual stop: n=3 was NEVER attempted (whole run stopped, not just this point)",
          not any(r["circuit"] == "h_all" and r["n"] == "3" for r in wall))


def test_resume_appends_remaining_reps_and_reaches_ok(scratch: Path):
    us, tel, sp, rs, tm = _fresh_uno_sweep(scratch)

    # first invocation: stop at 43/100
    def fake_stop(port, circuit, n, timeout_s, **kwargs):
        rows = [f"uno,{circuit},{n},{r},100,1000,1000" for r in range(43)]
        return None, rows, "operator_stop"
    us.read_serial_trials = fake_stop
    try:
        _run(us, ["h_all"], 2, 2)
    except SystemExit:
        pass

    # second invocation: completes naturally -- firmware always reports a
    # FRESH full 100 reps (it has no concept of "resume"), the sweep script
    # must cap at what's still needed (57) and relabel continuing from 43
    calls = []

    def fake_complete(port, circuit, n, timeout_s, **kwargs):
        calls.append((circuit, n))
        rows = [f"uno,{circuit},{n},{r},100,1000,1000" for r in range(100)]
        return True, rows, "reset_count=0"
    us.read_serial_trials = fake_complete

    _run(us, ["h_all"], 2, 2)

    check("resume: build_and_upload/read reached n=2 again (not skipped)",
          ("h_all", 2) in calls, calls)

    wall = _wall_rows(sp, "h_all")
    row = [r for r in wall if r["circuit"] == "h_all" and r["n"] == "2"][-1]
    check("resume: final status is ok (reached full REPS)", row["status"] == "ok", row["status"])

    raw = _raw_rows(sp, "h_all")
    reps_in_raw = sorted(int(r["rep"]) for r in raw)
    check("resume: exactly 100 raw rows total (43 old + 57 new), rep 0..99 with no gaps/dupes",
          reps_in_raw == list(range(100)), (len(reps_in_raw), reps_in_raw[:5], reps_in_raw[-5:]))


def test_second_manual_stop_during_a_resume_accumulates_correctly(scratch: Path):
    us, tel, sp, rs, tm = _fresh_uno_sweep(scratch)

    def fake_stop_43(port, circuit, n, timeout_s, **kwargs):
        rows = [f"uno,{circuit},{n},{r},100,1000,1000" for r in range(43)]
        return None, rows, "operator_stop"
    us.read_serial_trials = fake_stop_43
    try:
        _run(us, ["h_all"], 2, 2)
    except SystemExit:
        pass

    # resume, stop AGAIN after only 30 more reps this time (firmware still
    # reports a fresh run, sweep caps at min(30, remaining_needed=57)=30)
    def fake_stop_30_more(port, circuit, n, timeout_s, **kwargs):
        rows = [f"uno,{circuit},{n},{r},100,1000,1000" for r in range(30)]
        return None, rows, "operator_stop"
    us.read_serial_trials = fake_stop_30_more
    try:
        _run(us, ["h_all"], 2, 2)
    except SystemExit:
        pass

    wall = _wall_rows(sp, "h_all")
    row = [r for r in wall if r["circuit"] == "h_all" and r["n"] == "2"][-1]
    check("second stop: reps_completed accumulated to 73 (43+30)",
          row["status"] == "stopped_by_operator(reps_completed=73)", row["status"])

    raw = _raw_rows(sp, "h_all")
    reps_in_raw = sorted(int(r["rep"]) for r in raw)
    check("second stop: 73 raw rows total, rep 0..72 with no gaps/dupes",
          reps_in_raw == list(range(73)), (len(reps_in_raw), reps_in_raw[-3:]))


def main():
    scratch_root = Path(tempfile.mkdtemp(prefix="uno_manual_stop_test_"))
    try:
        test_ceiling_no_longer_caps_phase2()
        test_read_serial_trials_catches_keyboardinterrupt_keeps_rows()
        test_manual_stop_writes_resumable_partial_point_and_stops_whole_run(
            scratch_root / "manual_stop")
        test_resume_appends_remaining_reps_and_reaches_ok(scratch_root / "resume")
        test_second_manual_stop_during_a_resume_accumulates_correctly(
            scratch_root / "twice")
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)

    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\n{len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
