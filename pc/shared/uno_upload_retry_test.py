#!/usr/bin/env python3
# uno_upload_retry_test.py — self-contained tests for standing operator
# decisions 1 and 2 (2026-09-20, see run_log.md) as implemented in
# pc/phase2_sweep/uno_sweep.py, PLUS the per-board-per-algorithm path layout
# (pc/shared/paths.py) that same commit's follow-up migration introduced:
#
#   decision 1 (upload failures): up to UPLOAD_MAX_ATTEMPTS (3) attempts total
#   per n for an upload-stage failure (avrdude never got a working handshake).
#   Exhausting all 3 never abandons the circuit -- the sweep continues to the
#   next n. Two consecutive n values that each exhaust all 3 attempts stop the
#   whole run. Compile errors and link overflow (deterministic) are never
#   retried and keep stopping the circuit as before.
#
#   decision 2 (memory wall auto-classification): the Uno linker exits 0 even
#   when compile-time RAM usage is above 100% (docs/preflight_report.md
#   finding L2), so compile_ram_pct evidence has to be checked after a
#   *successful* build too. When found, the point is still run once (for the
#   observed behaviour) but never retried, and the final status is forced to
#   build_overflow regardless of run outcome. A hang/reset WITHOUT that
#   evidence is NOT a wall (runtime_hang_or_reset, for the owner to review).
#
#   path layout: every circuit in --circuits is now its own directory (own
#   raw.csv/memory_wall.csv/points.csv/sessions.csv/env/) under
#   data/raw/phase<N>/<board>/<circuit>/ (pc/shared/paths.py) instead of one
#   shared file per board across all circuits -- redirected in tests by
#   setting paths.REPO_ROOT to a scratch dir, the same mechanism every caller
#   uses (paths.py's functions read REPO_ROOT as a module global at call time,
#   same late-binding fix telemetry.py already used for its own paths).
#
# Root-cause coverage: read_serial_trials() must close its pyserial handle on
# the hard_timeout path (see pc/phase2_sweep/uno_sweep.py read_serial_trials),
# which uno_sweep.py's pending_settle mechanism then relies on before the next
# build_and_upload call.
#
# ไม่ใช้ pytest (รูปแบบเดียวกับ pc/shared/telemetry_test.py และ la_capture_test.py)
# รันด้วย: .venv/bin/python pc/shared/uno_upload_retry_test.py

import csv
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
sys.path.insert(0, str(REPO_ROOT / "pc" / "phase2_sweep"))

RESULTS = []

STK500_LOG = (
    "avrdude: stk500_getsync() attempt 9 of 10: not in sync: resp=0x00\n"
    "avrdude: stk500_getsync() attempt 10 of 10: not in sync: resp=0x00\n"
    "\navrdude done.  Thank you.\n\n*** [upload] Error 1\n"
)

OVERFLOW_LOG = "region `data' overflowed by 206 bytes"


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

    scratch.mkdir(parents=True, exist_ok=True)
    # single redirection point for every path this sweep touches (raw/wall/
    # points/sessions/env/la, all derived from paths.py) -- late-bound at call
    # time inside each paths.py function, same fix telemetry.py already uses
    sp.REPO_ROOT = scratch
    us.find_uno_port = lambda hint: "/dev/fake"
    us.port_still_enumerated = lambda: True
    return us, tel, sp


def _install_read_serial_trials(us, n_rows=100, done=True):
    def fake_read_serial_trials(port, circuit, n, timeout_s):
        if not done:
            return False, [], "reset_count=0"
        rows = [f"uno,{circuit},{n},{r},100,1000,1000" for r in range(n_rows)]
        return True, rows, "reset_count=0"
    us.read_serial_trials = fake_read_serial_trials


def _run(us, circuits, n_start, n_max, extra_args=None):
    sys.argv = ["uno_sweep.py", "--port", "/dev/fake",
                "--circuits", *circuits,
                "--n-start", str(n_start), "--n-max", str(n_max),
                "--upload-retry-settle-s", "0"]
    if extra_args:
        sys.argv += extra_args
    us.main()


