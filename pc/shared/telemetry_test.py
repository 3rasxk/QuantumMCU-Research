#!/usr/bin/env python3
# telemetry_test.py — self-contained tests for pc/shared/telemetry.py: schema
# validation, append/resume behavior, and a mocked dry-run of one full sweep
# script (uno_sweep.py) with build/upload and serial I/O mocked out.
#
# ไม่ใช้ pytest (repo นี้ไม่มี test infra อยู่ก่อน) — ใช้รูปแบบเดียวกับ self-test ท้าย
# pc/shared/timing_model.py: รันตรง ๆ แล้วอ่าน PASS/FAIL จาก stdout, exit code != 0
# ถ้ามี FAIL
#
# รันด้วย: .venv/bin/python pc/shared/telemetry_test.py
#
# เขียนไฟล์ทดสอบทั้งหมดลง scratch dir ชั่วคราว (tempfile) — ไม่แตะ data/raw/ ของจริง
# เด็ดขาด (บั๊กที่เคยเจอระหว่างพัฒนา: ใช้ default parameter value ที่ bind ตอน def แทน
# ตอนเรียก ทำให้ reassign module attribute แล้วไม่มีผล ต้อง regression-test ไว้ด้วย —
# ดู case "module path reassignment" ด้านล่าง)

import csv
import json
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


def test_schema_and_append(scratch: Path):
    from shared import telemetry as tel

    sessions_csv = scratch / "sessions.csv"
    points_csv = scratch / "points.csv"

    with tel.SessionRecorder(phase=2, board="uno", circuits=["h_all", "grover"],
                              resumed_from_previous=False, estimated_total_s=100.0,
                              sessions_csv=sessions_csv) as sess:
        sess.note_point(device_s=1.2, reflash_s=20.0, status="ok")
        sess.note_point(device_s=0.0, reflash_s=20.0, status="failed")
        sess.note_point(device_s=0.0, reflash_s=0.0, status="skipped")
        sess.note_point(device_s=0.0, reflash_s=0.0, status="ok", resumed_skip=True)

    rows = list(csv.DictReader(open(sessions_csv)))
    check("session: exactly 1 row written", len(rows) == 1)
    r = rows[0]
    check("session: device_time_s_sum aggregated correctly", abs(float(r["device_time_s_sum"]) - 1.2) < 1e-6)
    check("session: reflash_time_s_sum aggregated correctly", abs(float(r["reflash_time_s_sum"]) - 40.0) < 1e-6)
    check("session: n_points_ok=1", r["n_points_ok"] == "1")
    check("session: n_points_failed=1", r["n_points_failed"] == "1")
    check("session: n_points_skipped=1", r["n_points_skipped"] == "1")
    check("session: n_points_resumed_skip=1", r["n_points_resumed_skip"] == "1")

    tel.write_point_row({
        "session_id": "test123", "phase": 2, "board": "uno", "circuit": "grover", "n": 6,
        "attempt_index": 0, "start_utc": "t0", "end_utc": "t1", "wall_s": 5.0,
        "build_compile_s": 3.0, "upload_s": 2.0, "boot_wait_s": 1.0,
        "device_exec_s": 4.9, "retry_count": 0, "timeout_hit": False,
        "failure_type": "none", "status": "ok",
    }, points_csv=points_csv)
    prows = list(csv.DictReader(open(points_csv)))
    check("point: 1 row written", len(prows) == 1)
    check("point: unspecified fields blank, not 0", prows[0]["pc_sim_s_total"] == "")
    check("point: field order matches POINT_FIELDS", list(prows[0].keys()) == tel.POINT_FIELDS)

    try:
        tel.write_point_row({"bogus_field": 1}, points_csv=points_csv)
        check("point: unknown field raises ValueError", False)
    except ValueError:
        check("point: unknown field raises ValueError", True)

    # append-only across two sessions (simulates a resume)
    with tel.SessionRecorder(phase=2, board="uno", circuits=["h_all"],
                              resumed_from_previous=True, sessions_csv=sessions_csv) as sess2:
        sess2.note_point(device_s=0.5, reflash_s=20.0, status="ok")
    rows2 = list(csv.DictReader(open(sessions_csv)))
    check("resume: second session APPENDS (2 total rows)", len(rows2) == 2)
    check("resume: first row untouched by second session", rows2[0]["device_time_s_sum"] == "1.2")
    check("resume: second row marked resumed_from_previous=True", rows2[1]["resumed_from_previous"] == "True")

    last_end = tel.last_session_end_utc("uno", 2, sessions_csv=sessions_csv)
    check("last_session_end_utc finds a datetime for a seen board", last_end is not None)
    check("last_session_end_utc returns None for an unseen board",
          tel.last_session_end_utc("esp32", 2, sessions_csv=sessions_csv) is None)

    env_path = tel.write_environment_metadata(
        "envtest123", "uno", "/dev/fake", 115200, 16_000_000,
        REPO_ROOT / "firmware" / "uno" / "src", env_dir=scratch / "env")
    check("environment metadata file created", env_path.exists())
    meta = json.loads(env_path.read_text())
    check("environment metadata has non-empty git_commit", meta["git_commit"] != "")
    check("environment metadata has 16-char firmware_source_hash", len(meta["firmware_source_hash"]) == 16)
    check("environment metadata has sleep_prevention.checked", "checked" in meta["sleep_prevention"])


