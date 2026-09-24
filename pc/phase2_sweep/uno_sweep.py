#!/usr/bin/env python3
# uno_sweep.py — Phase 2 Edge Benchmark: ไล่ค่า n ขึ้นทีละ 1 จนบอร์ด Uno ล้มเหลว
#
# สำหรับแต่ละ (circuit, n):
#   1. build + upload firmware ด้วย -D N_QUBITS=<n> -D CIRCUIT_ID=<id>
#      (ถ้า build/upload ไม่ผ่าน = ล้มเหลวแบบ "link/upload fail" หยุดวงจรนี้ทันที ไม่ retry
#      เพราะเป็นผลลัพธ์ deterministic — retry ก็ได้ผลเดิม)
#   2. อ่านค่า RAM usage % ที่ avr-size รายงานตอน build (ค่าทางทฤษฎีเทียบค่าที่วัดจริง)
#   3. เปิด serial อ่านผลจากบอร์ด 100 trial ต่อจุดข้อมูล จนกว่าจะเจอ "DONE"
#      timeout ไม่ใช่ค่าคงที่ค่าเดียวทั้งสวีปแล้ว แต่คำนวณต่อ (circuit, n) จาก
#      pc/shared/timing_model.py (จำนวนเกท × ค่าคงที่เวลาต่อเกทของบอร์ด × safety 2.5
#      หนีบด้วยพื้น 90 วินาที / เพดาน 4 ชั่วโมง) เพราะ grover ที่ n สูงใช้เวลาต่อจุด
#      มากกว่า h_all หลักพันเท่า ถ้าใช้ค่าคงที่เดียวกันหมด จุด grover จะถูกบันทึกเป็น
#      Memory Wall ทั้งที่บอร์ดแค่ยังคำนวณไม่เสร็จ — ค่า timeout ที่ใช้จริงถูกบันทึกลง
#      คอลัมน์ timeout_budget_s ของทั้งสองไฟล์ผลลัพธ์ (ไม่งั้นอ่านย้อนหลังแยกไม่ออก
#      ว่า "ชน 90 วินาที" กับ "ชน 4 ชั่วโมง" ซึ่งคนละความหมายสิ้นเชิง)
#      ถ้าไม่มี "DONE" ภายใน timeout = บอร์ด hang/reset -> ถือเป็นความล้มเหลวชั่วคราวได้
#      (สายหลุด, USB glitch) จึง retry ที่ n เดิมอีก 1 ครั้งก่อนสรุปว่าเป็น Memory Wall จริง
#      *** ข้อแตกต่างจากวิธีวัดของ dataset n=30: รอบนั้นไม่มี retry เลย ล้มเหลวครั้งแรก
#      ที่ n ไหนก็ถือเป็นกำแพงทันที รอบ n=100 นี้ผ่อนเกณฑ์ให้ทนความล้มเหลวชั่วคราวได้ 1
#      ครั้ง — ทำให้ตัวเลข Memory Wall ระหว่างสอง dataset "ไม่ได้เปรียบเทียบกันตรง ๆ
#      ได้ทันที" ต้องดูคอลัมน์ retry_count ใน memory_wall.csv ประกอบ (ดู run_log.md) ***
#      *** นโยบาย retry เพิ่มเติมสำหรับรอบ 6 วงจร: retry เฉพาะจุดที่ timeout budget
#      <= 600 วินาที เท่านั้น จุดที่แพงกว่านั้น (grover n สูง) จะไม่ retry เพราะต้นทุน
#      ของ retry แปรผันตาม budget แต่ประโยชน์คงที่ — ที่ 70 วินาทีคุ้ม แต่การจ่ายเพิ่ม
#      อีก 4 ชั่วโมงเพื่อทดสอบซ้ำสมมติฐานเดิมไม่คุ้ม และรันซ้ำเฉพาะจุดนั้นทีหลังก็ได้
#      (ไฟล์เป็น append-only) จุดที่ถูกข้าม retry บันทึกไว้ในคอลัมน์ retry_policy =
#      skipped_high_budget ไม่ปนกับจุดที่สำเร็จตั้งแต่ครั้งแรก (retry_count=0 เหมือนกัน
#      แต่คนละความหมาย) ***
#   3b. จุดที่ timing_model ประเมินว่าใช้เวลาเกินเพดาน (เช่น ESP8266 grover n=12 ~95 วัน
#      ต่อจุด) จะถูก "ข้าม" พร้อมบันทึก status=skipped_compute_infeasible และค่าประมาณ
#      ลงคอลัมน์ expected_point_s — ไม่ใช่ Memory Wall แต่เป็น compute wall ที่มาถึงก่อน
#      (ใช้ --force-infeasible ถ้าต้องการดันทุรังรันจริง ๆ)
#
# *** resume (ค่าเริ่มต้น): มีแถวใน memory_wall.csv = จุดนั้น "เสร็จสิ้น" แล้วไม่ว่า
# ผลจะเป็นอะไร (ok, build_or_upload_fail, skipped_compute_infeasible, ...) — resume ข้าม
# ได้เลย ไม่ต้องแตะฮาร์ดแวร์ซ้ำ วงจรที่เคยเจอ "กำแพงจริง" แล้ว (build_or_upload_fail,
# runtime_hang_or_reset หลัง retry หมด) จะไม่ถูกลอง n ที่สูงกว่านั้นซ้ำอีก แม้ n เหล่านั้น
# ไม่เคยมี record ก็ตาม (ตรรกะเดียวกับที่ sweep เดิม break ออกจาก n-loop ทันทีที่เจอ
# กำแพง) แถวกำพร้าใน raw CSV (จุดที่โปรเซสตายระหว่างเขียนผล ไม่มี terminal record คู่กัน)
# จะถูกกวาดทิ้งก่อนแล้วรันจุดนั้นใหม่ทั้งหมด — ห้าม "เติม" ให้ครบ 100 trial เพราะ trial
# จาก 2 sessions ไม่ใช่ตัวอย่างสม่ำเสมอเดียวกัน (บอร์ด reset/reflash/อุณหภูมิเครื่องต่างกัน
# ระหว่าง session) ใช้ --fresh เพื่อย้ายผลลัพธ์เดิมออกไป (ไม่ลบทิ้ง) แล้วเริ่มนับใหม่หมด
# — ดู pc/shared/resume.py สำหรับเหตุผลเต็ม ***
#   4. เขียนทุกแถวลง data/raw/phase2/uno/<circuit>/raw.csv (ไฟล์ดิบ ไม่ทับข้อมูลเดิม,
#      append) และสรุป Memory Wall ต่อจุดข้อมูลลง .../phase2/memory_wall.csv (คอลัมน์
#      retry_count: 0 = สำเร็จ/ล้มเหลวตั้งแต่ครั้งแรก, 1+ = ต้อง retry ก่อนได้ผลลัพธ์นี้
#      — ไม่ว่าผลจะเป็น ok หรือ wall จริงก็ตาม) — เส้นทางนี้มาจาก pc/shared/paths.py
#      (2026-09-20: ย้ายจาก data/raw/phase2/uno_*.csv ที่ทุกวงจรใช้ไฟล์เดียวกันมาเป็น
#      หนึ่งไดเรกทอรีต่อ (board, circuit) ดู run_log.md "per-board per-algorithm layout")
#
# การใช้งาน:
#   .venv/bin/python pc/phase2_sweep/uno_sweep.py --port /dev/cu.usbmodemXXXX \
#       --circuits h_all bell_ghz qft grover qpe steane_encode --n-start 2 --n-max 12
#
# steane_encode คงที่ที่ n=7 เสมอ (pc/shared/circuit_ids.n_values_for_sweep จัดการ
# ให้อัตโนมัติ) — ถ้า n=7 ไม่อยู่ใน [n-start, n-max] ที่ขอ จะข้ามวงจรนี้ไปเฉย ๆ
#
# แต่ละ circuit ใน --circuits ตอนนี้เป็น session ของตัวเอง (ไดเรกทอรี/sessions.csv/
# points.csv/env json แยกกันคนละชุด — ดู pc/shared/paths.py) ไม่ใช่ session เดียวที่
# ครอบทุกวงจรเหมือนเดิม เพราะ standing decision 3 (2026-09-20, run_log.md) กำหนดให้รัน
# ทีละวงจรอยู่แล้วในทางปฏิบัติ ผลคือ pending_settle (ดู UPLOAD_SYNC_FAILURE_MARKERS
# ด้านล่าง) ไม่ข้าม circuit boundary อีกต่อไปแม้จะยังอยู่ใน process เดียวกัน — ยังคง
# ทำงานถูกต้องข้าม n boundary ภายในวงจรเดียวกัน และไม่ได้กระทบการรันจริงเลยเพราะ
# ปกติมีแค่ 1 circuit ต่อการเรียกอยู่แล้ว

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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import serial

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared.circuit_ids import CIRCUIT_IDS, n_values_for_sweep  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared import resume as rs  # noqa: E402
from shared import telemetry as tel  # noqa: E402
from shared import la_capture as lac  # noqa: E402
from shared import paths as sp  # noqa: E402
from shared import upload_retry as ur  # noqa: E402