def _upload_fail_result():
    return {"ok": False, "ram_pct": 11.3, "ram_bytes": 232, "log": STK500_LOG,
            "port": "/dev/fake", "compile_s": 4.0, "upload_s": 6.3, "stage": "upload",
            "timed_out": False}


def _ok_result(ram_pct=12.0, ram_bytes=234):
    return {"ok": True, "ram_pct": ram_pct, "ram_bytes": ram_bytes, "log": "",
            "port": "/dev/fake", "compile_s": 0.5, "upload_s": 0.5, "stage": "upload",
            "timed_out": False}


def _wall_rows(sp, circuit):
    return list(csv.DictReader(open(sp.memory_wall_csv_path("uno", circuit))))


def _points_rows(sp, circuit):
    return list(csv.DictReader(open(sp.points_csv_path("uno", circuit))))


def test_upload_failure_retries_and_succeeds_on_third_attempt(scratch: Path):
    us, tel, sp = _fresh_uno_sweep(scratch / "retry_succeeds_attempt3")
    _install_read_serial_trials(us)

    calls = []

    def fake_build_and_upload(circuit, n, port_hint, build_timeout_s=None):
        calls.append((circuit, n))
        if circuit == "h_all" and n == 2 and calls.count(("h_all", 2)) < 3:
            return _upload_fail_result()
        return _ok_result()
    us.build_and_upload = fake_build_and_upload

    _run(us, ["h_all"], 2, 3)

    check("attempt3 success: build_and_upload called 3 times for n=2 (fail, fail, ok)",
          calls.count(("h_all", 2)) == 3, calls)
    check("attempt3 success: n=3 (same circuit) still attempted -- circuit NOT abandoned",
          ("h_all", 3) in calls, calls)

    wall_rows = _wall_rows(sp, "h_all")
    row = [r for r in wall_rows if r["circuit"] == "h_all" and r["n"] == "2"][0]
    check("attempt3 success: n=2 ends up recorded ok", row["status"] == "ok", row)
    check("attempt3 success: retry_count=2 recorded", row["retry_count"] == "2", row["retry_count"])

    pts = _points_rows(sp, "h_all")
    n2_rows = [r for r in pts if r["n"] == "2"]
    check("attempt3 success: 3 telemetry rows for n=2 (one per attempt)",
          len(n2_rows) == 3, len(n2_rows))
    check("attempt3 success: attempts 0,1 telemetry status=retrying",
          n2_rows[0]["status"] == "retrying" and n2_rows[1]["status"] == "retrying",
          [r["status"] for r in n2_rows])
    check("attempt3 success: attempt 2 telemetry status=ok",
          n2_rows[2]["status"] == "ok", n2_rows[2]["status"])
    check("attempt3 success: failure_type stays 'build' (no new enum value)",
          n2_rows[0]["failure_type"] == "build", n2_rows[0]["failure_type"])


def test_upload_failure_exhausts_all_3_then_continues_to_next_n(scratch: Path):
    us, tel, sp = _fresh_uno_sweep(scratch / "exhaust_continues")
    _install_read_serial_trials(us)

    calls = []

    def fake_build_and_upload(circuit, n, port_hint, build_timeout_s=None):
        calls.append((circuit, n))
        if circuit == "h_all" and n == 2:
            return _upload_fail_result()
        return _ok_result()
    us.build_and_upload = fake_build_and_upload

    _run(us, ["h_all"], 2, 4)

    check("exhaust-continues: build_and_upload called exactly 3 times for n=2 (no 4th attempt)",
          calls.count(("h_all", 2)) == 3, calls)
    check("exhaust-continues: n=3 in the SAME circuit IS attempted "
          "(upload failure never abandons the circuit)",
          ("h_all", 3) in calls, calls)
    check("exhaust-continues: n=4 in the SAME circuit IS also attempted",
          ("h_all", 4) in calls, calls)

    wall_rows = _wall_rows(sp, "h_all")
    row = [r for r in wall_rows if r["circuit"] == "h_all" and r["n"] == "2"][0]
    check("exhaust-continues: final status is build_or_upload_fail (no new status value)",
          row["status"] == "build_or_upload_fail", row["status"])
    check("exhaust-continues: retry_count=2 recorded (3 attempts = 2 retries)",
          row["retry_count"] == "2", row["retry_count"])
    row3 = [r for r in wall_rows if r["circuit"] == "h_all" and r["n"] == "3"][0]
    check("exhaust-continues: n=3 recorded ok", row3["status"] == "ok", row3)


