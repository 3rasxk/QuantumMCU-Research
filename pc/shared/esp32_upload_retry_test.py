#!/usr/bin/env python3
# esp32_upload_retry_test.py — self-contained tests for standing operator
# decision 1 (2026-09-20 for Uno, ported to ESP32 2026-09-22, see run_log.md)
# as implemented in pc/phase2_sweep/esp32_sweep.py. Mirrors
# pc/shared/uno_upload_retry_test.py's structure and mocking approach, scoped
# to the scenarios the port needs to cover:
#
#   - upload failure at the smallest n, then success on retry
#   - retries exhausted at one n -> continues to the NEXT n (circuit not
#     abandoned)
#   - two consecutive n values that each exhaust all retries -> stops the
#     whole run
#   - deterministic failures (build/link overflow) still stop climbing
#     immediately, never retried
#   - resume is unaffected by any of the above (second invocation with the
#     same result files touches hardware zero times)
#
# ไม่ใช้ pytest (รูปแบบเดียวกับ pc/shared/uno_upload_retry_test.py)
# รันด้วย: .venv/bin/python pc/shared/esp32_upload_retry_test.py

import csv
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
sys.path.insert(0, str(REPO_ROOT / "pc" / "phase2_sweep"))

RESULTS = []

# esptool (newer modular package -- espressif32@7.0.1 pins tool-esptoolpy
# ~2.41100.0, distinct from ESP8266's older single-file esptool.py) sync-
# failure wording -- see esp32_sweep.py's UPLOAD_SYNC_FAILURE_MARKERS comment
# for the file:line citations.
ESPTOOL_SYNC_LOG = (
    "Connecting.......\n"
    "A fatal error occurred: Failed to connect to ESP32: "
    "No serial data received.\n"
)

OVERFLOW_LOG = "region `iram1_0_seg' overflowed by 512 bytes"


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((name, status))
    print(f"[{status}] {name}  {detail}")


def _fresh_esp32_sweep(scratch: Path):
    import importlib
    import esp32_sweep as es
    importlib.reload(es)
    from shared import telemetry as tel
    from shared import paths as sp

    scratch.mkdir(parents=True, exist_ok=True)
    sp.REPO_ROOT = scratch
    es.find_esp_port = lambda hint: "/dev/fake"
    es.port_still_enumerated = lambda: True
    return es, tel, sp


def _rows_for(circuit, n, n_rows=100):
    # esp32's raw.csv has an extra largest_block column vs esp8266's (see
    # esp32_sweep.py's raw header: ..., free_heap_after, largest_block,
    # timeout_budget_s) -- the device line itself carries 8 fields, budget_s
    # is appended by the sweep script.
    return [f"esp32,{circuit},{n},{r},100,1000,1000,900" for r in range(n_rows)]


def _run(es, circuits, n_start, n_max, extra_args=None):
    sys.argv = ["esp32_sweep.py", "--port", "/dev/fake",
                "--circuits", *circuits,
                "--n-start", str(n_start), "--n-max", str(n_max),
                "--upload-retry-settle-s", "0"]
    if extra_args:
        sys.argv += extra_args
    es.main()


def _upload_fail_result():
    return {"ok": False, "ram_pct": None, "ram_bytes": None, "log": ESPTOOL_SYNC_LOG,
            "port": "/dev/fake", "compile_s": 3.0, "upload_s": 5.0, "stage": "upload",
            "timed_out": False}


def _ok_result():
    return {"ok": True, "ram_pct": None, "ram_bytes": None, "log": "",
            "port": "/dev/fake", "compile_s": 0.5, "upload_s": 0.5, "stage": "upload",
            "timed_out": False}


def _wall_rows(sp, circuit):
    return list(csv.DictReader(open(sp.memory_wall_csv_path("esp32", circuit))))


def _points_rows(sp, circuit):
    return list(csv.DictReader(open(sp.points_csv_path("esp32", circuit))))


