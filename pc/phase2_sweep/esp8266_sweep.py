#!/usr/bin/env python3
# esp8266_sweep.py — Phase 2 Edge Benchmark: ไล่ค่า n ขึ้นทีละ 1 จนบอร์ด ESP8266 ล้มเหลว
#
# ต่างจาก uno_sweep.py ตรงที่ ESP8266 ใช้ malloc() รันไทม์ (ไม่ใช่ static array)
# ดังนั้น build จะสำเร็จเสมอไม่ว่า n จะเท่าไร ความล้มเหลวที่แท้จริงเกิด "ตอนรัน" เท่านั้น
# และมี 2 รูปแบบที่ต้องแยกกัน:
#   - malloc_failed  : malloc() คืน NULL ตรง ๆ (ตรวจจับได้สะอาด ไม่ hang) — เป็น
#                       Memory Wall ที่แท้จริงและ "ปลอดภัยกว่า" แบบของ Uno
#   - runtime_hang_or_reset : ไม่ตอบสนองเลย (ผิดคาด ต้องบันทึกไว้เช่นกัน)
#
# สำหรับแต่ละ (circuit, n):
#   1. build + upload firmware ด้วย -D N_QUBITS=<n> -D CIRCUIT_ID=<id>
#      (build/upload fail ไม่ retry — deterministic)
#   2. เปิด serial อ่านผลจากบอร์ด 100 trial ต่อจุดข้อมูล จนกว่าจะเจอ "DONE"
#      (ข้ามข้อความขยะจาก ESP8266 ROM bootloader ที่พิมพ์ 74880 baud ตอน boot)
#      runtime_hang_or_reset (ไม่ใช่ malloc_failed) ถือเป็นความล้มเหลวชั่วคราวได้ จึง
#      retry ที่ n เดิมอีก 1 ครั้งก่อนสรุปว่าเป็น Memory Wall จริง — malloc_failed ไม่ retry
#      เพราะ deterministic เหมือนกัน
#      *** ข้อแตกต่างจากวิธีวัดของ dataset n=30: รอบนั้นไม่มี retry เลย รอบ n=100 นี้
#      ผ่อนเกณฑ์ให้ทนความล้มเหลวชั่วคราวได้ 1 ครั้ง — Memory Wall ของสอง dataset จึง
#      "ไม่ได้เปรียบเทียบกันตรง ๆ ได้ทันที" ต้องดูคอลัมน์ retry_count ประกอบ (run_log.md) ***
#
# *** timeout ต่อจุดข้อมูล (รอบ 6 วงจร): ไม่ใช่ค่าคงที่ค่าเดียวทั้งสวีปแล้ว คำนวณต่อ
# (circuit, n) จาก pc/shared/timing_model.py = จำนวนเกท x ค่าคงที่เวลาต่อเกทของบอร์ด
# x safety 2.5 หนีบด้วยพื้น 90 วินาที / เพดาน 4 ชั่วโมง เหตุผล: grover ที่ n สูงใช้เวลา
# ต่อจุดมากกว่า h_all หลักพันเท่า ถ้าใช้ค่าคงที่เดียวกันหมด จุด grover จะถูกบันทึกเป็น
# Memory Wall ทั้งที่บอร์ดแค่ยังคำนวณไม่เสร็จ ค่าที่ใช้จริงบันทึกลงคอลัมน์
# timeout_budget_s ทั้งใน *_raw.csv และ *_memory_wall.csv (อ่านย้อนหลังต้องแยกออกว่า
# "ชน 90 วินาที" กับ "ชน 4 ชั่วโมง" คนละความหมาย) ***
#
# *** นโยบาย retry เพิ่มเติม: retry เฉพาะจุดที่ timeout budget <= 600 วินาที จุดที่แพง
# กว่านั้น (grover n สูง) ไม่ retry เพราะต้นทุนของ retry แปรผันตาม budget แต่ประโยชน์
# คงที่ — ที่ 70 วินาทีคุ้ม แต่จ่ายเพิ่มอีก 4 ชั่วโมงเพื่อทดสอบซ้ำสมมติฐานเดิมไม่คุ้ม
# และรันซ้ำเฉพาะจุดนั้นทีหลังก็ได้ (ไฟล์เป็น append-only) จุดที่ถูกข้าม retry บันทึกไว้
# ที่คอลัมน์ retry_policy = skipped_high_budget ไม่ปนกับจุดที่สำเร็จตั้งแต่ครั้งแรก ***
#
# *** จุดที่ timing_model ประเมินว่าเกินเพดาน (เช่น ESP8266 grover n=12 ~95 วันต่อจุด)
# จะถูกข้ามพร้อม status=skipped_compute_infeasible + คอลัมน์ expected_point_s —
# ไม่ใช่ Memory Wall แต่เป็น compute wall ที่มาถึงก่อน (--force-infeasible เพื่อดันทุรัง) ***
#
# *** resume (ค่าเริ่มต้น): มีแถวใน *_memory_wall.csv = จุดนั้น "เสร็จสิ้น" แล้วไม่ว่า
# ผลจะเป็นอะไร (ok, malloc_failed, skipped_compute_infeasible, ...) — resume ข้ามได้เลย
# ไม่ต้องแตะฮาร์ดแวร์ซ้ำ วงจรที่เคยเจอ "กำแพงจริง" แล้ว (build_or_upload_fail,
# malloc_failed, runtime_hang_or_reset หลัง retry หมด) จะไม่ถูกลอง n ที่สูงกว่านั้นซ้ำ
# อีก แม้ n เหล่านั้นไม่เคยมี record ก็ตาม (ตรรกะเดียวกับที่ sweep เดิม break ออกจาก
# n-loop ทันทีที่เจอกำแพง) แถวกำพร้าใน raw CSV (จุดที่โปรเซสตายระหว่างเขียนผล ไม่มี
# terminal record คู่กัน) จะถูกกวาดทิ้งก่อนแล้วรันจุดนั้นใหม่ทั้งหมด — ห้าม "เติม" ให้
# ครบ 100 trial เพราะ trial จาก 2 sessions ไม่ใช่ตัวอย่างสม่ำเสมอเดียวกัน (บอร์ด reset/
# reflash/อุณหภูมิเครื่องต่างกันระหว่าง session) ใช้ --fresh เพื่อย้ายผลลัพธ์เดิมออกไป
# (ไม่ลบทิ้ง) แล้วเริ่มนับใหม่หมด — ดู pc/shared/resume.py สำหรับเหตุผลเต็ม ***
#   3. เขียนทุกแถวลง data/raw/phase2/esp8266/<circuit>/raw.csv (ไฟล์ดิบ, append)
#      และสรุปลง .../phase2/memory_wall.csv (คอลัมน์ retry_count: 0/1) — เส้นทางเปลี่ยน
#      จาก data/raw/phase2/esp8266_*.csv เดิมเมื่อ 2026-09-20 (ดู pc/shared/paths.py)
#
# การใช้งาน:
#   .venv/bin/python pc/phase2_sweep/esp8266_sweep.py --port /dev/cu.usbserialXXXX \
#       --circuits h_all bell_ghz qft grover qpe steane_encode --n-start 2 --n-max 16
#
# steane_encode คงที่ที่ n=7 เสมอ (pc/shared/circuit_ids.n_values_for_sweep จัดการให้
# อัตโนมัติ) — ถ้า n=7 ไม่อยู่ใน [n-start, n-max] ที่ขอ จะข้ามวงจรนี้ไปเฉย ๆ