def test_two_consecutive_n_exhaustions_stop_the_whole_run(scratch: Path):
    us, tel, sp = _fresh_uno_sweep(scratch / "consecutive_stop")
    _install_read_serial_trials(us)

    calls = []

    def fake_build_and_upload(circuit, n, port_hint, build_timeout_s=None):
        calls.append((circuit, n))
        return _upload_fail_result()  # every n in h_all fails all attempts
    us.build_and_upload = fake_build_and_upload

    stopped = False
    try:
        _run(us, ["h_all"], 2, 5)
    except SystemExit as e:
        stopped = True
        check("consecutive stop: exits with code 2", e.code == 2, e.code)

    check("consecutive stop: run actually stopped via SystemExit", stopped)
    check("consecutive stop: n=2 attempted 3 times", calls.count(("h_all", 2)) == 3, calls)
    check("consecutive stop: n=3 attempted 3 times (2nd consecutive exhaustion -> stop)",
          calls.count(("h_all", 3)) == 3, calls)
    check("consecutive stop: n=4 never attempted -- stopped before reaching it",
          ("h_all", 4) not in calls, calls)


def test_port_closed_after_hard_timeout(scratch: Path):
    us, tel, sp = _fresh_uno_sweep(scratch / "hard_timeout_close")

    state = {"closed": False, "is_open": True}

    class FakeSerialHardTimeout:
        def __init__(self, *a, **kw):
            self.is_open = True
            state["is_open"] = True

        def readline(self):
            raise us.HardTimeout()

        def close(self):
            self.is_open = False
            state["closed"] = True
            state["is_open"] = False

    us.serial.Serial = FakeSerialHardTimeout

    done, rows, note = us.read_serial_trials("/dev/fake", "h_all", 2, 1)

    check("hard timeout: read_serial_trials returns done=False", done is False, done)
    check("hard timeout: note flags hard_timeout=true", "hard_timeout=true" in note, note)
    check("hard timeout: pyserial handle's close() was called", state["closed"] is True)
    check("hard timeout: handle no longer reports open", state["is_open"] is False)


def test_hard_timeout_triggers_settle_before_next_build_and_upload(scratch: Path):
    us, tel, sp = _fresh_uno_sweep(scratch / "hard_timeout_settle")

    slept = []
    real_sleep = us.time.sleep
    us.time.sleep = lambda s: slept.append(s)

    call_count = {"n": 0}

    def fake_read_serial_trials(port, circuit, n, timeout_s):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return False, [], "hard_timeout=true,reset_count=0"
        return True, [f"uno,{circuit},{n},{r},100,1000,1000" for r in range(100)], "reset_count=0"
    us.read_serial_trials = fake_read_serial_trials
    us.build_and_upload = lambda circuit, n, port_hint, build_timeout_s=None: _ok_result()

    try:
        _run(us, ["h_all"], 2, 2, extra_args=["--upload-retry-settle-s", "5"])
    finally:
        us.time.sleep = real_sleep  # module-level monkeypatch -- must not leak into later tests

    check("hard-timeout settle: a 5s settle sleep happened before the retry's "
          "build_and_upload (not just BOOT_WAIT_S)", 5.0 in slept, slept)


