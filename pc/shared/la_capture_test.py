#!/usr/bin/env python3
# la_capture_test.py — self-contained tests for the opt-in `--la` flag added to
# pc/phase2_sweep/uno_sweep.py (pc/shared/la_capture.py) covering exactly the
# four cases called for in docs/preflight_report.md / run_checklist.md's
# Logic Analyzer procedure:
#   1. --la off -> zero calls into la_capture, output unchanged
#   2. --la on, sigrok-cli present, clean capture -> arm/stop/analyze wired
#      correctly and in the right order relative to build/upload
#   3. --la on, sigrok-cli missing -> continues WITHOUT capture, output
#      unchanged from (1)
#   4. --la on, capture fails (sigrok error / stop_capture returns False) ->
#      the point's micros() data (raw/wall CSV rows) is byte-for-byte
#      unaffected, no analysis is run on a bad capture
#
# ไม่ใช้ pytest (ตามรูปแบบเดียวกับ pc/shared/telemetry_test.py และ analysis/la_test.py)
# รันด้วย: .venv/bin/python pc/shared/la_capture_test.py
#
# หมายเหตุการ mock: ใช้รูปแบบเดียวกับ
# telemetry_test.py::test_mocked_uno_sweep_dry_run — reload uno_sweep, ชี้
# paths.REPO_ROOT ไปที่ scratch dir (จุดเดียวที่ต้อง redirect ตั้งแต่ 2026-09-20,
# ดู pc/shared/paths.py) แล้ว monkeypatch build_and_upload/read_serial_trials/
# lac.* เป็นฟังก์ชันปลอมทั้งหมด ไม่แตะฮาร์ดแวร์หรือ data/raw/ ของจริงเลย

import csv
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
sys.path.insert(0, str(REPO_ROOT / "pc" / "phase2_sweep"))

RESULTS = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    RESULTS.append((name, status))
    print(f"[{status}] {name}  {detail}")


def _fresh_uno_sweep(scratch: Path):
    """Reload uno_sweep + telemetry with paths pointed at a scratch dir, exactly
    like telemetry_test.py's mocked dry-run harness."""
    import importlib
    import uno_sweep as us
    importlib.reload(us)
    from shared import telemetry as tel
    from shared import la_capture as lac
    from shared import paths as sp

    sweep_dir = scratch
    sweep_dir.mkdir(parents=True, exist_ok=True)
    sp.REPO_ROOT = sweep_dir
    return us, tel, lac, sp


def _install_fake_build_and_upload(us, order):
    def fake_build_and_upload(circuit, n, port_hint, build_timeout_s=None):
        order.append(("build_and_upload", circuit, n))
        return {"ok": True, "ram_pct": 11.4, "ram_bytes": 234, "log": "",
                "port": "/dev/fake", "compile_s": 4.61, "upload_s": 5.68}
    us.build_and_upload = fake_build_and_upload
    us.find_uno_port = lambda hint: "/dev/fake"


def _install_fake_read_serial_trials(us, order, done=True, n_rows=100):
    def fake_read_serial_trials(port, circuit, n, timeout_s):
        order.append(("read_serial_trials", circuit, n))
        rows = [f"uno,{circuit},{n},{r},284,1780,1780" for r in range(n_rows)]
        return done, rows, "reset_count=0"
    us.read_serial_trials = fake_read_serial_trials


def _run(us, la: bool):
    sys.argv = ["uno_sweep.py", "--port", "/dev/fake", "--circuits", "h_all",
                "--n-start", "2", "--n-max", "2"]
    if la:
        sys.argv.append("--la")
    us.main()