def test_upload_failure_at_smallest_n_then_success_on_retry(scratch: Path):
    es, tel, sp = _fresh_esp32_sweep(scratch / "retry_succeeds")

    def fake_read_serial_trials(port, circuit, n, timeout_s, **kwargs):
        return True, _rows_for("h_all", 2), False, "reset_count=0"
    es.read_serial_trials = fake_read_serial_trials

    calls = []

    def fake_build_and_upload(circuit, n, port_hint, build_timeout_s=None):
        calls.append((circuit, n))
        if circuit == "h_all" and n == 2 and calls.count(("h_all", 2)) < 2:
            return _upload_fail_result()
        return _ok_result()
    es.build_and_upload = fake_build_and_upload

    _run(es, ["h_all"], 2, 2)

    check("retry succeeds: build_and_upload called twice for smallest n=2 (fail, ok)",
          calls.count(("h_all", 2)) == 2, calls)

    wall_rows = _wall_rows(sp, "h_all")
    row = [r for r in wall_rows if r["circuit"] == "h_all" and r["n"] == "2"][0]
    check("retry succeeds: n=2 ends up recorded ok", row["status"] == "ok", row)
    check("retry succeeds: retry_count=1 recorded", row["retry_count"] == "1", row["retry_count"])

    pts = _points_rows(sp, "h_all")
    check("retry succeeds: attempt 0 telemetry status=retrying",
          pts[0]["status"] == "retrying", pts[0]["status"])
    check("retry succeeds: attempt 1 telemetry status=ok",
          pts[1]["status"] == "ok", pts[1]["status"])


def test_retries_exhausted_then_continues_to_next_n(scratch: Path):
    es, tel, sp = _fresh_esp32_sweep(scratch / "exhaust_continues")

    def fake_read_serial_trials(port, circuit, n, timeout_s, **kwargs):
        return True, _rows_for("h_all", 3), False, "reset_count=0"
    es.read_serial_trials = fake_read_serial_trials

    calls = []

    def fake_build_and_upload(circuit, n, port_hint, build_timeout_s=None):
        calls.append((circuit, n))
        if circuit == "h_all" and n == 2:
            return _upload_fail_result()
        return _ok_result()
    es.build_and_upload = fake_build_and_upload

    _run(es, ["h_all"], 2, 4)

    check("exhaust-continues: build_and_upload called exactly 3 times for n=2 (no 4th attempt)",
          calls.count(("h_all", 2)) == 3, calls)
    check("exhaust-continues: n=3 in the SAME circuit IS attempted (circuit not abandoned)",
          ("h_all", 3) in calls, calls)
    check("exhaust-continues: n=4 in the SAME circuit IS also attempted",
          ("h_all", 4) in calls, calls)

    wall_rows = _wall_rows(sp, "h_all")
    row2 = [r for r in wall_rows if r["circuit"] == "h_all" and r["n"] == "2"][0]
    check("exhaust-continues: final status is build_or_upload_fail (no new status value)",
          row2["status"] == "build_or_upload_fail", row2["status"])
    check("exhaust-continues: retry_count=2 recorded (3 attempts = 2 retries)",
          row2["retry_count"] == "2", row2["retry_count"])
    row3 = [r for r in wall_rows if r["circuit"] == "h_all" and r["n"] == "3"][0]
    check("exhaust-continues: n=3 recorded ok", row3["status"] == "ok", row3)