def test_compile_ram_wall_stops_climbing_despite_successful_build(scratch: Path):
    us, tel, sp = _fresh_uno_sweep(scratch / "ram_wall")
    _install_read_serial_trials(us)

    calls = []

    def fake_build_and_upload(circuit, n, port_hint, build_timeout_s=None):
        calls.append((circuit, n))
        if circuit == "h_all" and n == 8:
            # Uno L2 quirk: linker exits 0 (ok=True) even though RAM > 100%
            return _ok_result(ram_pct=110.5, ram_bytes=2260)
        return _ok_result()
    us.build_and_upload = fake_build_and_upload

    _run(us, ["h_all", "bell_ghz"], 8, 9)

    check("ram wall: build_and_upload called exactly once for n=8 (no retry)",
          calls.count(("h_all", 8)) == 1, calls)
    check("ram wall: n=9 in the same circuit never attempted (wall stops climbing)",
          ("h_all", 9) not in calls, calls)
    check("ram wall: next circuit still attempted",
          ("bell_ghz", 8) in calls, calls)

    wall_rows = _wall_rows(sp, "h_all")
    row = [r for r in wall_rows if r["circuit"] == "h_all" and r["n"] == "8"][0]
    check("ram wall: status forced to build_overflow despite ok=True/done=True",
          row["status"] == "build_overflow", row["status"])
    check("ram wall: compile_ram_pct evidence recorded", row["compile_ram_pct"] == "110.5",
          row["compile_ram_pct"])
    check("ram wall: retry_count=0 (never retried)", row["retry_count"] == "0", row["retry_count"])

    raw_rows = list(csv.DictReader(
        open(sp.raw_csv_path("uno", "h_all")),
        fieldnames=["board", "circuit", "n", "rep", "exec_time_us",
                    "free_heap_before", "free_heap_after", "timeout_budget_s"]))
    check("ram wall: the single observed run's raw trial data is still kept",
          any(r["circuit"] == "h_all" and r["n"] == "8" for r in raw_rows[1:]))


def test_hang_without_ram_evidence_is_not_a_wall(scratch: Path):
    us, tel, sp = _fresh_uno_sweep(scratch / "hang_not_wall")
    _install_read_serial_trials(us, done=False)  # never sends DONE -> hang
    us.build_and_upload = lambda circuit, n, port_hint, build_timeout_s=None: _ok_result(ram_pct=45.0)

    calls = {"n": 0}
    orig_read = us.read_serial_trials

    def counting_read(*a, **kw):
        calls["n"] += 1
        return orig_read(*a, **kw)
    us.read_serial_trials = counting_read

    _run(us, ["h_all"], 2, 2)  # Uno has no WDT threshold (timing_model.WDT_PER_REP_THRESHOLD_S
    # ["uno"] is None) so this is deterministically runtime_hang_or_reset, not watchdog_suspected

    check("hang: retried once (2 read attempts) before giving up", calls["n"] == 2, calls["n"])

    wall_rows = _wall_rows(sp, "h_all")
    row = [r for r in wall_rows if r["circuit"] == "h_all" and r["n"] == "2"][0]
    check("hang: status is runtime_hang_or_reset, NOT build_overflow",
          row["status"].startswith("runtime_hang_or_reset"), row["status"])

    import importlib
    from shared import resume as rs
    importlib.reload(rs)
    check("hang: rs.is_wall_status() is False for this status (NOT a Memory Wall)",
          rs.is_wall_status(row["status"]) is False, row["status"])
    check("hang: rs.stops_climbing() is still True (stops climbing THIS session only)",
          rs.stops_climbing(row["status"]) is True, row["status"])


def test_build_overflow_deterministic_never_retries(scratch: Path):
    us, tel, sp = _fresh_uno_sweep(scratch / "overflow")
    _install_read_serial_trials(us)
    calls = []

    def fake_build_and_upload(circuit, n, port_hint, build_timeout_s=None):
        calls.append((circuit, n))
        return {"ok": False, "ram_pct": 110.1, "ram_bytes": 2254,
                "log": OVERFLOW_LOG, "port": "/dev/fake",
                "compile_s": 2.0, "upload_s": 0.0, "stage": "compile", "timed_out": False}
    us.build_and_upload = fake_build_and_upload
    us.port_still_enumerated = lambda: (_ for _ in ()).throw(
        AssertionError("port_still_enumerated must not be called for a deterministic overflow"))

    _run(us, ["h_all", "bell_ghz"], 8, 9)

    check("build_overflow: build_and_upload called exactly once (no retry at all)",
          calls.count(("h_all", 8)) == 1, calls)
    check("build_overflow: higher n in same circuit never attempted",
          ("h_all", 9) not in calls, calls)
    check("build_overflow: next circuit still attempted",
          ("bell_ghz", 8) in calls, calls)

    wall_rows = _wall_rows(sp, "h_all")
    row = [r for r in wall_rows if r["circuit"] == "h_all" and r["n"] == "8"][0]
    check("build_overflow: status stays build_overflow, retry_count=0",
          row["status"] == "build_overflow" and row["retry_count"] == "0", row)


