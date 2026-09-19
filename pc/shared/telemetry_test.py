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
sys.path.insert(0, str(REPO_ROOT / "pc" / "phase3_offload"))

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
        sess.note_point(device_s=0.0, reflash_s=0.0, status="skipped_compute_infeasible")
        sess.note_point(device_s=0.0, reflash_s=0.0, status="skipped_resume")
        sess.note_point(device_s=0.0, reflash_s=0.0, status="skipped_known_wall")
        sess.note_point(device_s=0.0, reflash_s=0.0, status="skipped_sim_cost_infeasible")

    rows = list(csv.DictReader(open(sessions_csv)))
    check("session: exactly 1 row written", len(rows) == 1)
    r = rows[0]
    check("session: schema_version=1", r["schema_version"] == "1")
    check("session: device_time_s_sum aggregated correctly", abs(float(r["device_time_s_sum"]) - 1.2) < 1e-6)
    check("session: reflash_time_s_sum aggregated correctly", abs(float(r["reflash_time_s_sum"]) - 40.0) < 1e-6)
    check("session: n_points_ok=1", r["n_points_ok"] == "1")
    check("session: n_points_failed=1", r["n_points_failed"] == "1")
    check("session: n_points_skipped_resume=1", r["n_points_skipped_resume"] == "1")
    check("session: n_points_skipped_known_wall=1", r["n_points_skipped_known_wall"] == "1")
    check("session: n_points_skipped_compute_infeasible=1", r["n_points_skipped_compute_infeasible"] == "1")
    check("session: n_points_skipped_sim_cost_infeasible=1", r["n_points_skipped_sim_cost_infeasible"] == "1")

    tel.write_point_row({
        "session_id": "test123", "phase": 2, "board": "uno", "circuit": "grover", "n": 6,
        "attempt_index": 0, "start_utc": "t0", "end_utc": "t1", "wall_s": 5.0,
        "build_compile_s": 3.0, "upload_s": 2.0, "boot_wait_s": 1.0,
        "device_exec_s": 4.9, "retry_count": 0, "timeout_hit": False,
        "failure_type": "none", "status": "ok",
    }, points_csv=points_csv)
    prows = list(csv.DictReader(open(points_csv)))
    check("point: 1 row written", len(prows) == 1)
    check("point: schema_version=1", prows[0]["schema_version"] == "1")
    check("point: unspecified fields blank, not 0", prows[0]["pc_sim_s_total"] == "")
    check("point: field order matches POINT_FIELDS", list(prows[0].keys()) == tel.POINT_FIELDS)

    try:
        tel.write_point_row({"bogus_field": 1}, points_csv=points_csv)
        check("point: unknown field raises ValueError", False)
    except ValueError:
        check("point: unknown field raises ValueError", True)

    try:
        tel.write_point_row({"status": "skipped"}, points_csv=points_csv)
        check("point: invalid status ('skipped', pre-freeze value) raises ValueError", False)
    except ValueError:
        check("point: invalid status ('skipped', pre-freeze value) raises ValueError", True)

    try:
        tel.write_point_row({"status": "ok", "failure_type": "bogus"}, points_csv=points_csv)
        check("point: invalid failure_type raises ValueError", False)
    except ValueError:
        check("point: invalid failure_type raises ValueError", True)

    for valid_status in tel.STATUS_TYPES:
        tel.write_point_row({"status": valid_status}, points_csv=points_csv)
    prows_after_valid = list(csv.DictReader(open(points_csv)))
    check(f"point: all {len(tel.STATUS_TYPES)} STATUS_TYPES values accepted without error",
          len(prows_after_valid) == 1 + len(tel.STATUS_TYPES), len(prows_after_valid))

    # schema mismatch on an old-header file must refuse, not silently misalign columns
    old_schema_points_csv = scratch / "old_schema_points.csv"
    with open(old_schema_points_csv, "w", newline="") as f:
        csv.writer(f).writerow(["session_id", "phase", "board"])  # ไม่มี schema_version เลย
    try:
        tel.write_point_row({"status": "ok"}, points_csv=old_schema_points_csv)
        check("point: appending to an old-schema file raises SchemaMismatchError", False)
    except tel.SchemaMismatchError:
        check("point: appending to an old-schema file raises SchemaMismatchError", True)

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
    check("environment metadata has schema_version=1", meta["schema_version"] == 1)
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
    check("dry-run resume: n_points_skipped_resume=2", sess2[1]["n_points_skipped_resume"] == "2")
    pts2 = list(csv.DictReader(open(tel.POINTS_CSV)))
    check("dry-run resume: 2 more point rows appended for the resumed skips (4 total)",
          len(pts2) == 4, len(pts2))
    check("dry-run resume: the new rows carry status=skipped_resume",
          pts2[2]["status"] == "skipped_resume" and pts2[3]["status"] == "skipped_resume",
          (pts2[2]["status"], pts2[3]["status"]))