import argparse
import csv
import glob
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import serial

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared.circuit_ids import CIRCUIT_IDS, n_values_for_sweep  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared import resume as rs  # noqa: E402
from shared import telemetry as tel  # noqa: E402
from shared import paths as sp  # noqa: E402
from shared import upload_retry as ur  # noqa: E402

RESUME_KEY_SPEC = [("circuit", str), ("n", int)]

FW_DIR = REPO_ROOT / "firmware" / "esp8266"
PIO = os.environ.get("PIO_PATH") or shutil.which("pio")

BAUD = 115200
F_CPU = 80000000  # เมตาดาต้าเท่านั้น ไม่ได้ใช้คำนวณอะไร
BOOT_WAIT_S = 1.5  # เผื่อบอร์ด reset ตัวเองหลัง upload แล้วเริ่ม setup() ใหม่
# เวลารอสูงสุดต่อจุดข้อมูลไม่ใช่ค่าคงที่อีกต่อไป — คำนวณต่อ (circuit, n) จาก
# pc/shared/timing_model.timeout_budget_s() ดูเหตุผลใน header ของไฟล์นี้

ESP_PORT_GLOBS = ("/dev/cu.usbserial*", "/dev/cu.wchusbserial*", "/dev/cu.SLAB_USBtoUART*")

# Standing operator decision 1 (2026-09-20 for Uno, ported here 2026-09-22 —
# see run_log.md "port upload-retry to ESP boards"): an upload failure gets
# up to UPLOAD_MAX_ATTEMPTS attempts before the point is logged failed and
# the sweep moves to the NEXT n in the SAME circuit (never abandons it).
# Deterministic failures (compile error, link overflow) still stop climbing
# immediately, same as before -- this only changes upload-stage failures.
#
# esptool signature markers (this platform pins espressif8266@4.2.1, which
# pulls tool-esptoolpy ~1.30000.0 -- the single-file esptool.py, confirmed via
# ~/.platformio/platforms/espressif8266/platform.json's uploader pin, distinct
# from the ESP32 platform's newer modular esptool -- see esp32_sweep.py):
#   - "Failed to connect to" -- esptool.py's connect(), wraps the underlying
#     sync error (tool-esptoolpy@1.30000.201119/esptool.py:529)
#   - "timed out waiting for packet" -- the underlying sync error text itself
#     (same file:2636, raised by the SLIP packet reader on read timeout)
#   - "a fatal error occurred" -- esptool.py's top-level handler, always
#     wraps whichever FatalError above fired (same file:3964) -- present in
#     the captured `pio run -t upload` output for every esptool FatalError,
#     so it's kept as a catch-all alongside the two more specific markers.
# None of these ever fire on a build_overflow (compile-stage, never reaches
# esptool) or a determinstic flash-content mismatch.
UPLOAD_SYNC_FAILURE_MARKERS = (
    "failed to connect to",
    "timed out waiting for packet",
    "a fatal error occurred",
)
UPLOAD_RETRY_SETTLE_S_DEFAULT = 2.0
UPLOAD_MAX_ATTEMPTS = ur.UPLOAD_MAX_ATTEMPTS
CONSECUTIVE_UPLOAD_FAIL_LIMIT = ur.CONSECUTIVE_UPLOAD_FAIL_LIMIT
ConsecutiveUploadFailuresError = ur.ConsecutiveUploadFailuresError