RESUME_KEY_SPEC = [("circuit", str), ("n", int)]

FW_DIR = REPO_ROOT / "firmware" / "uno"
PIO = os.environ.get("PIO_PATH") or shutil.which("pio")

BAUD = 115200
F_CPU = 16_000_000  # ATmega328P — เมตาดาต้าเท่านั้น ไม่ได้ใช้คำนวณอะไร
BOOT_WAIT_S = 1.0  # เผื่อบอร์ด reset ตัวเองหลัง upload แล้วเริ่ม setup() ใหม่
# เวลารอสูงสุดต่อจุดข้อมูลไม่ใช่ค่าคงที่อีกต่อไป — คำนวณต่อ (circuit, n) จาก
# pc/shared/timing_model.timeout_budget_s() ดูเหตุผลใน header ของไฟล์นี้
TOTAL_SRAM_BYTES = 2048  # ATmega328P

# avrdude's STK500 bootloader handshake failing to sync — observed twice in the
# 2026-09-20 Session A run (qft n=2 at 11.3% RAM, steane_encode n=7 at 60.3%
# RAM — nowhere near overflow), both landing ~6ms after a hard_timeout=true
# (signal.alarm-interrupted) serial read on the immediately preceding point.
# Root cause: read_serial_trials() DID close the pyserial handle on that path
# (finally: ser.close(), see below) but nothing then waited for the OS/bootloader
# to actually release the port before the next build_and_upload() touched it.
# The fix here is the proactive settle (pending_settle, set whenever a point
# ends in hard_timeout=true OR an upload-stage failure, consumed once before
# the very next build_and_upload call regardless of which point that is for)
# — the retry loop below is a safety net for when the settle alone isn't
# enough, not the fix itself.
#
# UPLOAD_SYNC_FAILURE_MARKERS is a signature match used only for the printed
# label/log (not for retry eligibility, which is stage-based — see
# is_upload_stage_failure below) so this can never fire on a genuine
# build_overflow, and classify_build_failure()'s output (still
# "build_or_upload_fail") and points.csv's failure_type (still "build") are
# both unchanged by any of this.
UPLOAD_SYNC_FAILURE_MARKERS = (
    "stk500_getsync",
    "not in sync",
    "programmer is not responding",
)
UPLOAD_RETRY_SETTLE_S_DEFAULT = 2.0

# Standing operator decision 1 (2026-09-20, see run_log.md): an upload failure
# (avrdude never got a working handshake — as opposed to a deterministic
# compile error or a genuine RAM/flash overflow) gets up to 3 attempts total
# at the same n before the point is logged failed and the sweep moves on to
# the NEXT n in the SAME circuit (never abandons the circuit). Two consecutive
# n values that each exhaust all 3 attempts stop the whole run — that pattern
# means the point failures aren't independent (cable/port/hardware problem),
# not that n=2 has been reached. Constants and the stage classifier now live
# in pc/shared/upload_retry.py so esp8266_sweep.py/esp32_sweep.py share the
# exact same policy instead of drifting copies (2026-09-22, see run_log.md
# "port upload-retry to ESP boards").
UPLOAD_MAX_ATTEMPTS = ur.UPLOAD_MAX_ATTEMPTS
CONSECUTIVE_UPLOAD_FAIL_LIMIT = ur.CONSECUTIVE_UPLOAD_FAIL_LIMIT


def is_upload_sync_failure(log: str) -> bool:
    return ur.is_upload_sync_failure(log, UPLOAD_SYNC_FAILURE_MARKERS)


def is_upload_stage_failure(build_status: str, result: dict) -> bool:
    """True iff this failure happened during the upload step (avrdude), not
    during compile — i.e. compile succeeded (ram_pct is meaningful) and the
    subsequent `pio run -t upload` is what failed. See
    pc/shared/upload_retry.is_upload_stage_failure for the full docstring —
    it's stage-based, not log-signature-based, so it also covers avrdude
    failures whose log text doesn't match UPLOAD_SYNC_FAILURE_MARKERS."""
    return ur.is_upload_stage_failure(build_status, result)


def port_still_enumerated() -> bool:
    """Best-effort check that some Uno-shaped port still exists before
    retrying an upload — if the board really disconnected, retrying just
    wastes attempts this policy allows."""
    return bool(glob.glob("/dev/cu.usbmodem*"))


# pc/shared/upload_retry.ConsecutiveUploadFailuresError — shared across
# uno/esp8266/esp32 sweeps now (2026-09-22). Message gained a board prefix
# ("uno circuit=..." instead of bare "circuit=...") as part of that sharing;
# nothing reads the message text programmatically (only e.circuit/e.n_prev/
# e.n_cur below and SystemExit code 2, both unchanged).
ConsecutiveUploadFailuresError = ur.ConsecutiveUploadFailuresError


def find_uno_port(hint: str) -> str:
    """สแกนหา port ใหม่ทุกครั้ง เพราะ Uno R3 (USB-CDC) อาจ re-enumerate เปลี่ยน
    path กลางการ upload ได้ (พบจริงระหว่างทดสอบ: /dev/cu.usbmodem101 ->
    /dev/cu.usbmodem1101) ใช้ hint (path เดิม) เป็นตัวช่วยจับคู่ prefix เท่านั้น"""
    candidates = sorted(glob.glob("/dev/cu.usbmodem*"))
    if not candidates:
        return hint  # ให้ avrdude ลองเอง แล้วรายงาน error ตามจริง
    if hint in candidates:
        return hint
    return candidates[0]