def _rows_no_timestamp(path: Path, ts_cols):
    """CSV rows with volatile timestamp columns blanked out, for comparing two
    separate runs that are otherwise expected to produce identical data."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        r = dict(r)
        for c in ts_cols:
            r.pop(c, None)
        out.append(r)
    return out


WALL_TS_COLS = ["timestamp_utc"]
POINTS_TS_COLS = ["session_id", "start_utc", "end_utc"]
SESSIONS_TS_COLS = ["session_id", "start_utc", "end_utc", "env_json_path"]


def test_flag_off_zero_la_calls(scratch: Path):
    us, tel, lac, sp = _fresh_uno_sweep(scratch / "off")
    order = []
    _install_fake_build_and_upload(us, order)
    _install_fake_read_serial_trials(us, order)

    lac_calls = []
    for name in ("check_sigrok", "load_plan_entry", "arm_capture", "stop_capture",
                 "run_analysis", "log_issue"):
        def make(name):
            def f(*a, **kw):
                lac_calls.append(name)
                raise AssertionError(f"lac.{name} must never be called with --la off")
            return f
        setattr(us.lac, name, make(name))

    _run(us, la=False)

    check("flag off: zero calls into la_capture", lac_calls == [], lac_calls)
    raw_rows = list(csv.DictReader(open(sp.raw_csv_path("uno", "h_all"))))
    check("flag off: 100 raw rows written", len(raw_rows) == 100, len(raw_rows))
    wall_rows = list(csv.DictReader(open(sp.memory_wall_csv_path("uno", "h_all"))))
    check("flag off: wall status=ok", wall_rows[0]["status"] == "ok", wall_rows[0]["status"])
    return raw_rows, wall_rows


def test_flag_on_missing_sigrok_matches_baseline(scratch: Path, baseline_raw, baseline_wall):
    us, tel, lac, sp = _fresh_uno_sweep(scratch / "missing_sigrok")
    order = []
    _install_fake_build_and_upload(us, order)
    _install_fake_read_serial_trials(us, order)

    lac.check_sigrok = lambda: {"available": False, "driver": None,
                                 "note": "sigrok-cli not found on PATH"}
    for name in ("load_plan_entry", "arm_capture", "stop_capture", "run_analysis"):
        def make(name):
            def f(*a, **kw):
                raise AssertionError(f"lac.{name} must not be called when sigrok is unavailable")
            return f
        setattr(lac, name, make(name))
    issues = []
    lac.log_issue = lambda *a, **kw: issues.append(a)

    _run(us, la=True)

    raw_rows = list(csv.DictReader(open(sp.raw_csv_path("uno", "h_all"))))
    wall_rows = list(csv.DictReader(open(sp.memory_wall_csv_path("uno", "h_all"))))
    check("missing sigrok: continues without capture (no crash, no la_* calls)", True)
    check("missing sigrok: raw rows match flag-off baseline",
          raw_rows == baseline_raw, "mismatch" if raw_rows != baseline_raw else "")
    check("missing sigrok: wall status matches flag-off baseline",
          [dict(w, timestamp_utc="") for w in wall_rows]
          == [dict(w, timestamp_utc="") for w in baseline_wall])
    check("missing sigrok: no capture issues logged (missing sigrok isn't a capture failure)",
          issues == [], issues)


def test_flag_on_clean_capture(scratch: Path, baseline_raw, baseline_wall):
    us, tel, lac, sp = _fresh_uno_sweep(scratch / "clean_capture")
    order = []
    _install_fake_build_and_upload(us, order)
    _install_fake_read_serial_trials(us, order)

    lac.check_sigrok = lambda: {"available": True, "driver": None, "note": "found demo device"}
    lac.load_plan_entry = lambda board, circuit, n, plan_path=None: {
        "n_reps_to_capture": 100, "recommended_sample_rate_hz": 24_000_000.0}

    armed_obj = SimpleNamespace(out_path=None)

    def fake_arm_capture(board, circuit, n, plan_entry, out_path):
        order.append(("arm_capture", circuit, n))
        armed_obj.out_path = out_path
        return armed_obj
    lac.arm_capture = fake_arm_capture

    def fake_stop_capture(armed, board, circuit, n, timeout_s=15.0):
        order.append(("stop_capture", circuit, n))
        check("clean capture: stop_capture receives the object arm_capture returned",
              armed is armed_obj)
        return True
    lac.stop_capture = fake_stop_capture

    analysis_calls = []

    def fake_run_analysis(board, circuit, n, capture_path, expected_reps):
        order.append(("run_analysis", circuit, n))
        analysis_calls.append((board, circuit, n, capture_path, expected_reps))
        return {"ok": True}
    lac.run_analysis = fake_run_analysis

    issues = []
    lac.log_issue = lambda *a, **kw: issues.append(a)

    _run(us, la=True)

    check("clean capture: order is arm -> build_and_upload -> read_serial_trials -> "
          "stop_capture -> run_analysis",
          [x[0] for x in order] ==
          ["arm_capture", "build_and_upload", "read_serial_trials", "stop_capture", "run_analysis"],
          [x[0] for x in order])
    check("clean capture: run_analysis called once with expected_reps=100",
          len(analysis_calls) == 1 and analysis_calls[0][4] == 100, analysis_calls)
    check("clean capture: no issues logged", issues == [], issues)

    raw_rows = list(csv.DictReader(open(sp.raw_csv_path("uno", "h_all"))))
    wall_rows = list(csv.DictReader(open(sp.memory_wall_csv_path("uno", "h_all"))))
    check("clean capture: raw rows match flag-off baseline (LA wiring doesn't change data)",
          raw_rows == baseline_raw)
    check("clean capture: wall status matches flag-off baseline",
          [dict(w, timestamp_utc="") for w in wall_rows]
          == [dict(w, timestamp_utc="") for w in baseline_wall])


def test_flag_on_capture_failure_does_not_affect_micros_data(scratch: Path, baseline_raw, baseline_wall):
    us, tel, lac, sp = _fresh_uno_sweep(scratch / "capture_fail")
    order = []
    _install_fake_build_and_upload(us, order)
    _install_fake_read_serial_trials(us, order)

    lac.check_sigrok = lambda: {"available": True, "driver": None, "note": "found demo device"}
    lac.load_plan_entry = lambda board, circuit, n, plan_path=None: {
        "n_reps_to_capture": 100, "recommended_sample_rate_hz": 24_000_000.0}
    lac.arm_capture = lambda board, circuit, n, plan_entry, out_path: SimpleNamespace(out_path=out_path)

    def fake_stop_capture(armed, board, circuit, n, timeout_s=15.0):
        return False  # sigrok error / bad capture
    lac.stop_capture = fake_stop_capture

    analysis_calls = []
    lac.run_analysis = lambda *a, **kw: analysis_calls.append(a) or {"ok": False}

    _run(us, la=True)

    raw_rows = list(csv.DictReader(open(sp.raw_csv_path("uno", "h_all"))))
    wall_rows = list(csv.DictReader(open(sp.memory_wall_csv_path("uno", "h_all"))))
    check("capture failure: run_analysis is never called on a failed capture",
          analysis_calls == [], analysis_calls)
    check("capture failure: raw (micros()) data unaffected, matches flag-off baseline",
          raw_rows == baseline_raw)
    check("capture failure: point still recorded status=ok (build/device outcome unaffected)",
          wall_rows[0]["status"] == "ok", wall_rows[0]["status"])
    check("capture failure: wall row otherwise matches flag-off baseline",
          [dict(w, timestamp_utc="") for w in wall_rows]
          == [dict(w, timestamp_utc="") for w in baseline_wall])


def test_flag_on_missing_plan_entry_skips_capture(scratch: Path, baseline_raw):
    """No data/raw/la/capture_plan.csv entry for this point -> log and skip
    capture for it, still complete the point normally (no crash, no guessing)."""
    us, tel, lac, sp = _fresh_uno_sweep(scratch / "no_plan")
    order = []
    _install_fake_build_and_upload(us, order)
    _install_fake_read_serial_trials(us, order)

    lac.check_sigrok = lambda: {"available": True, "driver": None, "note": "found demo device"}
    lac.load_plan_entry = lambda board, circuit, n, plan_path=None: None
    lac.arm_capture = lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("arm_capture must not be called with no plan entry"))
    issues = []
    lac.log_issue = lambda board, circuit, n, message: issues.append(message)

    _run(us, la=True)

    check("no plan entry: capture skipped and logged, point still completes",
          any("no capture_plan.csv entry" in m for m in issues), issues)
    raw_rows = list(csv.DictReader(open(sp.raw_csv_path("uno", "h_all"))))
    check("no plan entry: raw rows still match flag-off baseline", raw_rows == baseline_raw)


def main():
    scratch = Path(tempfile.mkdtemp(prefix="la_capture_test_"))
    try:
        baseline_raw, baseline_wall = test_flag_off_zero_la_calls(scratch)
        test_flag_on_missing_sigrok_matches_baseline(scratch, baseline_raw, baseline_wall)
        test_flag_on_clean_capture(scratch, baseline_raw, baseline_wall)
        test_flag_on_capture_failure_does_not_affect_micros_data(scratch, baseline_raw, baseline_wall)
        test_flag_on_missing_plan_entry_skips_capture(scratch, baseline_raw)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\n{len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