def is_upload_sync_failure(log: str) -> bool:
    return ur.is_upload_sync_failure(log, UPLOAD_SYNC_FAILURE_MARKERS)


def is_upload_stage_failure(build_status: str, result: dict) -> bool:
    return ur.is_upload_stage_failure(build_status, result)


def find_esp_port(hint: str) -> str:
    """สแกน port ใหม่ทุกครั้ง กันกรณี re-enumerate เหมือนที่เจอกับ Uno"""
    candidates = sorted(p for pat in ESP_PORT_GLOBS for p in glob.glob(pat))
    if not candidates:
        return hint
    if hint in candidates:
        return hint
    return candidates[0]


def port_still_enumerated() -> bool:
    """Best-effort check that some ESP8266-shaped port still exists before
    retrying an upload. Unlike the Uno (native USB-CDC, re-enumerates to a
    new /dev path on reset -- see uno_sweep.py's find_uno_port docstring),
    the ESP8266 boards this project uses go through a USB-UART bridge chip
    (CH340/CP2102-family) whose /dev path stays stable across resets -- this
    check is still worth doing (catches the board/cable being fully
    unplugged before wasting a retry attempt) but reuses find_esp_port's own
    glob patterns rather than assuming a Uno-style re-enumeration."""
    return any(glob.glob(pat) for pat in ESP_PORT_GLOBS)


def build_and_upload(circuit: str, n: int, port_hint: str, build_timeout_s=None):
    """แยก compile กับ upload เป็นสอง subprocess (เดิมเป็นคำสั่งเดียว `-t upload`) เพื่อ
    จับเวลาแยกกันได้จริง — ดู uno_sweep.py::build_and_upload สำหรับเหตุผลเต็ม เรื่อง
    dependency tracking ของ PlatformIO ที่ทำให้พฤติกรรมจริงไม่เปลี่ยนจากเดิม

    คืน dict (ไม่ใช่ tuple) เพราะจำนวนค่าที่ต้องส่งกลับเพิ่มขึ้น"""
    if build_timeout_s is None:
        build_timeout_s = tm.BUILD_TIMEOUT_S
    port = find_esp_port(port_hint)
    env = os.environ.copy()
    env.update({"N_QUBITS": str(n), "CIRCUIT_ID": str(CIRCUIT_IDS[circuit])})

    timed_out = False
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [PIO, "run", "-e", "nodemcuv2"],
            cwd=str(FW_DIR), env=env, capture_output=True, text=True, timeout=build_timeout_s,
        )
        c_stdout, c_stderr, c_rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        c_stdout = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        c_stderr = f"pio run (compile) timed out after {build_timeout_s}s"
        c_rc = -1
        timed_out = True
    compile_s = time.perf_counter() - t0

    ram_pct, ram_bytes = None, None
    m = re.search(r"RAM:\s*\[.*?\]\s*([\d.]+)%\s*\(used (\d+) bytes", c_stdout)
    if m:
        ram_pct, ram_bytes = float(m.group(1)), int(m.group(2))

    if c_rc != 0:
        return {"ok": False, "log": c_stdout[-4000:] + c_stderr[-2000:], "port": port,
                "compile_s": compile_s, "upload_s": 0.0, "stage": "compile",
                "ram_pct": ram_pct, "ram_bytes": ram_bytes, "timed_out": timed_out}

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [PIO, "run", "-e", "nodemcuv2", "-t", "upload", "--upload-port", port],
            cwd=str(FW_DIR), env=env, capture_output=True, text=True, timeout=build_timeout_s,
        )
        u_stdout, u_stderr, u_rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        u_stdout = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        u_stderr = f"pio run (upload) timed out after {build_timeout_s}s (stuck esptool / stuck port)"
        u_rc = -1
        timed_out = True
    upload_s = time.perf_counter() - t0

    ok = u_rc == 0
    return {"ok": ok, "log": u_stdout[-4000:] + u_stderr[-2000:], "port": port,
            "compile_s": compile_s, "upload_s": upload_s, "stage": "upload",
            "ram_pct": ram_pct, "ram_bytes": ram_bytes, "timed_out": timed_out}


class HardTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise HardTimeout()