def test_phase3_crc_vs_serial_dry_run(scratch: Path):
    """เอกสารประกอบการตัดสินใจ (2026-09-20, run_checklist.md ส่วน 'Telemetry schema'):
    CRC error กับความล้มเหลวของสาย/พอร์ตแยกไม่ออกด้วย exchange logic ปัจจุบันของ Phase 3
    — จำลอง session_incomplete ที่มี crc_error_count > 0 (dropped=5) แล้วยืนยันว่า
    failure_type ที่บันทึกยังคงเป็น "serial" ไม่ใช่ "crc" (การเดาจาก crc_error_count > 0
    ว่าเป็นสาเหตุจะให้ข้อมูลที่ดูน่าเชื่อถือแต่อาจผิด — ไม่ implement การเดานั้น) เทสต์นี้
    เป็น regression guard: ถ้าใครมาแก้ให้เดา failure_type จาก crc_error_count ทีหลังโดย
    ไม่ได้แก้ exchange logic ให้แยกสาเหตุได้จริงก่อน เทสต์นี้จะ fail"""
    import importlib
    import sweep as p3
    importlib.reload(p3)
    from shared import telemetry as tel

    sweep_dir = scratch / "phase3_dry_run"
    sweep_dir.mkdir(parents=True)
    p3.RESULTS_DIR = sweep_dir
    tel.TELEMETRY_DIR = sweep_dir / "telemetry"
    tel.SESSIONS_CSV = tel.TELEMETRY_DIR / "sessions.csv"
    tel.POINTS_CSV = tel.TELEMETRY_DIR / "points.csv"
    tel.ENV_DIR = tel.TELEMETRY_DIR / "env"

    def fake_build_and_upload(board, circuit, n, baud, port_hint):
        return {"ok": True, "port": "/dev/fake", "compile_s": 1.0, "upload_s": 1.0, "log": ""}

    def fake_find_port(board, hint):
        return "/dev/fake"

    def fake_run_offload_session(ser, sim, session_timeout_s):
        # session_incomplete (done=False, 0 rows) แต่มี crc_error_count>0 (dropped=5) —
        # กรณีตรงที่แยกสาเหตุไม่ได้ตามที่บันทึกไว้
        return False, [], 0, 5, "", [], 24

    class FakeSerial:
        def __init__(self, *a, **k):
            self.dtr = True
            self.rts = True

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def reset_input_buffer(self):
            pass

    p3.build_and_upload = fake_build_and_upload
    p3.find_port = fake_find_port
    p3.run_offload_session = fake_run_offload_session
    p3.serial.Serial = FakeSerial

    sys.argv = ["sweep.py", "--board", "esp8266", "--port", "/dev/fake",
                "--circuits", "h_all", "--n-start", "2", "--n-max", "2"]
    p3.main()

    pts = list(csv.DictReader(open(tel.POINTS_CSV)))
    check("phase3 crc-vs-serial: 1 point row written", len(pts) == 1, len(pts))
    check("phase3 crc-vs-serial: status=failed (session_incomplete mapped for points.csv's enum)",
          pts[0]["status"] == "failed", pts[0]["status"])
    check("phase3 crc-vs-serial: crc_error_count recorded (5) even though failure_type stays serial",
          pts[0]["crc_error_count"] == "5", pts[0]["crc_error_count"])
    check("phase3 crc-vs-serial: failure_type is 'serial', NOT 'crc' (cannot be separated, documented)",
          pts[0]["failure_type"] == "serial", pts[0]["failure_type"])


def main():
    scratch = Path(tempfile.mkdtemp(prefix="telemetry_test_"))
    real_data_dir = REPO_ROOT / "data" / "raw" / "telemetry"
    before = set(real_data_dir.glob("**/*")) if real_data_dir.exists() else set()
    try:
        test_schema_and_append(scratch / "case1")
        test_module_attribute_reassignment_respected(scratch / "case2")
        test_mocked_uno_sweep_dry_run(scratch / "case3")
        test_phase3_crc_vs_serial_dry_run(scratch / "case4")
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
