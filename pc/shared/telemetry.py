# telemetry.py — schema + writers for run-time timing/telemetry, shared by all four
# sweep scripts (uno/esp32/esp8266 Phase 2, offload Phase 3).
#
# ทำไมต้องมีไฟล์นี้: ตัวเลข 13.9 ชั่วโมงใน run_checklist.md เป็น "ค่าประมาณ" ทั้งหมด —
# ตอนนี้ยังไม่มีที่เก็บ "ค่าที่วัดจริง" ระดับ session/data point เลย มีแต่ *_raw.csv
# (ผลการทดลองจริง แต่ไม่มี timestamp เริ่ม/จบ, ไม่แยก compile กับ upload, ไม่มี session
# summary) กับ *_memory_wall.csv/*_session_log.csv (สถานะจบของแต่ละจุด แต่ไม่มี timing
# ละเอียด) — ไฟล์นี้เพิ่มชั้นข้อมูลใหม่ (แยกจากของเดิมทั้งหมด ไม่แก้ schema เดิม เพื่อไม่
# เสี่ยงทำ resume logic ที่ทดสอบแล้วพัง) ให้พอที่จะ:
#   1. แทนที่ REFLASH_COST_S (ประมาณการ) ด้วยค่ามัธยฐานที่วัดจริงหลัง sweep จริงรันไปสักพัก
#   2. เทียบ "ที่ประเมินไว้" กับ "ที่เกิดขึ้นจริง" ต่อ session/algorithm/phase
#   3. วินิจฉัยว่าเวลาที่เสียไปมาจากไหน (compile ช้า? upload ช้า? boot ช้า? รอ retry?)
#
# หลักการออกแบบ (ตรงตามข้อกำหนดที่ตกลงไว้):
#   - append-only เสมอ, flush ทุกแถว (interruption เสียข้อมูลได้อย่างมากแค่ 1 แถว)
#   - ไม่แตะ schema ของ *_raw.csv / *_memory_wall.csv / *_session_log.csv เดิมเลย —
#     resume logic (pc/shared/resume.py) อ่านไฟล์เหล่านั้นเป็นแหล่งความจริงเดียวอยู่แล้ว
#     และผ่านการทดสอบแล้ว การเพิ่มคอลัมน์ใหม่เข้าไปอีกมีความเสี่ยงเกินความจำเป็น
#   - ใช้ time.perf_counter() สำหรับ duration (monotonic, ไม่โดน NTP/system clock เปลี่ยน
#     ระหว่างวัดกวน) และ datetime.now(timezone.utc) สำหรับ timestamp ที่ต้องอ่านเป็นเวลา
#     จริงเท่านั้น — ห้ามเอา perf_counter().to string มาเก็บเป็น "เวลา" เพราะ epoch ของมัน
#     ไม่คงที่ข้าม process
#   - โค้ดจับเวลาทั้งหมดอยู่ "นอก" ฟังก์ชันที่ถูกจับเวลา (main loop ของแต่ละ sweep เรียก
#     ฟังก์ชัน build/upload/read ตามปกติ แล้วครอบด้วย perf_counter ข้างนอก) ไม่แตะโค้ด
#     ภายในฟังก์ชันที่มีผลต่อสิ่งที่ Logic Analyzer / micros() ของ MCU วัดอยู่แล้ว

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import csv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TELEMETRY_DIR = REPO_ROOT / "data" / "raw" / "telemetry"
ENV_DIR = TELEMETRY_DIR / "env"

SESSIONS_CSV = TELEMETRY_DIR / "sessions.csv"
POINTS_CSV = TELEMETRY_DIR / "points.csv"