def build_and_upload(circuit: str, n: int, port_hint: str, build_timeout_s=None):
    """แยก compile กับ upload เป็นสอง subprocess (เดิมเป็นคำสั่งเดียว `-t upload` ที่
    ทำทั้งสองอย่างในตัว) เพื่อจับเวลาแยกกันได้จริง (compile_s, upload_s) — PlatformIO
    ทำ dependency tracking เอง: เรียก `pio run` เฉย ๆ (compile) แล้วเรียก `-t upload`
    ต่อจะไม่ compile ซ้ำถ้าไม่มีอะไรเปลี่ยน จึงยังเป็นพฤติกรรมเดิมทุกประการ แค่วัดเป็น
    2 ช่วงแทนช่วงเดียว — เวลารวม (compile_s+upload_s) ควรใกล้เคียงของเดิมมาก

    คืน dict เดียว (ไม่ใช่ tuple) เพราะจำนวนค่าที่ต้องส่งกลับเพิ่มขึ้นมากจนใช้ positional
    tuple แล้วอ่านโค้ดเรียกยาก"""
    if build_timeout_s is None:
        build_timeout_s = tm.BUILD_TIMEOUT_S
    port = find_uno_port(port_hint)
    env = os.environ.copy()
    env.update({"N_QUBITS": str(n), "CIRCUIT_ID": str(CIRCUIT_IDS[circuit])})

    timed_out = False
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [PIO, "run", "-e", "uno"],
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
    compile_ok = c_rc == 0

    if not compile_ok:
        return {"ok": False, "ram_pct": ram_pct, "ram_bytes": ram_bytes,
                "log": c_stdout[-4000:] + c_stderr[-2000:], "port": port,
                "compile_s": compile_s, "upload_s": 0.0, "stage": "compile",
                "timed_out": timed_out}

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [PIO, "run", "-e", "uno", "-t", "upload", "--upload-port", port],
            cwd=str(FW_DIR), env=env, capture_output=True, text=True, timeout=build_timeout_s,
        )
        u_stdout, u_stderr, u_rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        u_stdout = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        u_stderr = f"pio run (upload) timed out after {build_timeout_s}s (stuck avrdude / stuck port)"
        u_rc = -1
        timed_out = True
    upload_s = time.perf_counter() - t0

    ok = u_rc == 0
    return {"ok": ok, "ram_pct": ram_pct, "ram_bytes": ram_bytes,
            "log": u_stdout[-4000:] + u_stderr[-2000:], "port": port,
            "compile_s": compile_s, "upload_s": upload_s, "stage": "upload",
            "timed_out": timed_out}


class HardTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise HardTimeout()


# 2026-09-22 standing decision (Phase 2 ceiling removed, see timing_model.py's
# CEILING_S comment): a point no longer gives up automatically after some
# fixed budget -- it runs until DONE, until the operator manually stops it
# (Ctrl+C), or until STUCK_READ_ALARM_S fires (a real OS/pyserial-level stuck
# read, NOT "this is taking a long time" -- see the comment this replaced:
# pyserial's readline() timeout alone once failed to return for 16+ minutes
# despite timeout=2). Re-armed every loop iteration (readline() itself already
# returns every ~2s in the normal case via its own timeout=2), so this only
# ever fires if a SINGLE readline() call itself never returns control at all.
STUCK_READ_ALARM_S = 900  # 15 min

# how often to print reps-received / ETA while waiting -- replaces the old
# ceiling's role of bounding how long an operator sits without status
PROGRESS_INTERVAL_S = 1800  # 30 min


def _print_progress(circuit, n, n_rows, target_reps, start_monotonic, expected_s):
    elapsed = time.perf_counter() - start_monotonic
    if n_rows > 0:
        remaining_s = (elapsed / n_rows) * max(target_reps - n_rows, 0)
        source = "observed rate"
    else:
        remaining_s = max((expected_s or 0.0) - elapsed, 0.0)
        source = "model estimate, no reps received yet"
    finish_clock = (datetime.now() + timedelta(seconds=remaining_s)).strftime("%H:%M")
    print(f"\n-- progress {circuit} n={n}: {n_rows}/{target_reps} reps received, "
          f"elapsed {tm.human_duration(elapsed)}, ETA {tm.human_duration(remaining_s)} "
          f"more (expected finish ~{finish_clock}, from {source})", flush=True)


def read_serial_trials(port: str, circuit: str, n: int, timeout_s: int,
                        expected_s: float = None, target_reps: int = None):
    """เปิด serial แล้วอ่านจนเจอ DONE, ถูกหยุดโดยผู้ควบคุม (Ctrl+C), หรือเจอ
    stuck-read จริง (ดู STUCK_READ_ALARM_S) — ไม่มี automatic give-up จาก
    budget อีกต่อไป (2026-09-22, ดู timing_model.py's CEILING_S comment)
    `timeout_s`/`expected_s` ใช้แค่แสดง ETA เท่านั้น ไม่ใช่ hard cutoff แล้ว

    คืนค่า (done, rows, note) เหมือนเดิม ยกเว้น done ตอนนี้มี 3 ค่าที่เป็นไปได้:
    True (DONE จริง), False (hang/reset/stuck-read), None (ผู้ควบคุมหยุดเอง —
    `rows` ยังมีข้อมูลที่เก็บมาได้แล้วอยู่ ไม่ทิ้ง — ดู resume.py's
    stopped_by_operator)
    """
    rows = []
    reset_count = 0
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    ser = None
    start_monotonic = time.perf_counter()
    last_progress = start_monotonic
    if target_reps is None:
        target_reps = tm.REPS
    try:
        ser = serial.Serial(port, BAUD, timeout=2)
        done = False
        while True:
            signal.alarm(STUCK_READ_ALARM_S)
            try:
                line = ser.readline().decode("utf-8", errors="replace").strip()
            finally:
                signal.alarm(0)
            now = time.perf_counter()
            if now - last_progress >= PROGRESS_INTERVAL_S:
                _print_progress(circuit, n, len(rows), target_reps, start_monotonic, expected_s)
                last_progress = now
            if not line:
                continue
            if line == "DONE":
                done = True
                break
            if line.startswith("uno,"):
                rows.append(line)
            elif line.startswith("board,circuit"):
                # header ซ้ำ = บอร์ด reset กลางทาง (watchdog/brown-out/stack overflow)
                reset_count += 1
                rows.clear()  # เริ่มนับ trial ใหม่หลัง reset
        return done, rows, f"reset_count={reset_count}"
    except serial.SerialException as e:
        return False, [], f"serial_error={e}"
    except HardTimeout:
        return False, rows, f"hard_timeout=true,reset_count={reset_count}"
    except KeyboardInterrupt:
        # 2026-09-22: caught HERE (not left to propagate) so `rows` -- whatever
        # was already received -- isn't lost. done=None is the sentinel the
        # caller checks for explicitly (both True and False are meaningfully
        # different from "the operator chose to stop").
        print(f"\n-- Ctrl+C: stopping {circuit} n={n} -- {len(rows)} rep(s) already "
              "received will be saved as a resumable partial point")
        return None, rows, "operator_stop"
    finally:
        # เดิม: `with serial.Serial(...) as ser:` ปิด handle ให้ตอน exception หลุดออก
        # จาก with-block อยู่แล้วก็จริง แต่ปิดแบบ implicit และไม่มีใครรอ/ตรวจว่า OS
        # ปล่อย port จริงก่อนที่ build_and_upload() ครั้งถัดไปจะเปิดมันอีกที — root
        # cause ของ avrdude "not in sync" ที่เกิด ~6ms หลัง hard_timeout=true (ดู
        # UPLOAD_SYNC_FAILURE_MARKERS comment ด้านบน) เขียนให้ explicit ตรงนี้แทน
        # เพื่อให้ทดสอบ/log ได้ตรง ๆ ว่า "port ถูกปิดแล้ว" ก่อนคืนค่ากลับไปให้
        # _sweep_body ตั้ง pending_settle — ใช้ getattr แทนการ assume ว่า ser มี
        # close()/is_open เสมอ เพราะเทสต์อื่นในโค้ดเบสนี้ (telemetry_test.py's
        # _FakeSerial) แทนที่ serial.Serial ด้วย double ที่ implement แค่
        # __enter__/__exit__ ไม่ใช่ close()/is_open ตรง ๆ
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
        if ser is not None:
            close = getattr(ser, "close", None)
            if close is not None and getattr(ser, "is_open", True):
                close()