def test_upload_failure_retries_regardless_of_budget_rule(scratch: Path):
    """Decision 1's 3-attempt upload retry is NOT gated by the budget rule
    (RETRY_MAX_BUDGET_S) the way the hang/build_timeout retry is -- reflash
    time doesn't scale with n the way device-run time does."""
    us, tel, sp = _fresh_uno_sweep(scratch / "upload_retry_ignores_budget")
    _install_read_serial_trials(us)
    us.tm.retry_allowed = lambda budget_s: False  # force may_retry=False regardless of budget

    calls = []

    def fake_build_and_upload(circuit, n, port_hint, build_timeout_s=None):
        calls.append((circuit, n))
        if calls.count(("h_all", 2)) < 2:
            return _upload_fail_result()
        return _ok_result()
    us.build_and_upload = fake_build_and_upload

    _run(us, ["h_all"], 2, 2)

    check("upload retry ignores budget rule: retried despite may_retry=False",
          calls.count(("h_all", 2)) == 2, calls)
    wall_rows = _wall_rows(sp, "h_all")
    row = [r for r in wall_rows if r["circuit"] == "h_all" and r["n"] == "2"][0]
    check("upload retry ignores budget rule: ends up ok", row["status"] == "ok", row["status"])


def test_resume_skips_completed_points_on_second_invocation(scratch: Path):
    us, tel, sp = _fresh_uno_sweep(scratch / "resume")
    _install_read_serial_trials(us)
    us.build_and_upload = lambda circuit, n, port_hint, build_timeout_s=None: _ok_result()

    _run(us, ["h_all"], 2, 3)

    calls = []

    def fake_build_and_upload_2(circuit, n, port_hint, build_timeout_s=None):
        calls.append((circuit, n))
        return _ok_result()
    us.build_and_upload = fake_build_and_upload_2

    _run(us, ["h_all"], 2, 3)  # second invocation, same result files -> resume

    check("resume: second invocation touches hardware zero times (everything skipped)",
          calls == [], calls)

    pts = _points_rows(sp, "h_all")
    second_session_statuses = [r["status"] for r in pts if r["session_id"]][-2:]
    check("resume: skip rows use skipped_resume (existing status value, no new one)",
          all(s == "skipped_resume" for s in second_session_statuses), second_session_statuses)


def test_paths_helper_resolves_per_board_per_algorithm_layout(scratch: Path):
    """pc/shared/paths.py itself: every function resolves to
    data/raw/phase<N>/<board>/<circuit>/... under whatever REPO_ROOT is set to
    at call time (not at import/def time -- the same late-binding requirement
    telemetry.py's write_point_row docstring documents)."""
    from shared import paths as sp
    root = scratch / "paths_helper"
    sp.REPO_ROOT = root

    check("paths: raw_dir",
          sp.raw_dir("uno", "h_all", phase=2) == root / "data/raw/phase2/uno/h_all")
    check("paths: raw_csv_path",
          sp.raw_csv_path("uno", "h_all", phase=2) == root / "data/raw/phase2/uno/h_all/raw.csv")
    check("paths: memory_wall_csv_path",
          sp.memory_wall_csv_path("uno", "h_all", phase=2)
          == root / "data/raw/phase2/uno/h_all/memory_wall.csv")
    check("paths: points_csv_path",
          sp.points_csv_path("uno", "h_all", phase=2)
          == root / "data/raw/phase2/uno/h_all/points.csv")
    check("paths: sessions_csv_path",
          sp.sessions_csv_path("uno", "h_all", phase=2)
          == root / "data/raw/phase2/uno/h_all/sessions.csv")
    check("paths: env_dir",
          sp.env_dir("uno", "h_all", phase=2) == root / "data/raw/phase2/uno/h_all/env")
    check("paths: la_dir",
          sp.la_dir("uno", "h_all", phase=2) == root / "data/raw/phase2/uno/h_all/la")
    check("paths: figures_dir per-circuit",
          sp.figures_dir("uno", "h_all") == root / "data/figures/uno/h_all")
    check("paths: figures_dir cumulative (circuit=None)",
          sp.figures_dir("uno") == root / "data/figures/uno")

    # late-binding check: re-point REPO_ROOT and confirm a function called
    # WITHOUT re-importing picks up the new value (this is the exact bug class
    # find_plan_entry() had before its 2026-09-20 fix -- see la_capture.py)
    root2 = scratch / "paths_helper_2"
    sp.REPO_ROOT = root2
    check("paths: REPO_ROOT reassignment takes effect without reimport (late-bound)",
          sp.raw_csv_path("uno", "h_all", phase=2) == root2 / "data/raw/phase2/uno/h_all/raw.csv")


