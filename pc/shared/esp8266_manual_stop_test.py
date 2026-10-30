#!/usr/bin/env python3
# esp8266_manual_stop_test.py — lighter-weight port of uno_manual_stop_test.py's
# coverage for esp8266_sweep.py (2026-09-22 standing decision: ceiling removed,
# ETA/progress printing, operator manual stop via Ctrl+C, resumable partial
# reps). See uno_manual_stop_test.py for the full design rationale; this file
# only re-verifies the same behavior survives esp8266's 4-tuple
# (done, rows, malloc_failed, note) read_serial_trials return shape and its
# `with serial.Serial(...) as ser:` context-manager read loop.
#
# ไม่ใช้ pytest, รันด้วย: .venv/bin/python pc/shared/esp8266_manual_stop_test.py

import csv
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


def _fresh_esp8266_sweep(scratch: Path):
    import importlib
    import esp8266_sweep as es
    importlib.reload(es)
    from shared import telemetry as tel
    from shared import paths as sp
    from shared import resume as rs
    from shared import timing_model as tm

    scratch.mkdir(parents=True, exist_ok=True)
    sp.REPO_ROOT = scratch
    es.find_esp_port = lambda hint: "/dev/fake"
    es.port_still_enumerated = lambda: True
    es.build_and_upload = lambda circuit, n, port_hint, build_timeout_s=None: {
        "ok": True, "ram_pct": None, "ram_bytes": None, "log": "",
        "port": "/dev/fake", "compile_s": 0.5, "upload_s": 0.5, "stage": "upload",
        "timed_out": False}
    return es, tel, sp, rs, tm


def _run(es, circuits, n_start, n_max):
    sys.argv = ["esp8266_sweep.py", "--port", "/dev/fake",
                "--circuits", *circuits,
                "--n-start", str(n_start), "--n-max", str(n_max),
                "--upload-retry-settle-s", "0"]
    es.main()


def _wall_rows(sp, circuit):
    return list(csv.DictReader(open(sp.memory_wall_csv_path("esp8266", circuit))))


def _raw_rows(sp, circuit):
    return list(csv.DictReader(open(sp.raw_csv_path("esp8266", circuit))))


def test_ceiling_no_longer_caps_esp8266():
    from shared import timing_model as tm
    budget = tm.timeout_budget_s("esp8266", "grover", 14)
    check("timeout_budget_s no longer clamped at old 14400s ceiling",
          budget > 14400, budget)
    check("is_compute_infeasible always False now",
          tm.is_compute_infeasible("esp8266", "grover", 14) is False)


def test_read_serial_trials_catches_keyboardinterrupt_keeps_rows():
    import esp8266_sweep as es
    import importlib
    importlib.reload(es)

    lines = [
        b"esp8266,h_all,2,0,100,1000,1000\r\n",
        b"esp8266,h_all,2,1,100,1000,1000\r\n",
    ]

    class FakeSerialCtx:
        def __init__(self, *a, **kw):
            self._lines = list(lines)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def readline(self):
            if self._lines:
                return self._lines.pop(0)
            raise KeyboardInterrupt()

    es.serial.Serial = FakeSerialCtx
    done, rows, malloc_failed, note = es.read_serial_trials("/dev/fake", "h_all", 2, 90)

    check("manual stop: done sentinel is None", done is None, done)
    check("manual stop: 2 rows kept before interrupt", len(rows) == 2, rows)
    check("manual stop: malloc_failed False", malloc_failed is False)
    check("manual stop: note says operator_stop", note == "operator_stop", note)


def test_time_cap_stops_collection():
    """2026-10-05 rule: board run time per point <= 2 h; 80 reps of 90 s = 2 h fit, the 81st would not."""
    import esp8266_sweep as es
    import importlib
    importlib.reload(es)

    lines = [f"esp8266,grover,9,{i},90000000,1000,1000\r\n".encode() for i in range(100)]

    class FakeSerialCtx:
        def __init__(self, *a, **kw):
            self._lines = list(lines)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def readline(self):
            return self._lines.pop(0) if self._lines else b"DONE\r\n"

    es.serial.Serial = FakeSerialCtx
    done, rows, malloc_failed, note = es.read_serial_trials("/dev/fake", "grover", 9, 90)
    check("time cap: collection ends as done", done is True, done)
    check("time cap: exactly 80 reps kept (80 x 90 s = 2 h)", len(rows) == 80, len(rows))
    check("time cap: note carries time_capped=80", "time_capped=80" in note, note)


def test_watchdog_reset_loop_gives_up():
    """Board re-boots forever without finishing rep 0 (hardware watchdog): stop after a few boots."""
    import esp8266_sweep as es
    import importlib
    importlib.reload(es)
    header = b"\xf3\x9a ets Jan  8 2013,rst cause:4 board,circuit,n,rep,exec_time_us,free_heap_before,free_heap_after\r\n"
    state = {"reads": 0}

    class FakeSerialCtx:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def readline(self):
            state["reads"] += 1
            if state["reads"] > 50:  # would loop forever without the fix
                raise AssertionError("read loop did not give up")
            return header

    es.serial.Serial = FakeSerialCtx
    done, rows, malloc_failed, note = es.read_serial_trials("/dev/fake", "grover", 8, 90)
    check("wdt loop: not done, no rows", done is False and rows == [], (done, rows))
    check("wdt loop: note flags watchdog_reset_loop after 4 boots", "watchdog_reset_loop=true" in note
          and state["reads"] == es.WDT_LOOP_RESETS + 1, (note, state["reads"]))


