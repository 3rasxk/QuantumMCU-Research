#!/usr/bin/env python3
# esp32_manual_stop_test.py — lighter port of uno_manual_stop_test.py for
# esp32_sweep.py (2026-09-22 standing decision: ceiling removed, ETA/progress
# printing, operator manual stop, resumable partial reps). esp32's raw.csv
# has an extra largest_block column vs esp8266's, but rep stays at index 3.

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


def _fresh_esp32_sweep(scratch: Path):
    import importlib
    import esp32_sweep as es
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
    sys.argv = ["esp32_sweep.py", "--port", "/dev/fake",
                "--circuits", *circuits,
                "--n-start", str(n_start), "--n-max", str(n_max),
                "--upload-retry-settle-s", "0"]
    es.main()


def _wall_rows(sp, circuit):
    return list(csv.DictReader(open(sp.memory_wall_csv_path("esp32", circuit))))


def _raw_rows(sp, circuit):
    return list(csv.DictReader(open(sp.raw_csv_path("esp32", circuit))))


def _rows_for(circuit, n, n_rows):
    # esp32 raw line: board,circuit,n,rep,exec_time_us,free_heap_before,
    # free_heap_after,largest_block (8 fields; budget_s appended by the sweep)
    return [f"esp32,{circuit},{n},{r},100,1000,1000,900" for r in range(n_rows)]


def test_ceiling_no_longer_caps_esp32():
    from shared import timing_model as tm
    budget = tm.timeout_budget_s("esp32", "grover", 14)
    check("timeout_budget_s no longer clamped at old 14400s ceiling",
          budget > 14400, budget)
    check("is_compute_infeasible always False now",
          tm.is_compute_infeasible("esp32", "grover", 14) is False)


def test_read_serial_trials_catches_keyboardinterrupt_keeps_rows():
    import esp32_sweep as es
    import importlib
    importlib.reload(es)

    lines = [
        b"esp32,h_all,2,0,100,1000,1000,900\r\n",
        b"esp32,h_all,2,1,100,1000,1000,900\r\n",
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
    check("manual stop: note says operator_stop", note == "operator_stop", note)


def test_manual_stop_and_resume_round_trip(scratch: Path):
    es, tel, sp, rs, tm = _fresh_esp32_sweep(scratch)

    def fake_stop(port, circuit, n, timeout_s, **kwargs):
        return None, _rows_for(circuit, n, 43), False, "operator_stop"
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
        return True, _rows_for(circuit, n, 100), False, "reset_count=0"
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
    scratch_root = Path(tempfile.mkdtemp(prefix="esp32_manual_stop_test_"))
    try:
        test_ceiling_no_longer_caps_esp32()
        test_read_serial_trials_catches_keyboardinterrupt_keeps_rows()
        test_manual_stop_and_resume_round_trip(scratch_root / "round_trip")
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)

    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\n{len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