def test_module_attribute_reassignment_respected(scratch: Path):
    """regression test สำหรับบั๊กที่เจอจริงระหว่างพัฒนา: default parameter ที่ผูกกับ
    module-level path constant ตอน def (`x: Path = SESSIONS_CSV`) จะไม่ตามการ
    reassign `tel.SESSIONS_CSV = ...` ทีหลัง — ต้อง resolve เป็น None แล้ว lookup
    module global ตอนเรียกจริง ดู pc/shared/telemetry.py หัวข้อคอมเมนต์ประกอบ"""
    from shared import telemetry as tel

    redirected = scratch / "redirected"
    tel.SESSIONS_CSV = redirected / "sessions.csv"
    tel.POINTS_CSV = redirected / "points.csv"
    tel.ENV_DIR = redirected / "env"

    with tel.SessionRecorder(phase=2, board="esp32", circuits=["qft"]):
        pass
    check("reassigning tel.SESSIONS_CSV is honored by SessionRecorder's default",
          tel.SESSIONS_CSV.exists(), str(tel.SESSIONS_CSV))

    tel.write_point_row({"session_id": "x", "phase": 2, "board": "esp32", "circuit": "qft",
                          "n": 2, "attempt_index": 0, "status": "ok"})
    check("reassigning tel.POINTS_CSV is honored by write_point_row's default",
          tel.POINTS_CSV.exists(), str(tel.POINTS_CSV))


def test_mocked_uno_sweep_dry_run(scratch: Path):
    """dry-run ของ uno_sweep.py ทั้งไฟล์ — mock build_and_upload/find_uno_port/
    read_serial_trials ไม่แตะฮาร์ดแวร์เลย ยืนยันว่า telemetry ผูกเข้ากับ resume logic
    ที่มีอยู่แล้วถูกต้อง (จุดที่ resume ข้าม ต้องไม่มี build_and_upload ใหม่เกิดขึ้น)"""
    import importlib
    import uno_sweep as us
    importlib.reload(us)  # กัน state ค้างจาก import ก่อนหน้าใน process เดียวกัน
    from shared import telemetry as tel

    sweep_dir = scratch / "uno_dry_run"
    sweep_dir.mkdir(parents=True)
    us.RESULTS_DIR = sweep_dir
    tel.TELEMETRY_DIR = sweep_dir / "telemetry"
    tel.SESSIONS_CSV = tel.TELEMETRY_DIR / "sessions.csv"
    tel.POINTS_CSV = tel.TELEMETRY_DIR / "points.csv"
    tel.ENV_DIR = tel.TELEMETRY_DIR / "env"

    calls = []

    def fake_build_and_upload(circuit, n, port_hint):
        calls.append((circuit, n))
        return {"ok": True, "ram_pct": 50.0, "ram_bytes": 100, "log": "",
                "port": "/dev/fake", "compile_s": 3.5, "upload_s": 2.1}

    def fake_read_serial_trials(port, circuit, n, timeout_s):
        rows = [f"uno,{circuit},{n},{r},999,1000,999" for r in range(100)]
        return True, rows, "reset_count=0"

    us.build_and_upload = fake_build_and_upload
    us.find_uno_port = lambda hint: "/dev/fake"
    us.read_serial_trials = fake_read_serial_trials

    sys.argv = ["uno_sweep.py", "--port", "/dev/fake", "--circuits", "h_all",
                "--n-start", "2", "--n-max", "3"]
    us.main()

    check("dry-run: both points attempted", calls == [("h_all", 2), ("h_all", 3)])
    sess = list(csv.DictReader(open(tel.SESSIONS_CSV)))
    check("dry-run: 1 session row", len(sess) == 1)
    check("dry-run: reflash_time_s_sum = 2*(3.5+2.1)=11.2",
          abs(float(sess[0]["reflash_time_s_sum"]) - 11.2) < 1e-6, sess[0]["reflash_time_s_sum"])
    pts = list(csv.DictReader(open(tel.POINTS_CSV)))
    check("dry-run: 2 point rows (no retries needed)", len(pts) == 2)
    check("dry-run: point rows carry build_compile_s from the mock", pts[0]["build_compile_s"] == "3.5")

    # second invocation: everything should resume-skip, no new hardware calls
    sys.argv = ["uno_sweep.py", "--port", "/dev/fake", "--circuits", "h_all",
                "--n-start", "2", "--n-max", "3"]
    us.main()
    check("dry-run resume: no new build_and_upload calls", len(calls) == 2)
    sess2 = list(csv.DictReader(open(tel.SESSIONS_CSV)))
    check("dry-run resume: second session appended, not overwritten", len(sess2) == 2)
    check("dry-run resume: n_points_resumed_skip=2", sess2[1]["n_points_resumed_skip"] == "2")


def main():
    scratch = Path(tempfile.mkdtemp(prefix="telemetry_test_"))
    real_data_dir = REPO_ROOT / "data" / "raw" / "telemetry"
    before = set(real_data_dir.glob("**/*")) if real_data_dir.exists() else set()
    try:
        test_schema_and_append(scratch / "case1")
        test_module_attribute_reassignment_respected(scratch / "case2")
        test_mocked_uno_sweep_dry_run(scratch / "case3")
    finally:
        after = set(real_data_dir.glob("**/*")) if real_data_dir.exists() else set()
        check("no test run touched the real data/raw/telemetry/ directory", after == before,
              f"new files: {after - before}" if after != before else "")
        shutil.rmtree(scratch, ignore_errors=True)

    n_fail = sum(1 for _, s in RESULTS if s == "FAIL")
    print(f"\nTOTAL: {len(RESULTS)} checks, {n_fail} failed")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