def read_serial_trials(port: str, timeout_s: int):
    """เปิด serial อ่านจนเจอ DONE / MALLOC_FAILED / timeout
    ใช้ hard deadline ผ่าน signal.alarm เหมือน uno_sweep.py (บทเรียนจากที่เจอค้างจริง)"""
    rows = []
    malloc_failed = False
    reset_count = 0
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(timeout_s + 10)
    try:
        with serial.Serial(port, BAUD, timeout=2) as ser:
            ser.dtr = False
            ser.rts = False
            deadline = time.time() + timeout_s
            done = False
            while time.time() < deadline:
                raw = ser.readline()
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.endswith("DONE") or line == "DONE":
                    done = True
                    break
                if line == "MALLOC_FAILED" or line.endswith("MALLOC_FAILED"):
                    malloc_failed = True
                    continue
                if "esp8266," in line:
                    # ตัดขยะจาก ROM bootloader (baud ไม่ตรง) ที่อาจติดมาก่อนบรรทัดจริง
                    idx = line.index("esp8266,")
                    rows.append(line[idx:])
                elif line.startswith("board,circuit"):
                    reset_count += 1
                    rows.clear()
                    malloc_failed = False
            return done, rows, malloc_failed, f"reset_count={reset_count}"
    except serial.SerialException as e:
        return False, [], False, f"serial_error={e}"
    except HardTimeout:
        return False, rows, malloc_failed, f"hard_timeout=true,reset_count={reset_count}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--circuits", nargs="+",
                     default=["h_all", "bell_ghz", "qft", "grover", "qpe", "steane_encode"])
    ap.add_argument("--n-start", type=int, default=2)
    ap.add_argument("--n-max", type=int, default=16)
    ap.add_argument("--force-infeasible", action="store_true",
                     help="พยายามรันจุดที่ timing_model บอกว่าเกินเพดานเวลาไปแล้วด้วย "
                          "(ปกติจะข้ามพร้อมบันทึกเหตุผล เพราะได้แค่ timeout เปล่า ๆ)")
    ap.add_argument("--build-timeout", dest="build_timeout_s", type=int, default=tm.BUILD_TIMEOUT_S,
                     help=f"วินาทีสูงสุดต่อการเรียก pio run หนึ่งครั้ง (compile และ upload แยกกัน) "
                          f"ค่าเริ่มต้น {tm.BUILD_TIMEOUT_S}s — timeout ไม่ถือเป็น Memory Wall "
                          f"และ retry ได้ (ดู docs/preflight_report.md H2)")
    ap.add_argument("--wdt-threshold-s", type=float, default=None,
                     help="ถ้าเวลาต่อ rep ที่ประเมินไว้เกินค่านี้ (วินาที) การที่บอร์ดเงียบจะถูก "
                          "บันทึกเป็น watchdog_suspected ไม่ใช่ runtime_hang_or_reset และจะไม่ถูก "
                          "ตีความเป็นกำแพง ค่าเริ่มต้นมาจาก timing_model.WDT_PER_REP_THRESHOLD_S")
    ap.add_argument("--fresh", "--no-resume", dest="fresh", action="store_true",
                     help="ไม่ resume จากผลลัพธ์เดิม — ย้ายไฟล์ raw/memory_wall เดิมไปเป็น "
                          "*.pre-fresh-<timestamp>.csv (ไม่ลบทิ้ง) แล้วเริ่มนับใหม่หมด")
    ap.add_argument("--upload-retry-settle-s", type=float, default=UPLOAD_RETRY_SETTLE_S_DEFAULT,
                     help="วินาทีที่รอก่อน retry เมื่อเจอ esptool sync failure (signature "
                          "match เท่านั้น ไม่ใช่ปัญหาหน่วยความจำ) แล้วเช็คว่า port ยังอยู่ "
                          f"ก่อน retry จริง — ค่าเริ่มต้น {UPLOAD_RETRY_SETTLE_S_DEFAULT}s "
                          "(standing decision 1, ported from uno_sweep.py 2026-09-22)")
    args = ap.parse_args()

    try:
        for circuit in args.circuits:
            print(f"\n=== circuit={circuit} ===")
            _run_circuit(args, circuit)
    except ConsecutiveUploadFailuresError as e:
        # standing decision 1: stop the whole run, don't crash past the point
        # of having flushed everything collected so far (_run_circuit's own
        # try/finally already closed that circuit's raw/wall file handles and
        # its SessionRecorder's __exit__ already wrote a session row noting
        # the exception before it got here) -- mirrors uno_sweep.py's main().
        print(f"\n!!! STOPPING RUN: {e}")
        print(f"raw -> {sp.raw_csv_path('esp8266', e.circuit)}\n"
              f"memory wall -> {sp.memory_wall_csv_path('esp8266', e.circuit)}")
        print(f"telemetry -> {sp.sessions_csv_path('esp8266', e.circuit)}, "
              f"{sp.points_csv_path('esp8266', e.circuit)}")
        sys.exit(2)