# ---------------------------------------------------------------------------
# SCHEMA_VERSION — ตัวเลขเดียวที่บอกว่า schema ของ sessions.csv/points.csv/environment
# JSON เวอร์ชันไหน บันทึกไว้ทั้ง 3 ที่ (คอลัมน์แรกของทั้งสอง CSV + field ใน JSON) —
# เพิ่มทุกครั้งที่ field list เปลี่ยน (เพิ่ม/ลบ/เปลี่ยนความหมายคอลัมน์ใด ๆ) ห้าม
# เปลี่ยนความหมายคอลัมน์เดิมโดยไม่เพิ่มเลขนี้ ไม่งั้นไฟล์เก่ากับใหม่จะปนกันโดยไม่มีทาง
# แยกออกจากกันได้ทีหลัง — ดู SchemaMismatchError ด้านล่าง (บังคับด้วยโค้ด ไม่ใช่แค่
# ข้อตกลงในคอมเมนต์) freeze ครั้งแรกที่ tag pre-run-schema-v1 (ดู run_log.md)
# ---------------------------------------------------------------------------
SCHEMA_VERSION = 1


class SchemaMismatchError(RuntimeError):
    """ไฟล์ CSV ที่มีอยู่แล้วมี header ไม่ตรงกับ field list ปัจจุบัน — เกิดได้ถ้า
    SCHEMA_VERSION เปลี่ยนหลังไฟล์ถูกสร้างไปแล้ว การ append ทับแบบเงียบ ๆ จะทำให้
    คอลัมน์เลื่อนไม่ตรงแถว (misaligned) โดยไม่มี error ใด ๆ เตือน — refuse ทันทีดีกว่า
    ปล่อยให้ข้อมูลปนกันแบบตรวจไม่เจอ ผู้ใช้ต้อง archive ไฟล์เก่า (ดู
    pc/shared/resume.archive_existing) หรือเริ่ม telemetry directory ใหม่ก่อนรันต่อ"""


# ---------------------------------------------------------------------------
# schema — คอลัมน์ที่ "ไม่มีข้อมูล" สำหรับแถวนั้น (เช่น field เฉพาะ Phase 3 ในแถว
# Phase 2) ให้เว้นว่างไว้ ไม่ใช่ใส่ 0 หรือ "n/a" — คอลัมน์ว่างอ่านเป็น NULL ตอน
# วิเคราะห์ได้ตรงไปตรงมากว่า
# ---------------------------------------------------------------------------

SESSION_FIELDS = [
    "schema_version",
    "session_id", "phase", "board", "circuits",
    "start_utc", "end_utc", "wall_clock_s",
    "device_time_s_sum", "reflash_time_s_sum",
    "n_points_ok", "n_points_failed",
    "n_points_skipped_resume", "n_points_skipped_known_wall",
    "n_points_skipped_compute_infeasible", "n_points_skipped_sim_cost_infeasible",
    "time_lost_to_interruption_s",
    "estimated_total_s", "actual_total_s", "ratio_actual_over_estimated",
    "resumed_from_previous", "env_json_path", "git_commit", "notes",
]

POINT_FIELDS = [
    "schema_version",
    "session_id", "phase", "board", "circuit", "n", "baud",
    "attempt_index", "start_utc", "end_utc", "wall_s",
    # ---- reflash breakdown (ทั้ง Phase 2 และ Phase 3 — ดู session_total_s ใน
    # timing_model.py: ทั้งสอง phase reflash ต่อจุดเหมือนกัน) ----
    "build_compile_s", "upload_s", "boot_wait_s",
    # ---- device-side execution ----
    "device_exec_s",           # เวลารวมที่บอร์ดใช้จริงกับจุดนี้ (100 rep รวมกัน, Phase 2)
    # ---- Phase 3 only ----
    "pc_sim_s_total", "pc_sim_s_median", "serial_transfer_s_total",
    "avg_round_trip_latency_s", "crc_error_count", "bytes_transferred",
    # ---- outcome ----
    "retry_count", "timeout_hit", "failure_type", "failure_message", "status",
]