def test_skipped_point_gets_prediction(scratch: Path):
    """1 rep > 2 h (grover n=11): not run, but predicted.csv carries an ESTIMATE row; raw.csv stays as is."""
    es, tel, sp, rs, tm = _fresh_esp8266_sweep(scratch)
    # measured grover n=6, 8 (median = 2 x model) to calibrate the prediction
    raw = sp.raw_csv_path("esp8266", "grover")
    raw.parent.mkdir(parents=True, exist_ok=True)
    with open(raw, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "rep", "exec_time_us", "free_heap_before", "free_heap_after", "timeout_budget_s"])
        for n in (6, 8):
            for rep in range(3):
                w.writerow(["esp8266", "grover", n, rep, 2.0 * tm.expected_exec_time_us("esp8266", "grover", n), 1, 1, 90])
    with open(sp.memory_wall_csv_path("esp8266", "grover"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["board", "circuit", "n", "theoretical_bytes", "compile_ram_used_bytes", "compile_ram_pct",
                    "status", "timestamp_utc", "retry_count", "timeout_budget_s", "expected_point_s", "retry_policy"])
        for n in (6, 8):  # terminal records, so resume keeps the raw rows instead of purging them as orphans
            w.writerow(["esp8266", "grover", n, 8 << n, "", "", "ok", "2026-10-05T00:00:00+00:00", 0, 90, 1, "allowed"])
    _run(es, ["grover"], 11, 11)
    pred_path = sp.predicted_csv_path("esp8266", "grover")
    check("skipped point: predicted.csv written", pred_path.exists())
    rows = list(csv.DictReader(open(pred_path))) if pred_path.exists() else []
    r = rows[0] if rows else {}
    check("predicted row: n=11, ESTIMATE_not_measured, 0 reps fit",
          r.get("n") == "11" and r.get("kind") == "ESTIMATE_not_measured" and r.get("max_reps_in_cap") == "0", r)
    check("predicted row: calibrated x2 from measured n=6 8",
          bool(r) and abs(float(r["calibration_ratio"]) - 2.0) < 1e-3 and r["calibration_n"] == "6 8", r)
    check("predicted row: used = 2 x model",
          bool(r) and abs(float(r["per_rep_used_us"]) / float(r["per_rep_model_us"]) - 2.0) < 1e-3, r)
    check("raw.csv unchanged (no fake measurement rows)", len(_raw_rows(sp, "grover")) == 6)
    wall = _wall_rows(sp, "grover")
    check("memory_wall.csv: skipped_compute_infeasible", bool(wall) and wall[-1]["status"] == "skipped_compute_infeasible", wall)
    _run(es, ["grover"], 11, 11)
    check("rerun does not duplicate the prediction row", len(list(csv.DictReader(open(pred_path)))) == 1)


def test_manual_stop_and_resume_round_trip(scratch: Path):
    es, tel, sp, rs, tm = _fresh_esp8266_sweep(scratch)

    def fake_stop(port, circuit, n, timeout_s, **kwargs):
        rows = [f"esp8266,{circuit},{n},{r},100,1000,1000" for r in range(43)]
        return None, rows, False, "operator_stop"
    es.read_serial_trials = fake_stop

    code = None
    try:
        _run(es, ["h_all"], 2, 2)
    except SystemExit as e:
        code = e.code
    check("manual stop: exits 130", code == 130, code)

    wall = _wall_rows(sp, "h_all")
    row = [r for r in wall if r["circuit"] == "h_all" and r["n"] == "2"][0]
    check("manual stop: status stopped_by_operator(reps_completed=43)",
          row["status"] == "stopped_by_operator(reps_completed=43)", row["status"])
    raw = _raw_rows(sp, "h_all")
    reps = sorted(int(r["rep"]) for r in raw)
    check("manual stop: 43 raw rows, rep 0..42", reps == list(range(43)), reps[-3:])

    def fake_complete(port, circuit, n, timeout_s, **kwargs):
        rows = [f"esp8266,{circuit},{n},{r},100,1000,1000" for r in range(100)]
        return True, rows, False, "reset_count=0"
    es.read_serial_trials = fake_complete
    _run(es, ["h_all"], 2, 2)

    wall = _wall_rows(sp, "h_all")
    row = [r for r in wall if r["circuit"] == "h_all" and r["n"] == "2"][-1]
    check("resume: final status ok", row["status"] == "ok", row["status"])
    raw = _raw_rows(sp, "h_all")
    reps = sorted(int(r["rep"]) for r in raw)
    check("resume: 100 raw rows total, rep 0..99 no gaps/dupes",
          reps == list(range(100)), (len(reps), reps[:3], reps[-3:]))


def main():
    scratch_root = Path(tempfile.mkdtemp(prefix="esp8266_manual_stop_test_"))
    try:
        test_ceiling_no_longer_caps_esp8266()
        test_read_serial_trials_catches_keyboardinterrupt_keeps_rows()
        test_time_cap_stops_collection()
        test_watchdog_reset_loop_gives_up()
        test_skipped_point_gets_prediction(scratch_root / "skipped")
        test_manual_stop_and_resume_round_trip(scratch_root / "round_trip")
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)

    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\n{len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