def _run_circuit(args, circuit):
    """One algorithm's directory/files/telemetry session — see pc/shared/paths.py
    and uno_sweep.py's module docstring for the per-board-per-algorithm layout
    this replaced (2026-09-20, run_log.md)."""
    n_values = n_values_for_sweep(circuit, args.n_start, args.n_max)
    if not n_values:
        print(f"skip: {circuit} is fixed-n and its n is outside [{args.n_start}, {args.n_max}]")
        return

    raw_directory = sp.raw_dir("esp8266", circuit, phase=2)
    raw_directory.mkdir(parents=True, exist_ok=True)
    raw_path = sp.raw_csv_path("esp8266", circuit)
    wall_path = sp.memory_wall_csv_path("esp8266", circuit)
    points_csv = sp.points_csv_path("esp8266", circuit)
    sessions_csv = sp.sessions_csv_path("esp8266", circuit)
    env_directory = sp.env_dir("esp8266", circuit)

    # resume (ค่าเริ่มต้น): มีแถวใน wall CSV = จุดนั้น "เสร็จสิ้น" แล้วไม่ว่าผลจะเป็นอะไร
    # ข้ามได้เลย ไม่ต้องแตะฮาร์ดแวร์ซ้ำ ส่วนแถวกำพร้าใน raw CSV (จุดที่โปรเซสตายระหว่าง
    # เขียนผล ไม่มี terminal record คู่กัน) ต้องกวาดทิ้งก่อน แล้วรันจุดนั้นใหม่ทั้งหมด — ห้าม
    # "เติม" ให้ครบ 100 trial เพราะ trial จาก 2 sessions ไม่ใช่ตัวอย่างสม่ำเสมอเดียวกัน
    # ดู pc/shared/resume.py สำหรับเหตุผลเต็ม
    if args.fresh:
        moved = rs.archive_existing(wall_path, raw_path)
        for src, dest in moved:
            print(f"--fresh: archived {src.name} -> {dest.name}")
        completed = {}
    else:
        completed = rs.load_terminal_points(wall_path, RESUME_KEY_SPEC)
        kept, removed, removed_keys = rs.purge_orphan_rows(raw_path, RESUME_KEY_SPEC, set(completed.keys()))
        if removed:
            print(f"resume: purged {removed} orphan raw row(s) from interrupted point(s) "
                  f"{sorted(removed_keys)} — these will be redone from scratch, not topped up")

    raw_is_new = not raw_path.exists()
    wall_is_new = not wall_path.exists()
    raw_f = open(raw_path, "a", newline="")
    wall_f = open(wall_path, "a", newline="")
    raw_w = csv.writer(raw_f)
    wall_w = csv.writer(wall_f)
    if raw_is_new:
        raw_w.writerow(["board", "circuit", "n", "rep", "exec_time_us",
                        "free_heap_before", "free_heap_after",
                        "timeout_budget_s"])
    if wall_is_new:
        wall_w.writerow([
            "board", "circuit", "n", "theoretical_bytes", "compile_ram_used_bytes",
            "compile_ram_pct", "status", "timestamp_utc", "retry_count",
            "timeout_budget_s", "expected_point_s", "retry_policy",
        ])

    try:
        # preflight: โชว์ budget ของทุกจุดก่อนเริ่ม ให้คนกดรันเห็นว่าจุดไหนแพง/จุดไหนทำไม่ได้
        # ตั้งแต่ก่อนเริ่ม ไม่ใช่ไปเจอตอนชั่วโมงที่หก
        planned = [(circuit, n) for n in n_values]
        infeasible = tm.print_budget_plan("esp8266", planned, phase=2)
        if args.force_infeasible:
            print("--force-infeasible: จะพยายามรันจุดที่เกินเพดานด้วย\n")
            infeasible = set()

        remaining_preview = [p for p in planned if p not in completed]
        real_remaining = [p for p in remaining_preview if p not in infeasible]
        est_s = sum(tm.expected_point_time_s("esp8266", c, n) for c, n in real_remaining)
        n_inf_remaining = len(remaining_preview) - len(real_remaining)
        remaining_human = tm.human_duration(est_s)
        if n_inf_remaining:
            remaining_human += f" (+{n_inf_remaining} infeasible point(s), skipped near-instantly)"
        rs.print_resume_summary("esp8266", planned, completed, remaining_human)
        wall_n_by_circuit = rs.known_wall_n(completed)

        # telemetry: session wrapper + environment metadata ครั้งเดียวตอน circuit นี้เริ่ม —
        # ดู pc/shared/telemetry.py และ uno_sweep.py สำหรับ schema เต็ม/เหตุผล
        resumed_from_previous = bool(completed)
        last_end = (tel.last_session_end_utc("esp8266", 2, sessions_csv=sessions_csv)
                    if resumed_from_previous else None)
        session = tel.SessionRecorder(phase=2, board="esp8266", circuits=[circuit],
                                       resumed_from_previous=resumed_from_previous,
                                       estimated_total_s=round(est_s, 1),
                                       sessions_csv=sessions_csv)
        with session:
            if last_end is not None:
                from datetime import datetime as _dt, timezone as _tz
                gap = (_dt.now(_tz.utc) - last_end).total_seconds()
                if gap > 0:
                    session.note_interruption_gap(gap)
            env_path = tel.write_environment_metadata(
                session.session_id, "esp8266", args.port, BAUD, F_CPU, FW_DIR / "src",
                env_dir=env_directory, pio_project_dir=FW_DIR, pio_env="nodemcuv2")
            session.env_json_path = str(env_path)

            _sweep_body(args, circuit, n_values, completed, wall_n_by_circuit, infeasible,
                        raw_w, raw_f, wall_w, wall_f, session, points_csv)
    finally:
        raw_f.close()
        wall_f.close()

    print(f"\nraw -> {raw_path}\nmemory wall -> {wall_path}")
    print(f"telemetry -> {sessions_csv}, {points_csv}")