def _write_raw_rows(raw_w, rows, budget_s, reps_already_done, cap_at=None):
    """เขียนแถว raw trial ที่เพิ่งได้มาลง raw.csv พร้อม relabel คอลัมน์ rep (index 3
    เสมอทุกบอร์ด) ให้ต่อจาก reps_already_done แทนเลขที่เฟิร์มแวร์รายงานเอง (2026-09-22,
    resumable stopped_by_operator points — เฟิร์มแวร์นับ rep 0..REPS-1 ใหม่ทุกครั้งที่
    reflash เสมอ ไม่รู้จัก "resume" — ดู resume.py) `cap_at` จำกัดจำนวนแถวที่เขียนไม่ให้
    เกินที่ยังต้องการจริง (ใช้ตอน resume จุดที่เหลือน้อยกว่า REPS เต็ม) คืนจำนวนแถวที่
    เขียนจริง"""
    kept = rows if cap_at is None else rows[:cap_at]
    for i, line in enumerate(kept):
        parts = line.split(",")
        parts[3] = str(reps_already_done + i)
        raw_w.writerow(parts + [budget_s])
    return len(kept)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="เช่น /dev/cu.usbmodem1101")
    ap.add_argument("--circuits", nargs="+",
                     default=["h_all", "bell_ghz", "qft", "grover", "qpe", "steane_encode"])
    ap.add_argument("--n-start", type=int, default=2)
    ap.add_argument("--n-max", type=int, default=14)
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
                          "ตีความเป็นกำแพง ค่าเริ่มต้นมาจาก timing_model.WDT_PER_REP_THRESHOLD_S "
                          "(uno=ไม่มีเกณฑ์ เพราะ AVR core ไม่เปิด watchdog)")
    ap.add_argument("--fresh", "--no-resume", dest="fresh", action="store_true",
                     help="ไม่ resume จากผลลัพธ์เดิม — ย้ายไฟล์ raw/memory_wall เดิมไปเป็น "
                          "*.pre-fresh-<timestamp>.csv (ไม่ลบทิ้ง) แล้วเริ่มนับใหม่หมด")
    ap.add_argument("--upload-retry-settle-s", type=float, default=UPLOAD_RETRY_SETTLE_S_DEFAULT,
                     help="วินาทีที่รอก่อน retry เมื่อเจอ avrdude STK500 sync failure "
                          "(signature match เท่านั้น เช่น stk500_getsync, ไม่ใช่ปัญหา "
                          "หน่วยความจำ) แล้วเช็คว่า port ยังอยู่ก่อน retry จริง — "
                          f"ค่าเริ่มต้น {UPLOAD_RETRY_SETTLE_S_DEFAULT}s "
                          "retry ได้ครั้งเดียวและยังอยู่ภายใต้กติกา budget<=600s เดิม")
    ap.add_argument("--la", action="store_true",
                     help="เปิด Logic Analyzer capture ผ่าน sigrok-cli ต่อจุดข้อมูล "
                          "(ค่าเริ่มต้นปิด — พฤติกรรมเมื่อปิดเหมือนเดิมทุกประการ ไม่มีการ "
                          "เรียก sigrok-cli เลยแม้แต่ครั้งเดียว) UNVERIFIED: sigrok-cli "
                          "command lines ไม่เคยรันกับฮาร์ดแวร์จริง (ดู "
                          "pc/shared/la_capture.py และ run_checklist.md ส่วน 'sigrok-cli "
                          "command lines — UNVERIFIED') ต้องมี capture_plan.csv อยู่แล้วใน "
                          "la/ ของ circuit นั้น (จาก analysis/la_capture_plan.py) และ "
                          "sigrok-cli บน PATH พร้อมอุปกรณ์ที่ตรวจเจอ ไม่งั้นจะรันต่อโดยไม่ "
                          "capture (ไม่ใช่ error)")
    args = ap.parse_args()

    # --la ปิด (ค่าเริ่มต้น): la_active คงเป็น False เสมอ ไม่มีการเรียก lac.* แม้แต่ครั้ง
    # เดียวตลอดทั้งการรัน — พฤติกรรมจึงเหมือนก่อนมี flag นี้ทุกประการ (ดู
    # pc/shared/la_capture_test.py "flag off = unchanged behavior") ตรวจ sigrok-cli
    # ครั้งเดียวต่อ process (ไม่ผูกกับ circuit ใดวงจรหนึ่ง)
    la_active = False
    if args.la:
        scan = lac.check_sigrok()
        print(f"[la] sigrok-cli check: {scan['note']}")
        la_active = scan["available"]
        if not la_active:
            print("[la] continuing WITHOUT capture (sigrok-cli unavailable or no device found)")

    try:
        for circuit in args.circuits:
            print(f"\n=== circuit={circuit} ===")
            _run_circuit(args, circuit, la_active)
    except ConsecutiveUploadFailuresError as e:
        # standing decision 1 (2026-09-20): stop the whole run, don't crash past
        # the point of having flushed everything collected so far (_run_circuit's
        # own try/finally already closed that circuit's raw/wall file handles and
        # its SessionRecorder's __exit__ already wrote a session row noting the
        # exception before it got here).
        print(f"\n!!! STOPPING RUN: {e}")
        print(f"raw -> {sp.raw_csv_path('uno', e.circuit, la=la_active)}\n"
              f"memory wall -> {sp.memory_wall_csv_path('uno', e.circuit, la=la_active)}")
        print(f"telemetry -> {sp.sessions_csv_path('uno', e.circuit, la=la_active)}, "
              f"{sp.points_csv_path('uno', e.circuit, la=la_active)}")
        sys.exit(2)
    except rs.OperatorStoppedError as e:
        # 2026-09-22 standing decision: operator pressed Ctrl+C mid-point --
        # the partial point (rows + a resumable stopped_by_operator status)
        # was already written and flushed before this was raised (see
        # read_serial_trials/_sweep_body). Exit code 130 matches the usual
        # Ctrl+C convention (128+SIGINT).
        print(f"\n!!! STOPPED BY OPERATOR: {e}")
        print(f"raw -> {sp.raw_csv_path('uno', e.circuit, la=la_active)}\n"
              f"memory wall -> {sp.memory_wall_csv_path('uno', e.circuit, la=la_active)}")
        print(f"re-run the exact same command to continue collecting the remaining "
              f"{e.total_reps - e.reps_completed} rep(s) for {e.circuit} n={e.n}")
        sys.exit(130)