# "crc" มีไว้ในตารางนี้เป็น value ที่ *เป็นไปได้ในหลักการ* เท่านั้น — โค้ดปัจจุบันของ
# pc/phase3_offload/sweep.py (จุดเดียวที่ใช้ CRC เลย) ไม่เคย set ค่านี้จริง เพราะแยกไม่
# ออกระหว่าง "session ล้มเหลวเพราะ CRC error พังจนหมดเวลา" กับ "session ล้มเหลวเพราะ
# สาย/พอร์ตหลุดโดยไม่เกี่ยว CRC เลย" — ทั้งสองกรณีจบด้วย status=session_incomplete /
# timeout เหมือนกันทุกประการจากมุมมองของ event loop ปัจจุบัน (ดู sweep.py:460 กับ
# comment ประกอบตรง crc_error_count) ต้องเพิ่ม logic แยกแยะสาเหตุตอนจบ session
# (เช่น "consecutive CRC error ก่อนหมดเวลา" หรือให้ MCU รายงานสาเหตุตอน timeout) ถึง
# จะ set ค่านี้ได้อย่างมีความหมายจริง ไม่ใช่แค่เดาจาก crc_error_count > 0 (ตัวเลขนั้น
# เป็น cumulative ทั้ง session ไม่ได้บอกว่า CRC error เป็น "สาเหตุสุดท้าย" ที่ทำให้ค้าง)
# — ตัดสินใจไว้ตรงนี้: ปล่อย failure_type="serial" ไว้เหมือนเดิมสำหรับทุก
# session_incomplete ไม่เดา แม้ crc_error_count จะสูงก็ตาม
FAILURE_TYPES = ("none", "build", "malloc", "hang", "serial", "crc", "sim")

# points.csv status — ต้องแยกเหตุผลการข้ามแต่ละแบบให้ชัด ไม่ยุบรวมเป็น "skipped"
# เฉย ๆ (ก่อนหน้านี้ทำแบบนั้น ทำให้อ่าน points.csv อย่างเดียวแยกไม่ออกว่าข้ามเพราะอะไร
# ต้องไปเปิด *_memory_wall.csv/*_session_log.csv ประกอบทุกครั้ง) "retrying" คือสถานะ
# ของ attempt ที่ยังไม่ใช่ผลสุดท้าย (retry-once policy, attempt_index 0 ที่กำลังจะลอง
# ซ้ำ) ไม่ใช่ terminal status ของจุดข้อมูล
STATUS_TYPES = (
    "ok", "failed", "retrying",
    "skipped_resume", "skipped_known_wall",
    "skipped_compute_infeasible", "skipped_sim_cost_infeasible",
)