def test_two_consecutive_n_exhaustions_stop_the_whole_run(scratch: Path):
    es, tel, sp = _fresh_esp32_sweep(scratch / "consecutive_stop")
    es.read_serial_trials = lambda port, circuit, n, timeout_s, **kwargs: (True, _rows_for("h_all", 99), False, "reset_count=0")

    calls = []

    def fake_build_and_upload(circuit, n, port_hint, build_timeout_s=None):
        calls.append((circuit, n))
        return _upload_fail_result()  # every n in h_all fails all attempts
    es.build_and_upload = fake_build_and_upload

    stopped = False
    try:
        _run(es, ["h_all"], 2, 5)
    except SystemExit as e:
        stopped = True
        check("consecutive stop: exits with code 2", e.code == 2, e.code)

    check("consecutive stop: run actually stopped via SystemExit", stopped)
    check("consecutive stop: n=2 attempted 3 times", calls.count(("h_all", 2)) == 3, calls)
    check("consecutive stop: n=3 attempted 3 times (2nd consecutive exhaustion -> stop)",
          calls.count(("h_all", 3)) == 3, calls)
    check("consecutive stop: n=4 never attempted -- stopped before reaching it",
          ("h_all", 4) not in calls, calls)


def test_deterministic_overflow_never_retries_and_stops_climbing(scratch: Path):
    es, tel, sp = _fresh_esp32_sweep(scratch / "overflow")
    es.read_serial_trials = lambda port, circuit, n, timeout_s, **kwargs: (True, _rows_for("h_all", 99), False, "reset_count=0")

    calls = []

    def fake_build_and_upload(circuit, n, port_hint, build_timeout_s=None):
        calls.append((circuit, n))
        return {"ok": False, "ram_pct": None, "ram_bytes": None, "log": OVERFLOW_LOG,
                "port": "/dev/fake", "compile_s": 2.0, "upload_s": 0.0, "stage": "compile",
                "timed_out": False}
    es.build_and_upload = fake_build_and_upload
    es.port_still_enumerated = lambda: (_ for _ in ()).throw(
        AssertionError("port_still_enumerated must not be called for a deterministic overflow"))

    _run(es, ["h_all", "bell_ghz"], 8, 9)

    check("build_overflow: build_and_upload called exactly once (no retry at all)",
          calls.count(("h_all", 8)) == 1, calls)
    check("build_overflow: higher n in same circuit never attempted (stops climbing)",
          ("h_all", 9) not in calls, calls)
    check("build_overflow: next circuit still attempted",
          ("bell_ghz", 8) in calls, calls)

    wall_rows = _wall_rows(sp, "h_all")
    row = [r for r in wall_rows if r["circuit"] == "h_all" and r["n"] == "8"][0]
    check("build_overflow: status stays build_overflow, retry_count=0",
          row["status"] == "build_overflow" and row["retry_count"] == "0", row)


def test_resume_unaffected_by_upload_retry_changes(scratch: Path):
    es, tel, sp = _fresh_esp32_sweep(scratch / "resume")
    es.read_serial_trials = lambda port, circuit, n, timeout_s, **kwargs: (True, _rows_for("h_all", 2), False, "reset_count=0")
    es.build_and_upload = lambda circuit, n, port_hint, build_timeout_s=None: _ok_result()

    _run(es, ["h_all"], 2, 3)

    calls = []

    def fake_build_and_upload_2(circuit, n, port_hint, build_timeout_s=None):
        calls.append((circuit, n))
        return _ok_result()
    es.build_and_upload = fake_build_and_upload_2

    _run(es, ["h_all"], 2, 3)  # second invocation, same result files -> resume

    check("resume: second invocation touches hardware zero times (everything skipped)",
          calls == [], calls)

    pts = _points_rows(sp, "h_all")
    second_session_statuses = [r["status"] for r in pts if r["session_id"]][-2:]
    check("resume: skip rows use skipped_resume (existing status value, no new one)",
          all(s == "skipped_resume" for s in second_session_statuses), second_session_statuses)


def main():
    scratch = Path(tempfile.mkdtemp(prefix="esp32_upload_retry_test_"))
    try:
        test_upload_failure_at_smallest_n_then_success_on_retry(scratch)
        test_retries_exhausted_then_continues_to_next_n(scratch)
        test_two_consecutive_n_exhaustions_stop_the_whole_run(scratch)
        test_deterministic_overflow_never_retries_and_stops_climbing(scratch)
        test_resume_unaffected_by_upload_retry_changes(scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\n{len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