def _run_circuit(args, circuit, la_active):
    """Set up this one algorithm's directory/files/telemetry session, run its
    sweep, and close everything down again — one call per circuit in
    args.circuits. Each circuit is now a fully independent unit (own raw dir,
    own points.csv/sessions.csv/env json — see pc/shared/paths.py), matching
    standing decision 3 (one algorithm at a time)."""
    n_values = n_values_for_sweep(circuit, args.n_start, args.n_max)
    if not n_values:
        print(f"skip: {circuit} is fixed-n and its n is outside [{args.n_start}, {args.n_max}]")
        return

    # no_la/with_la split (2026-09-22, see pc/shared/paths.py): la_active, not
    # args.la, decides the bucket -- if --la was passed but sigrok-cli turned
    # out unavailable/no device found, la_active is already False and no
    # capture is ever attempted (see the la_active computation in main()), so
    # this point belongs under no_la exactly like an ordinary run, not
    # with_la (which means "a capture was actually attempted").
    raw_directory = sp.raw_dir("uno", circuit, phase=2, la=la_active)
    raw_directory.mkdir(parents=True, exist_ok=True)
    raw_path = sp.raw_csv_path("uno", circuit, la=la_active)
    wall_path = sp.memory_wall_csv_path("uno", circuit, la=la_active)
    points_csv = sp.points_csv_path("uno", circuit, la=la_active)
    sessions_csv = sp.sessions_csv_path("uno", circuit, la=la_active)
    env_directory = sp.env_dir("uno", circuit, la=la_active)

    if la_active:
        # per-circuit LA dir/plan/issues-log — reassigning these module attributes
        # is the same redirection mechanism the tests already use (see
        # la_capture_test.py); load_plan_entry() resolves plan_path=None at call
        # time, not at def time, so this reassignment actually takes effect (a
        # latent bug fixed 2026-09-20 during this migration — see its docstring)
        lac.LA_DIR = sp.la_dir("uno", circuit, phase=2)
        lac.PLAN_PATH = lac.LA_DIR / "capture_plan.csv"
        lac.ISSUES_LOG = lac.LA_DIR / "capture_issues.log"

    # resume (ค่าเริ่มต้น): มีแถวใน wall CSV = จุดนั้น "เสร็จสิ้น" แล้วไม่ว่าผลจะเป็นอะไร
    # (ok, build_or_upload_fail, skipped_compute_infeasible, ...) ข้ามได้เลย ไม่ต้องแตะ
    # ฮาร์ดแวร์ซ้ำ ส่วนแถวกำพร้าใน raw CSV (จุดที่โปรเซสตายระหว่างเขียนผล ไม่มี terminal
    # record คู่กัน) ต้องกวาดทิ้งก่อน แล้วรันจุดนั้นใหม่ทั้งหมด — ห้าม "เติม" ให้ครบ 100
    # trial เพราะ trial จาก 2 sessions ไม่ใช่ตัวอย่างสม่ำเสมอเดียวกัน (reset บอร์ด/reflash/
    # อุณหภูมิต่างกัน) ดู pc/shared/resume.py สำหรับเหตุผลเต็ม
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
                        "free_heap_before", "free_heap_after", "timeout_budget_s"])
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
        infeasible = tm.print_budget_plan("uno", planned, phase=2)
        if args.force_infeasible:
            print("--force-infeasible: จะพยายามรันจุดที่เกินเพดานด้วย\n")
            infeasible = set()

        # resume summary: เวลาที่เหลือประมาณจากจุดที่ "เหลือและทำได้จริง" เท่านั้น — จุดที่
        # infeasible ถูกข้ามเกือบจะทันที (แค่พิมพ์แล้วบันทึก) จึงไม่นับรวมเวลาประเมินมหาศาล
        # ของมัน (เช่น 95 วัน) ปนเข้าไปในตัวเลข "เหลืออีกกี่ชั่วโมง" ที่ผู้ใช้จะดูจริง
        remaining_preview = [p for p in planned if p not in completed]
        real_remaining = [p for p in remaining_preview if p not in infeasible]
        est_s = sum(tm.expected_point_time_s("uno", c, n) for c, n in real_remaining)
        n_inf_remaining = len(remaining_preview) - len(real_remaining)
        remaining_human = tm.human_duration(
            sum(tm.point_wall_estimate_s("uno", c, n) for c, n in real_remaining))
        if n_inf_remaining:
            remaining_human += f" (+{n_inf_remaining} infeasible point(s), skipped near-instantly)"
        rs.print_resume_summary("uno", planned, completed, remaining_human)
        wall_n_by_circuit = rs.known_wall_n(completed)

        # telemetry: session wrapper + environment metadata ครั้งเดียวตอน circuit นี้เริ่ม
        # (ไม่ใช่ต่อจุด) — ดู pc/shared/telemetry.py สำหรับ schema เต็มและเหตุผลที่แยกจาก
        # raw.csv/memory_wall.csv เดิมโดยสิ้นเชิง (ไม่แตะ resume logic ที่ทดสอบแล้ว)
        resumed_from_previous = bool(completed)
        last_end = (tel.last_session_end_utc("uno", 2, sessions_csv=sessions_csv)
                    if resumed_from_previous else None)
        session = tel.SessionRecorder(phase=2, board="uno", circuits=[circuit],
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
                session.session_id, "uno", args.port, BAUD, F_CPU, FW_DIR / "src",
                env_dir=env_directory, pio_project_dir=FW_DIR, pio_env="uno", la=la_active)
            session.env_json_path = str(env_path)

            _sweep_body(args, circuit, n_values, completed, wall_n_by_circuit, infeasible,
                        raw_w, raw_f, wall_w, wall_f, session, la_active, points_csv)
    finally:
        raw_f.close()
        wall_f.close()

    print(f"\nraw -> {raw_path}\nmemory wall -> {wall_path}")
    print(f"telemetry -> {sessions_csv}, {points_csv}")