def new_session_id() -> str:
    """timestamp + short random suffix — เรียงตามเวลาได้ตรง ๆ เวลา ls ไฟล์ env/"""
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _ensure_csv(path: Path, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    if not is_new:
        with open(path, newline="") as rf:
            existing_header = next(csv.reader(rf), None)
        if existing_header is not None and existing_header != list(fields):
            raise SchemaMismatchError(
                f"{path} has header {existing_header} but the current schema "
                f"(SCHEMA_VERSION={SCHEMA_VERSION}) expects {list(fields)} — refusing to "
                f"append (would silently misalign columns). Archive the old file "
                f"(see pc/shared/resume.archive_existing) or move it aside before continuing."
            )
    f = open(path, "a", newline="")
    if is_new:
        csv.writer(f).writerow(fields)
        f.flush()
    return f


def _write_row(path: Path, fields, row: dict):
    """เขียน 1 แถว + flush ทันที — สอดคล้องกับ constraint ที่ว่า interruption ต้องเสีย
    ข้อมูลได้อย่างมากแค่ 1 แถว ไม่ใช่ทั้ง buffer ที่ยังไม่ flush"""
    f = _ensure_csv(path, fields)
    try:
        csv.writer(f).writerow([row.get(k, "") for k in fields])
        f.flush()
    finally:
        f.close()


def write_point_row(row: dict, points_csv: Path = None):
    """แถวเดียวต่อจุดข้อมูลต่อ attempt (attempt_index แยก retry ออกจากกันชัดเจน —
    ต่างจาก *_memory_wall.csv ที่รวมทุก attempt เป็นแถวเดียว: ที่นี่ต้องแยกเพื่อดูว่า
    compile/upload/boot ของแต่ละ attempt ใช้เวลาเท่าไหร่จริง ๆ)

    ค่า default ของทุกฟิลด์ที่ไม่ส่งมาคือ "" (ว่าง) ไม่ใช่ 0/None — เขียน CSV แล้วอ่านง่าย
    schema_version ใส่ให้อัตโนมัติเสมอ (caller ไม่ต้องรู้จัก SCHEMA_VERSION) status และ
    failure_type ถ้าระบุมาต้องอยู่ใน STATUS_TYPES/FAILURE_TYPES เท่านั้น

    points_csv=None แปลว่า resolve เป็น module-level POINTS_CSV "ตอนเรียก" ไม่ใช่ตอน
    def — ทำให้ทดสอบ redirect path ด้วยการ monkeypatch `telemetry.POINTS_CSV` ได้จริง
    (ถ้าใช้ `points_csv: Path = POINTS_CSV` เป็น default โดยตรง ค่าจะถูก bind ตอน def
    ครั้งเดียว เปลี่ยน module attribute ทีหลังจะไม่มีผลกับ default นี้อีก — เจอบั๊กนี้จริง
    ระหว่างเขียน integration test จึงแก้เป็นรูปแบบนี้)"""
    if points_csv is None:
        points_csv = POINTS_CSV
    missing = set(row) - set(POINT_FIELDS)
    if missing:
        raise ValueError(f"unknown point field(s): {sorted(missing)}")
    status = row.get("status")
    if status and status not in STATUS_TYPES:
        raise ValueError(f"invalid status {status!r}, must be one of {STATUS_TYPES}")
    failure_type = row.get("failure_type")
    if failure_type and failure_type not in FAILURE_TYPES:
        raise ValueError(f"invalid failure_type {failure_type!r}, must be one of {FAILURE_TYPES}")
    row = {**row, "schema_version": SCHEMA_VERSION}
    _write_row(points_csv, POINT_FIELDS, row)


def write_session_row(row: dict, sessions_csv: Path = None):
    if sessions_csv is None:
        sessions_csv = SESSIONS_CSV
    missing = set(row) - set(SESSION_FIELDS)
    if missing:
        raise ValueError(f"unknown session field(s): {sorted(missing)}")
    row = {**row, "schema_version": SCHEMA_VERSION}
    _write_row(sessions_csv, SESSION_FIELDS, row)


# ---------------------------------------------------------------------------
# SessionRecorder — context manager ที่รวบยอดตัวเลขระดับ session แล้วเขียน 1 แถว
# ตอนจบ (append เสมอ ไม่เคยเขียนทับ — session แต่ละครั้ง = 1 แถวใหม่ แม้จะเป็นการ
# resume ต่อจาก session ก่อนหน้าก็ตาม เพราะแต่ละ session คือการรัน process จริงหนึ่งครั้ง
# ไม่ใช่ "จุดข้อมูล" ที่ resume จะไปนับซ้ำ)
# ---------------------------------------------------------------------------

class SessionRecorder:
    def __init__(self, phase, board, circuits, resumed_from_previous=False,
                 estimated_total_s=None, sessions_csv: Path = None,
                 env_json_path=""):
        self.session_id = new_session_id()
        self.phase = phase
        self.board = board
        self.circuits = ";".join(circuits)
        self.resumed_from_previous = resumed_from_previous
        self.estimated_total_s = estimated_total_s
        self.sessions_csv = sessions_csv
        self.env_json_path = env_json_path
        self.device_time_s_sum = 0.0
        self.reflash_time_s_sum = 0.0
        self.n_ok = self.n_failed = 0
        self.n_skipped_resume = self.n_skipped_known_wall = 0
        self.n_skipped_compute_infeasible = self.n_skipped_sim_cost_infeasible = 0
        self.time_lost_to_interruption_s = 0.0
        self._t0 = None
        self._start_utc = None

    def __enter__(self):
        self._t0 = time.perf_counter()
        self._start_utc = datetime.now(timezone.utc).isoformat()
        return self

    def note_point(self, device_s=0.0, reflash_s=0.0, status="ok"):
        """เรียกครั้งเดียวต่อจุดข้อมูล (ไม่ใช่ต่อ attempt) หลังรู้ผลสุดท้ายของจุดนั้นแล้ว
        status ต้องเป็นค่า terminal จาก telemetry.STATUS_TYPES ("retrying" ไม่ใช่ terminal
        จึงไม่ควรถูกส่งมาที่นี่) skipped_resume/skipped_known_wall/
        skipped_compute_infeasible/skipped_sim_cost_infeasible นับแยกกันคนละตัวนับ
        (เดิมยุบรวมเป็น n_resumed_skip/n_skipped สองก้อน ทำให้ session summary
        แยกเหตุผลการข้ามไม่ได้ — ดู SCHEMA_VERSION 1 freeze)"""
        self.device_time_s_sum += device_s
        self.reflash_time_s_sum += reflash_s
        if status == "ok":
            self.n_ok += 1
        elif status == "skipped_resume":
            self.n_skipped_resume += 1
        elif status == "skipped_known_wall":
            self.n_skipped_known_wall += 1
        elif status == "skipped_compute_infeasible":
            self.n_skipped_compute_infeasible += 1
        elif status == "skipped_sim_cost_infeasible":
            self.n_skipped_sim_cost_infeasible += 1
        else:
            self.n_failed += 1

    def note_interruption_gap(self, seconds):
        """ถ้า session นี้เป็น resume ต่อ ให้เรียกด้วยช่องว่างเวลา (วินาที) ระหว่างแถว
        สุดท้ายของ session ก่อนหน้ากับตอนเริ่ม session นี้ — คือ "เวลาที่เสียไปเฉย ๆ"
        ระหว่างรอแก้ปัญหา/เสียบสาย/นอนหลับ ไม่ใช่เวลาที่ใช้ทำงานจริง"""
        self.time_lost_to_interruption_s += seconds

    def _resolve_sessions_csv(self):
        return self.sessions_csv if self.sessions_csv is not None else SESSIONS_CSV

    def __exit__(self, exc_type, exc, tb):
        wall = time.perf_counter() - self._t0
        end_utc = datetime.now(timezone.utc).isoformat()
        try:
            commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
        except Exception:
            commit = ""
        ratio = (wall / self.estimated_total_s) if self.estimated_total_s else ""
        notes = "" if exc_type is None else f"session ended via exception: {exc_type.__name__}: {exc}"
        write_session_row({
            "session_id": self.session_id, "phase": self.phase, "board": self.board,
            "circuits": self.circuits, "start_utc": self._start_utc, "end_utc": end_utc,
            "wall_clock_s": round(wall, 3),
            "device_time_s_sum": round(self.device_time_s_sum, 3),
            "reflash_time_s_sum": round(self.reflash_time_s_sum, 3),
            "n_points_ok": self.n_ok, "n_points_failed": self.n_failed,
            "n_points_skipped_resume": self.n_skipped_resume,
            "n_points_skipped_known_wall": self.n_skipped_known_wall,
            "n_points_skipped_compute_infeasible": self.n_skipped_compute_infeasible,
            "n_points_skipped_sim_cost_infeasible": self.n_skipped_sim_cost_infeasible,
            "time_lost_to_interruption_s": round(self.time_lost_to_interruption_s, 3),
            "estimated_total_s": self.estimated_total_s or "",
            "actual_total_s": round(wall, 3),
            "ratio_actual_over_estimated": round(ratio, 3) if ratio != "" else "",
            "resumed_from_previous": self.resumed_from_previous,
            "env_json_path": self.env_json_path, "git_commit": commit, "notes": notes,
        }, self._resolve_sessions_csv())
        return False  # ไม่กลืน exception


def last_session_end_utc(board, phase, sessions_csv: Path = None):
    """หา end_utc ของ session ล่าสุดของ (board, phase) นี้ — ใช้คำนวณ
    time_lost_to_interruption_s ตอนเริ่ม session ใหม่ที่เป็นการ resume ต่อ
    คืน None ถ้าไม่เคยมี session ก่อนหน้า (ไฟล์ไม่มี หรือไม่มีแถวที่ตรงเงื่อนไข)"""
    if sessions_csv is None:
        sessions_csv = SESSIONS_CSV
    if not sessions_csv.exists():
        return None
    import csv
    last = None
    with open(sessions_csv, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("board") == board and str(row.get("phase")) == str(phase):
                last = row.get("end_utc") or last
    if not last:
        return None
    try:
        return datetime.fromisoformat(last)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# environment metadata — เขียนครั้งเดียวต่อ session (ไม่ append ทับ, ไฟล์แยกต่อ
# session_id) เก็บทุกอย่างที่ทำให้ตัวเลข timing "อ่านซ้ำได้" ในอนาคต — ถ้า re-fit
# BOARD_GATE_COST ใหม่จากข้อมูลชุดนี้ ต้องรู้ว่ารันด้วย toolchain/host แบบไหน
# ---------------------------------------------------------------------------

def _git_commit_and_dirty():
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip() != ""
        return commit, dirty
    except Exception:
        return "", None


def _pio_version():
    try:
        pio = os.environ.get("PIO_PATH") or "pio"
        out = subprocess.run([pio, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
        return out
    except Exception:
        return ""


def _firmware_build_hash(fw_src_dir: Path):
    """hash เนื้อหาของ firmware/common + firmware/<board>/src(_offload) ที่ใช้ compile
    จริง — ไม่ใช่ hash ของ binary (ไม่ได้ build ตอนเก็บ metadata) แต่พอให้รู้ว่าซอร์ส
    เปลี่ยนหรือไม่เทียบ session อื่น ถ้าต้องการ hash ของ binary จริงต้องอ่านจาก
    .pio/build/<env>/firmware.{hex,bin} หลัง build เสร็จ (ไม่ได้ทำในนี้ เพราะไฟล์นี้ไม่
    ผูกกับขั้นตอน build โดยตรง)"""
    h = hashlib.sha256()
    common = REPO_ROOT / "firmware" / "common"
    paths = sorted(common.rglob("*.hpp")) + sorted(Path(fw_src_dir).rglob("*.cpp"))
    for p in paths:
        try:
            h.update(p.read_bytes())
        except OSError:
            continue
    return h.hexdigest()[:16]


def check_sleep_prevention():
    """best-effort: บอกว่า host มีอะไรกัน sleep อยู่หรือไม่ (macOS ผ่าน `pmset -g
    assertions`) — Phase 3 timing พังได้ถ้า host หลับกลางคัน (WiFi/USB suspend,
    Aer process ถูก throttle) แพลตฟอร์มอื่นคืน checked=False ให้ผู้ใช้ตรวจเอง
    ไม่ implement เต็มรูปแบบข้ามแพลตฟอร์ม เพราะนอกขอบเขตของงานนี้"""
    if sys.platform != "darwin":
        return {"checked": False, "prevented": None,
                "note": "sleep-prevention check only implemented for macOS; verify manually "
                        "(e.g. run under `caffeinate -s`) on this platform"}
    try:
        out = subprocess.run(["pmset", "-g", "assertions"], capture_output=True, text=True, timeout=5).stdout
        prevented = "PreventUserIdleSystemSleep" in out and "0x00000001" in out
        # ตรวจแบบหยาบ: มีบรรทัด PreventUserIdleSystemSleep ที่ active (ไม่ได้ parse
        # ทุก process ที่ถืออยู่ — พอบอกได้ว่า "มีใครกัน sleep อยู่บ้างไหม" เท่านั้น
        active = any("PreventUserIdleSystemSleep" in line and "(00" not in line for line in out.splitlines())
        return {"checked": True, "prevented": bool(active),
                "note": "checked via `pmset -g assertions`; run under `caffeinate -s` before a "
                        "long session if this is False"}
    except Exception as e:
        return {"checked": False, "prevented": None, "note": f"pmset check failed: {e}"}


def write_environment_metadata(session_id, board, port, baud, f_cpu, fw_src_dir,
                                env_dir: Path = None):
    if env_dir is None:
        env_dir = ENV_DIR
    env_dir.mkdir(parents=True, exist_ok=True)
    commit, dirty = _git_commit_and_dirty()
    meta = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "git_commit": commit,
        "git_dirty": dirty,
        "firmware_source_hash": _firmware_build_hash(fw_src_dir),
        "platformio_version": _pio_version(),
        "python_version": platform.python_version(),
        "board": board,
        "serial_port": port,
        "baud": baud,
        "f_cpu": f_cpu,
        "host_os": platform.platform(),
        "host_cpu": platform.processor() or platform.machine(),
        "sleep_prevention": check_sleep_prevention(),
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
    }
    path = env_dir / f"{session_id}.json"
    path.write_text(json.dumps(meta, indent=2))
    return path


# ---------------------------------------------------------------------------
# warm-up flag — ไม่ต้องแก้เฟิร์มแวร์: derive จาก rep index อย่างเดียว ฝั่ง PC
# ---------------------------------------------------------------------------

WARMUP_REPS = 0  # ค่าเริ่มต้น: ไม่ตัด rep ไหนทิ้ง (IQR ที่วัดจริงในรอบ REPS=30 แคบมาก
                 # ไม่เห็นสัญญาณ warm-up effect ที่ชัดเจน) เปลี่ยนได้ถ้าพบสัญญาณภายหลัง


def is_warmup(rep_index: int) -> bool:
    return rep_index < WARMUP_REPS


# ---------------------------------------------------------------------------
# ข้อจำกัดที่ตั้งใจไม่ implement ในไฟล์นี้ (ต้องแก้เฟิร์มแวร์ หรือใช้เครื่องมือเพิ่ม
# — บันทึกไว้ที่นี่ + run_log.md ตามที่ตกลง ไม่ implement เงียบ ๆ แบบครึ่ง ๆ กลาง ๆ):
#
# 1. Heap/SRAM "high-water mark ระหว่างการรัน" (ไม่ใช่แค่ก่อน/หลัง):
#    เฟิร์มแวร์ปัจจุบัน (firmware/*/src/main.cpp) วัด freeMemory()/free heap ที่
#    "ก่อน" กับ "หลัง" runCircuit() เท่านั้น (คอลัมน์ free_heap_before/free_heap_after
#    ใน *_raw.csv ที่มีอยู่แล้ว) การจะรู้ค่า "ต่ำสุดระหว่างทาง" ต้องแก้เฟิร์มแวร์ให้
#    sample ซ้ำ ๆ ระหว่าง runCircuit() ทำงาน (เช่นผ่าน interrupt timer) ซึ่งจะเพิ่ม
#    overhead เข้าไปใน "สิ่งที่ micros() วัดอยู่" โดยตรง — ขัดกับ constraint ที่ว่าโค้ด
#    จับเวลาต้องไม่กวนสิ่งที่วัด จึงไม่ implement ในรอบนี้
#
# 2. "MCU micros() เทียบ Logic Analyzer แบบอิสระ": exec_time_us (micros() ของ MCU)
#    มีอยู่แล้วใน *_raw.csv คอลัมน์ที่สองที่ควรจะมาจาก Logic Analyzer จริง ๆ ต้องอ่าน
#    ขอบสัญญาณจาก GPIO_TIMING_PIN ด้วยเครื่องมือภายนอก (Logic Analyzer + ซอฟต์แวร์แปลง
#    สัญญาณเป็นตัวเลข) ซึ่งไม่มีอยู่ในโปรเจกต์นี้เลย (คอมเมนต์ในเฟิร์มแวร์เองระบุว่า
#    "สำรองไว้ต่อ Logic Analyzer ในอนาคต" — ยังไม่เคยต่อจริง) ไม่ใช่การแก้เฟิร์มแวร์
#    แต่เป็นเครื่องมือ/ฮาร์ดแวร์เพิ่มเติมที่ไม่มีในขอบเขตงานนี้ — คอลัมน์
#    logic_analyzer_exec_time_us จึงไม่ได้เพิ่มเข้า schema เลย (เพิ่มคอลัมน์ที่ไม่มี
#    ทางกรอกข้อมูลได้จริงจะสร้างความเข้าใจผิดว่ามันมีข้อมูลรออยู่)
# ---------------------------------------------------------------------------