def _sweep_body(args, circuit, n_values, completed, wall_n_by_circuit, infeasible,
                 raw_w, raw_f, wall_w, wall_f, session, points_csv):
    # standing decision 1 (ported from uno_sweep.py 2026-09-22): settle once,
    # consumed once, before the very next build_and_upload call regardless of
    # which point that's for -- the port doesn't know about the n boundary.
    pending_settle = False
    pending_settle_reason = None

    # two consecutive n values that each exhaust all UPLOAD_MAX_ATTEMPTS
    # upload attempts stop the whole run -- see ConsecutiveUploadFailuresError.
    prev_upload_exhausted_n = None

    for n in n_values:
        skip_ts = datetime.now(timezone.utc).isoformat()
        if (circuit, n) in completed:
            print(f"n={n:2d}  SKIP (resume): already {completed[(circuit, n)].get('status', '?')}")
            tel.write_point_row({
                "session_id": session.session_id, "phase": 2, "board": "esp8266",
                "circuit": circuit, "n": n, "attempt_index": 0,
                "start_utc": skip_ts, "end_utc": skip_ts, "wall_s": 0,
                "retry_count": 0, "timeout_hit": False, "failure_type": "none",
                "status": "skipped_resume",
            }, points_csv)
            session.note_point(status="skipped_resume")
            continue
        if circuit in wall_n_by_circuit and n > wall_n_by_circuit[circuit]:
            print(f"n={n:2d}  SKIP (resume): {circuit} already hit its wall at "
                  f"n={wall_n_by_circuit[circuit]} in a previous session")
            tel.write_point_row({
                "session_id": session.session_id, "phase": 2, "board": "esp8266",
                "circuit": circuit, "n": n, "attempt_index": 0,
                "start_utc": skip_ts, "end_utc": skip_ts, "wall_s": 0,
                "retry_count": 0, "timeout_hit": False, "failure_type": "none",
                "status": "skipped_known_wall",
            }, points_csv)
            session.note_point(status="skipped_known_wall")
            continue

        theoretical_bytes = (1 << n) * 8
        budget_s = tm.timeout_budget_s("esp8266", circuit, n)
        expected_s = tm.expected_point_time_s("esp8266", circuit, n)
        may_retry = tm.retry_allowed(budget_s)
        retry_policy = "allowed" if may_retry else "skipped_high_budget"
        ts = datetime.now(timezone.utc).isoformat()

        if (circuit, n) in infeasible:
            # ไม่ใช่ Memory Wall และไม่ใช่ hang — เป็นขีดจำกัดเชิงเวลาคำนวณล้วน ๆ
            # บันทึกค่าประมาณไว้ด้วย เพื่อให้แถวนี้อ่านเป็น "ผลการทดลอง" ได้จริง
            print(f"n={n:2d}  SKIP compute-infeasible: expected "
                  f"{tm.human_duration(expected_s)} > ceiling {tm.CEILING_S}s")
            wall_w.writerow(["esp8266", circuit, n, theoretical_bytes, None, None,
                              "skipped_compute_infeasible", ts, 0,
                              budget_s, round(expected_s, 1), "n/a"])
            wall_f.flush()
            tel.write_point_row({
                "session_id": session.session_id, "phase": 2, "board": "esp8266",
                "circuit": circuit, "n": n, "attempt_index": 0,
                "start_utc": ts, "end_utc": ts, "wall_s": 0,
                "retry_count": 0, "timeout_hit": False, "failure_type": "none",
                "status": "skipped_compute_infeasible",
            }, points_csv)
            session.note_point(status="skipped_compute_infeasible")
            continue

        wall_found = False
        retry_used = 0
        point_device_s = 0.0
        point_reflash_s = 0.0
        upload_fail_exhausted = False  # this point's terminal outcome: ran out
        # of all UPLOAD_MAX_ATTEMPTS upload attempts (standing decision 1)

        # attempt loop: three independent retry policies share this loop, each
        # gated on the failure kind of the attempt that just happened --
        #   - runtime hang/reset/watchdog/build_timeout: unchanged existing
        #     policy, one retry only (2 attempts total), gated by may_retry
        #     (budget rule, see timing_model.retry_allowed).
        #   - upload-stage failure (esptool never got a working sync):
        #     standing decision 1 -- up to UPLOAD_MAX_ATTEMPTS (3) attempts
        #     total, NOT gated by the budget rule, and exhausting all 3 does
        #     NOT stop climbing / does NOT abandon the circuit.
        #   - malloc_failed / compile-stage failure: deterministic, one
        #     attempt only, regardless of which of the above this attempt
        #     would otherwise have matched.
        attempt = 0
        while True:
            print(f"n={n:2d}  theoretical={theoretical_bytes:6d} bytes  "
                  f"budget={budget_s}s (expected {tm.human_duration(expected_s)})  "
                  f"attempt={attempt + 1}  ", end="", flush=True)
            if attempt > 0:
                print("(retry) ", end="", flush=True)

            # settle + port-still-enumerated check BEFORE this build_and_upload
            # if the previous action on the port ended in hard_timeout=true or
            # an upload-stage failure -- see uno_sweep.py for the root-cause
            # this addresses (avrdude/esptool retried too soon after the OS
            # hadn't yet released the port).
            settle_note = ""
            if pending_settle:
                print(f"\n-- settling {args.upload_retry_settle_s}s before the next "
                      f"build_and_upload (previous: {pending_settle_reason})")
                time.sleep(args.upload_retry_settle_s)
                port_ok = port_still_enumerated()
                print(f"-- port re-enumeration check: {'found' if port_ok else 'NOT FOUND'}")
                settle_note = (f"[settled {args.upload_retry_settle_s}s after "
                                f"{pending_settle_reason}; port_reenum="
                                f"{'ok' if port_ok else 'missing'}] ")
                pending_settle = False
                pending_settle_reason = None

            attempt_start = datetime.now(timezone.utc).isoformat()
            result = build_and_upload(circuit, n, args.port, args.build_timeout_s)
            ts = datetime.now(timezone.utc).isoformat()
            args.port = result["port"]
            reflash_s = result["compile_s"] + result["upload_s"]
            point_reflash_s += reflash_s

            if not result["ok"]:
                # แยกสาเหตุก่อนตัดสิน: timeout ของ toolchain ไม่ใช่กำแพง และ retry ได้
                # (ดู pc/shared/resume.classify_build_failure และ finding H2)
                build_status = rs.classify_build_failure(
                    result["log"], result.get("ram_pct"), result.get("timed_out", False))
                is_timeout = build_status == "build_timeout"
                is_upload_fail = is_upload_stage_failure(build_status, result)
                is_upload_sync = is_upload_fail and is_upload_sync_failure(result["log"])
                label = {
                    "build_overflow": "BUILD OVERFLOW -> Memory Wall (positive evidence: linker/RAM)",
                    "build_timeout": "BUILD TIMEOUT -> toolchain/host problem, NOT a wall",
                    "build_or_upload_fail": "UPLOAD/BUILD FAIL -> not a wall (no memory evidence)",
                }[build_status]
                print(label + ("  (matched upload-sync-failure signature)" if is_upload_sync else ""))
                print(result["log"][-800:])

                will_retry = False
                if is_timeout and attempt == 0 and may_retry:
                    will_retry = True
                elif is_upload_fail and attempt < UPLOAD_MAX_ATTEMPTS - 1:
                    will_retry = True

                failure_message = settle_note + result["log"][-300:]
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 2, "board": "esp8266",
                    "circuit": circuit, "n": n, "attempt_index": attempt,
                    "start_utc": attempt_start, "end_utc": ts, "wall_s": round(reflash_s, 3),
                    "build_compile_s": round(result["compile_s"], 3),
                    "upload_s": round(result["upload_s"], 3),
                    "retry_count": retry_used, "timeout_hit": is_timeout,
                    "failure_type": "build_timeout" if is_timeout else "build",
                    "failure_message": failure_message,
                    "status": "retrying" if will_retry else "failed",
                }, points_csv)
                if will_retry:
                    retry_used += 1
                    if is_upload_fail:
                        pending_settle = True
                        pending_settle_reason = f"upload-stage failure (attempt {attempt + 1})"
                        print(f"-- upload-stage failure, will retry (attempt "
                              f"{attempt + 2}/{UPLOAD_MAX_ATTEMPTS})")
                    else:
                        print("-- transient build timeout, retrying once at the same n")
                    attempt += 1
                    continue

                if is_upload_fail:
                    upload_fail_exhausted = True

                wall_w.writerow(["esp8266", circuit, n, theoretical_bytes,
                                  result.get("ram_bytes"), result.get("ram_pct"),
                                  build_status, ts, retry_used,
                                  budget_s, round(expected_s, 1), retry_policy])
                wall_f.flush()
                session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="failed")
                if upload_fail_exhausted:
                    # standing decision 1: an upload failure (even after
                    # exhausting all attempts) is never treated as a reason to
                    # stop climbing n in this circuit -- it carries no memory
                    # evidence at all.
                    wall_found = False
                    print(f"-- exhausted all {UPLOAD_MAX_ATTEMPTS} upload attempts for n={n} "
                          "-- NOT abandoning the circuit, continuing to the next n")
                else:
                    wall_found = rs.stops_climbing(build_status)
                break

            time.sleep(BOOT_WAIT_S)  # เผื่อบอร์ด reset ตัวเองหลัง upload แล้วเริ่ม setup() ใหม่
            exec_t0 = time.perf_counter()
            done, rows, malloc_failed, note = read_serial_trials(find_esp_port(args.port), budget_s)
            device_exec_s = time.perf_counter() - exec_t0
            point_device_s += device_exec_s
            if "hard_timeout=true" in note:
                pending_settle = True
                pending_settle_reason = f"hard_timeout on {circuit} n={n}"
            attempt_end = datetime.now(timezone.utc).isoformat()

            if malloc_failed:
                print(f"MALLOC_FAILED -> Memory Wall found (n={n})")
                wall_w.writerow(["esp8266", circuit, n, theoretical_bytes, None, None,
                                  "malloc_failed", ts, retry_used,
                                  budget_s, round(expected_s, 1), retry_policy])
                wall_f.flush()
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 2, "board": "esp8266",
                    "circuit": circuit, "n": n, "attempt_index": attempt,
                    "start_utc": attempt_start, "end_utc": attempt_end,
                    "wall_s": round(reflash_s + BOOT_WAIT_S + device_exec_s, 3),
                    "build_compile_s": round(result["compile_s"], 3),
                    "upload_s": round(result["upload_s"], 3),
                    "boot_wait_s": BOOT_WAIT_S, "device_exec_s": round(device_exec_s, 3),
                    "retry_count": retry_used, "timeout_hit": False,
                    "failure_type": "malloc", "status": "failed",
                }, points_csv)
                session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="failed")
                wall_found = True
                break

            if done:
                for line in rows:
                    raw_w.writerow(line.split(",") + [budget_s])
                raw_f.flush()
                wall_w.writerow(["esp8266", circuit, n, theoretical_bytes, None, None,
                                  "ok", ts, retry_used,
                                  budget_s, round(expected_s, 1), retry_policy])
                wall_f.flush()
                suffix = f"  (succeeded after {retry_used} retry)" if retry_used else ""
                print(f"OK  trials_captured={len(rows)}{suffix}")
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 2, "board": "esp8266",
                    "circuit": circuit, "n": n, "attempt_index": attempt,
                    "start_utc": attempt_start, "end_utc": attempt_end,
                    "wall_s": round(reflash_s + BOOT_WAIT_S + device_exec_s, 3),
                    "build_compile_s": round(result["compile_s"], 3),
                    "upload_s": round(result["upload_s"], 3),
                    "boot_wait_s": BOOT_WAIT_S, "device_exec_s": round(device_exec_s, 3),
                    "retry_count": retry_used, "timeout_hit": False,
                    "failure_type": "none", "status": "ok",
                }, points_csv)
                session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="ok")
                break

            # ถ้าเวลาต่อ rep ที่ประเมินไว้เกินเกณฑ์ WDT ของบอร์ดนี้ การที่บอร์ดเงียบ
            # มีคำอธิบายที่เป็นไปได้มากกว่าหน่วยความจำ — บันทึกแยก และห้ามตีความเป็น
            # Memory Wall (ดู timing_model.watchdog_suspected, finding H1)
            wdt_suspected = tm.watchdog_suspected("esp8266", circuit, n, args.wdt_threshold_s)
            status = (f"watchdog_suspected({note})" if wdt_suspected
                      else f"runtime_hang_or_reset({note})")
            tel.write_point_row({
                "session_id": session.session_id, "phase": 2, "board": "esp8266",
                "circuit": circuit, "n": n, "attempt_index": attempt,
                "start_utc": attempt_start, "end_utc": attempt_end,
                "wall_s": round(reflash_s + BOOT_WAIT_S + device_exec_s, 3),
                "build_compile_s": round(result["compile_s"], 3),
                "upload_s": round(result["upload_s"], 3),
                "boot_wait_s": BOOT_WAIT_S, "device_exec_s": round(device_exec_s, 3),
                "retry_count": retry_used, "timeout_hit": True,
                "failure_type": "watchdog_suspected" if wdt_suspected else "hang",
                "failure_message": note,
                "status": "failed" if not (attempt == 0 and may_retry) else "retrying",
            }, points_csv)
            if attempt == 0 and may_retry:
                retry_used = 1
                print(f"NO 'DONE' within {budget_s}s -> {status}  "
                      "-- transient failure, retrying once at same n before declaring "
                      "Memory Wall (deviation from n=30 methodology, see run_log.md)")
                attempt += 1
                continue

            tail = "(after retry)" if retry_used else f"(no retry: {retry_policy})"
            print(f"NO 'DONE' within {budget_s}s -> {status} {tail}")
            wall_w.writerow(["esp8266", circuit, n, theoretical_bytes, None, None,
                              status, ts, retry_used,
                              budget_s, round(expected_s, 1), retry_policy])
            wall_f.flush()
            session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="failed")
            wall_found = rs.stops_climbing(status)
            break

        if upload_fail_exhausted:
            if prev_upload_exhausted_n is not None:
                raise ConsecutiveUploadFailuresError("esp8266", circuit, prev_upload_exhausted_n, n)
            prev_upload_exhausted_n = n
        else:
            prev_upload_exhausted_n = None

        if wall_found:
            break


if __name__ == "__main__":
    main()