def _sweep_body(args, circuit, n_values, completed, wall_n_by_circuit, infeasible,
                 raw_w, raw_f, wall_w, wall_f, session, la_active, points_csv):
    # ข้าม n boundary ภายในวงจรนี้ — เรื่องพอร์ตทางกายภาพไม่รู้จัก n boundary ตั้งครั้งเดียว
    # หลัง hard_timeout=true หรือ upload-stage failure ใด ๆ แล้วถูก "ใช้" ครั้งเดียวก่อน
    # build_and_upload ครั้งถัดไป ไม่ว่าจะเป็น n ไหนก็ตาม (ดู UPLOAD_SYNC_FAILURE_MARKERS
    # comment ด้านบนสำหรับ root cause ที่ตรงนี้แก้) — ไม่ข้าม circuit boundary อีกต่อไป
    # เพราะแต่ละ circuit เป็นการเรียก _sweep_body แยกกันแล้ว (ดู module docstring ด้านบน)
    pending_settle = False
    pending_settle_reason = None

    # standing decision 1 (2026-09-20): two consecutive n values that each
    # exhaust all UPLOAD_MAX_ATTEMPTS upload attempts stop the whole run.
    # Skipped points (resume/infeasible) leave this untouched -- they aren't a
    # hardware attempt either way.
    prev_upload_exhausted_n = None

    for n in n_values:
        skip_ts = datetime.now(timezone.utc).isoformat()
        reps_already_done = 0
        if (circuit, n) in completed:
            prior_status = completed[(circuit, n)].get("status", "?")
            # 2026-09-22 standing decision: a stopped_by_operator point (Ctrl+C
            # mid-collection, see read_serial_trials) is the ONE resume case
            # that is NOT skipped outright -- it's resumed and the remaining
            # reps are appended (see resume.py's module comment for why this
            # is a deliberate, informed exception to the usual
            # never-mix-sessions rule: the operator chose to stop, it's not an
            # unexplained crash/orphan).
            if rs.is_operator_stopped_status(prior_status):
                reps_already_done = rs.parse_operator_stopped_reps(prior_status)
            if not rs.is_operator_stopped_status(prior_status) or reps_already_done >= tm.REPS:
                print(f"n={n:2d}  SKIP (resume): already {prior_status}")
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 2, "board": "uno",
                    "circuit": circuit, "n": n, "attempt_index": 0,
                    "start_utc": skip_ts, "end_utc": skip_ts, "wall_s": 0,
                    "retry_count": 0, "timeout_hit": False, "failure_type": "none",
                    "status": "skipped_resume",
                }, points_csv)
                session.note_point(status="skipped_resume")
                continue
            print(f"n={n:2d}  RESUME partial (operator-stopped previously at "
                  f"{reps_already_done}/{tm.REPS} reps) -- collecting the remaining "
                  f"{tm.REPS - reps_already_done}")
        if circuit in wall_n_by_circuit and n > wall_n_by_circuit[circuit]:
            print(f"n={n:2d}  SKIP (resume): {circuit} already hit its wall at "
                  f"n={wall_n_by_circuit[circuit]} in a previous session")
            tel.write_point_row({
                "session_id": session.session_id, "phase": 2, "board": "uno",
                "circuit": circuit, "n": n, "attempt_index": 0,
                "start_utc": skip_ts, "end_utc": skip_ts, "wall_s": 0,
                "retry_count": 0, "timeout_hit": False, "failure_type": "none",
                "status": "skipped_known_wall",
            }, points_csv)
            session.note_point(status="skipped_known_wall")
            continue

        theoretical_bytes = (1 << n) * 8
        budget_s = tm.timeout_budget_s("uno", circuit, n)
        expected_s = tm.expected_point_time_s("uno", circuit, n)
        may_retry = tm.retry_allowed(budget_s)
        retry_policy = "allowed" if may_retry else "skipped_high_budget"
        ts = datetime.now(timezone.utc).isoformat()

        if (circuit, n) in infeasible:
            # 2026-09-22: `infeasible` is always empty for Phase 2 now (see
            # timing_model.is_compute_infeasible -- ceiling removed, standing
            # decision) -- this branch is unreachable in practice, kept only
            # so print_budget_plan()'s return value never needs a caller-side
            # special case and --force-infeasible stays a harmless no-op
            # rather than an error for anyone still passing it.
            # ไม่ใช่ Memory Wall และไม่ใช่ hang — เป็นขีดจำกัดเชิงเวลาคำนวณล้วน ๆ
            # บันทึกค่าประมาณไว้ด้วย เพื่อให้แถวนี้อ่านเป็น "ผลการทดลอง" ได้จริง
            print(f"n={n:2d}  SKIP compute-infeasible: expected "
                  f"{tm.human_duration(expected_s)} > ceiling {tm.CEILING_S}s")
            wall_w.writerow(["uno", circuit, n, theoretical_bytes, None, None,
                              "skipped_compute_infeasible", ts, 0,
                              budget_s, round(expected_s, 1), "n/a"])
            wall_f.flush()
            tel.write_point_row({
                "session_id": session.session_id, "phase": 2, "board": "uno",
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
        upload_fail_exhausted = False  # this point's terminal outcome: ran out of
        # all UPLOAD_MAX_ATTEMPTS upload attempts (standing decision 1) — set only
        # on the terminal (non-retry) branch of the upload-stage-failure path below

        # attempt loop: two independent retry policies share this loop, each
        # gated on the failure kind of the attempt that just happened, not on a
        # single shared attempt cap —
        #   - runtime hang/reset/watchdog/build_timeout: unchanged existing policy,
        #     one retry only (2 attempts total), gated by may_retry (budget rule,
        #     see timing_model.retry_allowed) — untouched by standing decision 1.
        #   - upload-stage failure (avrdude never got a working handshake):
        #     standing decision 1 (2026-09-20) — up to UPLOAD_MAX_ATTEMPTS (3)
        #     attempts total, NOT gated by the budget rule (reflash time doesn't
        #     scale with n the way device-run time does), and exhausting all 3
        #     does NOT stop climbing / does NOT abandon the circuit.
        #   - compile-time RAM>100% evidence (Uno linker exits 0 above 100%, see
        #     compile_ram_wall below): standing decision 2 — never retried, one
        #     attempt only, regardless of which of the above this attempt would
        #     otherwise have matched.
        attempt = 0
        while True:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                  f"n={n:2d}  theoretical={theoretical_bytes:6d} bytes  "
                  f"budget={budget_s}s (expected {tm.human_duration(expected_s)})  "
                  f"attempt={attempt + 1}  ", end="", flush=True)
            if attempt > 0:
                print("(retry) ", end="", flush=True)

            # root-cause fix (see UPLOAD_SYNC_FAILURE_MARKERS comment): settle +
            # re-enumeration check BEFORE this build_and_upload if the previous
            # action on the port ended in hard_timeout=true or an upload-stage
            # failure — applies whether this is a retry of the same point or the
            # next n in this circuit, since the port doesn't know about that
            # boundary. Logged into failure_message below (no new telemetry
            # column — SCHEMA_VERSION stays 2).
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

            # --la: arm the capture BEFORE build_and_upload (compile+upload+the
            # reset that actually starts the board running) — this can only add
            # time to the reflash phase (PC-side, outside any timed region), never
            # to the GPIO pulse or the micros() window it brackets.
            armed = None
            plan_entry = None
            if la_active:
                plan_entry = lac.load_plan_entry("uno", circuit, n)
                if plan_entry is None:
                    lac.log_issue("uno", circuit, n,
                                  "no capture_plan.csv entry for this point in this "
                                  "circuit's la/ dir — skipping capture (run "
                                  "analysis/la_capture_plan.py first)")
                else:
                    out_path = lac.LA_DIR / f"uno_{circuit}_n{n}.csv"
                    armed = lac.arm_capture("uno", circuit, n, plan_entry, out_path)
                    if armed is None:
                        print(f"[la] failed to arm capture for {circuit} n={n} "
                              "— continuing without capture for this point")

            attempt_start = datetime.now(timezone.utc).isoformat()
            result = build_and_upload(circuit, n, args.port, args.build_timeout_s)
            ts = datetime.now(timezone.utc).isoformat()
            args.port = result["port"]  # จำ port ล่าสุดที่ใช้สำเร็จ ไว้เป็น hint รอบถัดไป
            reflash_s = result["compile_s"] + result["upload_s"]
            point_reflash_s += reflash_s

            if armed is not None and not result["ok"]:
                # board never ran (build/upload failed before the reset that
                # starts it) — discard the capture, don't run analysis on it.
                # This must not touch the micros()/build failure handling below.
                lac.stop_capture(armed, "uno", circuit, n)
                lac.log_issue("uno", circuit, n, "build/upload failed — capture discarded")
                armed = None

            # standing decision 2 (2026-09-20): the Uno linker exits 0 even when
            # RAM usage is above 100% (documented toolchain quirk, docs/
            # preflight_report.md finding L2) — so compile_ram_pct evidence has
            # to be checked after a SUCCESSFUL build too, not only inside the
            # classify_build_failure() branch below which only ever runs when
            # result["ok"] is False. result["stage"] == "upload" is exactly
            # "compile succeeded" (build_and_upload() only ever returns
            # stage="compile" on the early-return path when compile itself
            # failed) so ram_pct is meaningful here regardless of whether the
            # later upload step succeeded.
            compile_succeeded = result.get("stage") == "upload"
            compile_ram_wall = (compile_succeeded and result["ram_pct"] is not None
                                 and result["ram_pct"] > 100.0)
            if compile_ram_wall and result["ok"]:
                # 2026-09-24 operator decision (supersedes the "run once anyway"
                # handling of decision 2): compile RAM > 100% is already positive
                # evidence of a Memory Wall, and running the point only burns
                # hours on a board that hangs/reset-loops (grover n=8: 0 reps in
                # 30 min). Stop here: no execution, no retry, record the wall.
                print(f"\ncompile_ram_pct={result['ram_pct']}% > 100% despite the linker "
                      "exiting 0 (Uno L2 quirk) -- Memory Wall. Not executing this point; "
                      "recorded as build_overflow.")
                if armed is not None:
                    lac.stop_capture(armed, "uno", circuit, n)
                    lac.log_issue("uno", circuit, n, "compile RAM > 100% — not executed, capture discarded")
                    armed = None
                wall_w.writerow(["uno", circuit, n, theoretical_bytes, result["ram_bytes"],
                                  result["ram_pct"], "build_overflow", ts, retry_used,
                                  budget_s, round(expected_s, 1), retry_policy])
                wall_f.flush()
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 2, "board": "uno",
                    "circuit": circuit, "n": n, "attempt_index": attempt,
                    "start_utc": attempt_start, "end_utc": ts,
                    "wall_s": round(reflash_s, 3),
                    "build_compile_s": round(result["compile_s"], 3),
                    "upload_s": round(result["upload_s"], 3),
                    "retry_count": retry_used, "timeout_hit": False,
                    "failure_type": "build",
                    "failure_message": f"compile_ram_pct={result['ram_pct']}% > 100%, not executed",
                    "status": "failed",
                }, points_csv)
                session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="failed")
                wall_found = True
                break

            if not result["ok"]:
                # แยกสาเหตุก่อนตัดสิน: timeout ของ toolchain ไม่ใช่กำแพง และ retry ได้
                # (ดู pc/shared/resume.classify_build_failure และ finding H2)
                build_status = rs.classify_build_failure(
                    result["log"], result["ram_pct"], result.get("timed_out", False))
                if compile_ram_wall:
                    build_status = "build_overflow"  # force-reclassify: upload/whatever
                    # else went wrong afterward doesn't matter, the positive RAM
                    # evidence from compile time already makes this a wall
                is_timeout = build_status == "build_timeout"
                is_upload_fail = (not compile_ram_wall
                                   and is_upload_stage_failure(build_status, result))
                # signature match เอาไว้ label/log เท่านั้น (ไม่ใช้ตัดสิน retry
                # eligibility อีกต่อไป — ดู is_upload_stage_failure)
                is_upload_sync = is_upload_stage_failure(build_status, result) and \
                    is_upload_sync_failure(result["log"])
                label = {
                    "build_overflow": "BUILD OVERFLOW -> Memory Wall (positive evidence: linker/RAM)",
                    "build_timeout": "BUILD TIMEOUT -> toolchain/host problem, NOT a wall",
                    "build_or_upload_fail": "UPLOAD/BUILD FAIL -> not a wall (no memory evidence)",
                }[build_status]
                print(label + ("  (matched upload-sync-failure signature)" if is_upload_sync else ""))
                print(result["log"][-800:])

                will_retry = False
                if compile_ram_wall:
                    will_retry = False  # decision 2: never retried
                elif is_timeout and attempt == 0 and may_retry:
                    will_retry = True
                elif is_upload_fail and attempt < UPLOAD_MAX_ATTEMPTS - 1:
                    will_retry = True

                failure_message = settle_note + result["log"][-300:]
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 2, "board": "uno",
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

                wall_w.writerow(["uno", circuit, n, theoretical_bytes, result["ram_bytes"], result["ram_pct"],
                                  build_status, ts, retry_used,
                                  budget_s, round(expected_s, 1), retry_policy])
                wall_f.flush()
                session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="failed")
                if upload_fail_exhausted:
                    # standing decision 1: an upload failure (even after
                    # exhausting all attempts) is never treated as a reason to
                    # stop climbing n in this circuit -- it carries no memory
                    # evidence at all, unlike the other STOP_CLIMB_PREFIXES cases.
                    wall_found = False
                    print(f"-- exhausted all {UPLOAD_MAX_ATTEMPTS} upload attempts for n={n} "
                          "-- NOT abandoning the circuit, continuing to the next n")
                else:
                    wall_found = rs.stops_climbing(build_status)
                break

            time.sleep(BOOT_WAIT_S)  # เผื่อบอร์ด reset ตัวเองหลัง upload แล้วเริ่ม setup() ใหม่
            remaining_needed = tm.REPS - reps_already_done
            exec_t0 = time.perf_counter()
            done, rows, note = read_serial_trials(find_uno_port(args.port), circuit, n, budget_s,
                                                   expected_s=expected_s, target_reps=tm.REPS)
            device_exec_s = time.perf_counter() - exec_t0
            point_device_s += device_exec_s
            if "hard_timeout=true" in note:
                pending_settle = True
                pending_settle_reason = f"hard_timeout on {circuit} n={n}"

            # --la: stop the capture after the point (regardless of the outcome
            # timed above, which is already fixed by this point) and only run
            # the analysis scripts if the point actually produced micros() data
            # to cross-check against. A capture/analysis problem is logged and
            # never changes `done`, `rows`, or anything written below.
            if armed is not None:
                cap_ok = lac.stop_capture(armed, "uno", circuit, n)
                if cap_ok and done:
                    expected_reps = plan_entry["n_reps_to_capture"] if plan_entry else len(rows)
                    lac.run_analysis("uno", circuit, n, armed.out_path, expected_reps)
                elif cap_ok and not done:
                    lac.log_issue("uno", circuit, n,
                                  "point did not complete (no DONE) — capture kept on disk "
                                  "but not analyzed, no micros() data to cross-check against")
                armed = None

            attempt_end = datetime.now(timezone.utc).isoformat()

            if done:
                # 2026-09-22: cap at remaining_needed and relabel `rep` to
                # continue from reps_already_done -- see _write_raw_rows and
                # resume.py's stopped_by_operator. For a fresh (non-resumed)
                # point reps_already_done=0 and remaining_needed=tm.REPS, so
                # this is a no-op change from the old "write every row"
                # behavior.
                n_written = _write_raw_rows(raw_w, rows, budget_s, reps_already_done,
                                             cap_at=remaining_needed)
                raw_f.flush()
                total_reps_now = reps_already_done + n_written
                if compile_ram_wall:
                    # decision 2: ran successfully once despite the RAM>100%
                    # evidence, per the recommended handling above -- the raw
                    # trial data collected is real and kept, but the point is
                    # still classified as a wall, not "ok".
                    wall_w.writerow(["uno", circuit, n, theoretical_bytes, result["ram_bytes"],
                                      result["ram_pct"], "build_overflow", ts, retry_used,
                                      budget_s, round(expected_s, 1), retry_policy])
                    wall_f.flush()
                    print(f"ran to completion (trials_captured={n_written}, "
                          f"total={total_reps_now}/{tm.REPS}) but "
                          f"compile_ram_pct={result['ram_pct']}% > 100% -- recorded as "
                          "build_overflow per decision 2, not ok")
                    tel.write_point_row({
                        "session_id": session.session_id, "phase": 2, "board": "uno",
                        "circuit": circuit, "n": n, "attempt_index": attempt,
                        "start_utc": attempt_start, "end_utc": attempt_end,
                        "wall_s": round(reflash_s + BOOT_WAIT_S + device_exec_s, 3),
                        "build_compile_s": round(result["compile_s"], 3),
                        "upload_s": round(result["upload_s"], 3),
                        "boot_wait_s": BOOT_WAIT_S, "device_exec_s": round(device_exec_s, 3),
                        "retry_count": retry_used, "timeout_hit": False,
                        "failure_type": "build", "status": "failed",
                    }, points_csv)
                    session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="failed")
                    wall_found = True
                    break
                wall_w.writerow(["uno", circuit, n, theoretical_bytes, result["ram_bytes"], result["ram_pct"],
                                  "ok", ts, retry_used,
                                  budget_s, round(expected_s, 1), retry_policy])
                wall_f.flush()
                suffix = f"  (succeeded after {retry_used} retry)" if retry_used else ""
                resumed_note = f"  (resumed, {reps_already_done} prior + {n_written} this attempt)" \
                    if reps_already_done else ""
                print(f"OK  compile_ram={result['ram_pct']}%  trials_captured={total_reps_now}"
                      f"{suffix}{resumed_note}\n      "
                      + tm.format_memory_note("uno", theoretical_bytes, rows,
                                               result.get("ram_pct"), result.get("ram_bytes")))
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 2, "board": "uno",
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

            if done is None:
                # 2026-09-22 standing decision: operator manually stopped this
                # point (Ctrl+C during read_serial_trials, see its docstring).
                # Whatever reps it collected THIS attempt are appended (capped
                # at what's actually still needed) and relabeled to continue
                # the logical 0..REPS-1 sequence -- kept as real, resumable
                # data, never discarded like a crash orphan (see resume.py's
                # module comment for why this is a deliberate exception).
                n_written = _write_raw_rows(raw_w, rows, budget_s, reps_already_done,
                                             cap_at=remaining_needed)
                raw_f.flush()
                total_reps_now = reps_already_done + n_written
                new_status = rs.format_operator_stopped_status(total_reps_now)
                wall_w.writerow(["uno", circuit, n, theoretical_bytes, result["ram_bytes"], result["ram_pct"],
                                  new_status, ts, retry_used,
                                  budget_s, round(expected_s, 1), retry_policy])
                wall_f.flush()
                print(f"-- operator-stopped: {total_reps_now}/{tm.REPS} reps saved "
                      f"({n_written} this attempt), resumable -- re-run the same "
                      "command to collect the rest")
                # points.csv's own status column is a closed enum
                # (telemetry.STATUS_TYPES, has no "stopped_by_operator" value
                # and this is supplementary per-attempt telemetry, not what
                # resume.py reads back) -- "failed" is the closest fit ("this
                # attempt did not reach ok"); the actual rich detail
                # (resumable, reps_completed=N) lives in memory_wall.csv's
                # free-text status column above, which resume.py DOES read.
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 2, "board": "uno",
                    "circuit": circuit, "n": n, "attempt_index": attempt,
                    "start_utc": attempt_start, "end_utc": attempt_end,
                    "wall_s": round(reflash_s + BOOT_WAIT_S + device_exec_s, 3),
                    "build_compile_s": round(result["compile_s"], 3),
                    "upload_s": round(result["upload_s"], 3),
                    "boot_wait_s": BOOT_WAIT_S, "device_exec_s": round(device_exec_s, 3),
                    "retry_count": retry_used, "timeout_hit": False,
                    "failure_type": "none", "status": "failed",
                }, points_csv)
                session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="failed")
                raise rs.OperatorStoppedError("uno", circuit, n, total_reps_now, tm.REPS)

            if compile_ram_wall:
                # decision 2: hung/reset instead of completing -- still no
                # retry, still forced to build_overflow (the compile-time
                # evidence alone is sufficient, don't need the run to succeed)
                wall_w.writerow(["uno", circuit, n, theoretical_bytes, result["ram_bytes"],
                                  result["ram_pct"], "build_overflow", ts, retry_used,
                                  budget_s, round(expected_s, 1), retry_policy])
                wall_f.flush()
                print(f"NO 'DONE' within {budget_s}s, and compile_ram_pct="
                      f"{result['ram_pct']}% > 100% -- recorded as build_overflow "
                      f"(no retry per decision 2), note={note}")
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 2, "board": "uno",
                    "circuit": circuit, "n": n, "attempt_index": attempt,
                    "start_utc": attempt_start, "end_utc": attempt_end,
                    "wall_s": round(reflash_s + BOOT_WAIT_S + device_exec_s, 3),
                    "build_compile_s": round(result["compile_s"], 3),
                    "upload_s": round(result["upload_s"], 3),
                    "boot_wait_s": BOOT_WAIT_S, "device_exec_s": round(device_exec_s, 3),
                    "retry_count": retry_used, "timeout_hit": True,
                    "failure_type": "build", "failure_message": note, "status": "failed",
                }, points_csv)
                session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="failed")
                wall_found = True
                break

            # ถ้าเวลาต่อ rep ที่ประเมินไว้เกินเกณฑ์ WDT ของบอร์ดนี้ การที่บอร์ดเงียบ
            # มีคำอธิบายที่เป็นไปได้มากกว่าหน่วยความจำ — บันทึกแยก และห้ามตีความเป็น
            # Memory Wall (ดู timing_model.watchdog_suspected, finding H1) — this is
            # standing decision 2's "hang without RAM evidence is NOT a wall,
            # logged as runtime_hang_or_reset for the owner to review"
            wdt_suspected = tm.watchdog_suspected("uno", circuit, n, args.wdt_threshold_s)
            status = (f"watchdog_suspected({note})" if wdt_suspected
                      else f"runtime_hang_or_reset({note})")
            tel.write_point_row({
                "session_id": session.session_id, "phase": 2, "board": "uno",
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
                      "-- transient failure, retrying once at same n "
                      "(deviation from n=30 methodology, see run_log.md)")
                attempt += 1
                continue

            tail = "(after retry)" if retry_used else f"(no retry: {retry_policy})"
            note_wall = "" if rs.is_wall_status(status) else "  [NOT recorded as a Memory Wall]"
            print(f"NO 'DONE' within {budget_s}s -> {status} {tail}{note_wall}")
            wall_w.writerow(["uno", circuit, n, theoretical_bytes, result["ram_bytes"], result["ram_pct"],
                              status, ts, retry_used,
                              budget_s, round(expected_s, 1), retry_policy])
            wall_f.flush()
            session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="failed")
            wall_found = rs.stops_climbing(status)
            break

        if upload_fail_exhausted:
            if prev_upload_exhausted_n is not None:
                raise ConsecutiveUploadFailuresError("uno", circuit, prev_upload_exhausted_n, n)
            prev_upload_exhausted_n = n
        else:
            prev_upload_exhausted_n = None

        if wall_found:
            break


if __name__ == "__main__":
    main()