def test_two_algorithms_get_two_separate_directories_and_nothing_leaks(scratch: Path):
    """Mocked dry run of two algorithms in one invocation: confirms each gets
    its own data/raw/phase2/uno/<circuit>/ directory (raw.csv, memory_wall.csv,
    points.csv, sessions.csv, env/*.json all present and non-empty for both),
    and that nothing is written anywhere else under data/raw/phase2/uno/ (no
    stray files outside the two expected per-circuit trees)."""
    us, tel, sp = _fresh_uno_sweep(scratch / "two_algorithms")
    _install_read_serial_trials(us, n_rows=5)
    us.build_and_upload = lambda circuit, n, port_hint, build_timeout_s=None: _ok_result()

    _run(us, ["h_all", "bell_ghz"], 2, 2)

    uno_root = sp.REPO_ROOT / "data" / "raw" / "phase2" / "uno"
    all_files = sorted(p.relative_to(uno_root) for p in uno_root.rglob("*") if p.is_file())
    expected_prefixes = ("h_all/", "bell_ghz/")
    check("two algorithms: at least raw.csv+memory_wall.csv+points.csv+sessions.csv+1 env "
          "json exist for BOTH circuits",
          all((sp.raw_dir("uno", c, 2) / f).exists()
              for c in ("h_all", "bell_ghz")
              for f in ("raw.csv", "memory_wall.csv", "points.csv", "sessions.csv"))
          and len(list(sp.env_dir("uno", "h_all", 2).glob("*.json"))) >= 1
          and len(list(sp.env_dir("uno", "bell_ghz", 2).glob("*.json"))) >= 1)
    check("two algorithms: every file under data/raw/phase2/uno/ lives under one of the "
          "two circuits' own directory -- nothing leaked elsewhere",
          all(str(f).startswith(expected_prefixes) for f in all_files), all_files)
    check("two algorithms: h_all's raw.csv contains only h_all rows (no cross-contamination)",
          all(row["circuit"] == "h_all"
              for row in csv.DictReader(open(sp.raw_csv_path("uno", "h_all")))))
    check("two algorithms: bell_ghz's raw.csv contains only bell_ghz rows (no cross-contamination)",
          all(row["circuit"] == "bell_ghz"
              for row in csv.DictReader(open(sp.raw_csv_path("uno", "bell_ghz")))))


def main():
    scratch = Path(tempfile.mkdtemp(prefix="uno_upload_retry_test_"))
    try:
        test_upload_failure_retries_and_succeeds_on_third_attempt(scratch)
        test_upload_failure_exhausts_all_3_then_continues_to_next_n(scratch)
        test_two_consecutive_n_exhaustions_stop_the_whole_run(scratch)
        test_port_closed_after_hard_timeout(scratch)
        test_hard_timeout_triggers_settle_before_next_build_and_upload(scratch)
        test_compile_ram_wall_stops_climbing_despite_successful_build(scratch)
        test_hang_without_ram_evidence_is_not_a_wall(scratch)
        test_build_overflow_deterministic_never_retries(scratch)
        test_upload_failure_retries_regardless_of_budget_rule(scratch)
        test_resume_skips_completed_points_on_second_invocation(scratch)
        test_paths_helper_resolves_per_board_per_algorithm_layout(scratch)
        test_two_algorithms_get_two_separate_directories_and_nothing_leaks(scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\n{len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
