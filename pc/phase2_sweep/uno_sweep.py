#!/usr/bin/env python3
# uno_sweep.py — Phase 2 Edge Benchmark: ไล่ค่า n ขึ้นทีละ 1 จนบอร์ด Uno ล้มเหลว
#
# สำหรับแต่ละ (circuit, n):
#   1. build + upload firmware ด้วย -D N_QUBITS=<n> -D CIRCUIT_ID=<id>
#      (ถ้า build/upload ไม่ผ่าน = ล้มเหลวแบบ "link/upload fail" หยุดวงจรนี้ทันที ไม่ retry
#      เพราะเป็นผลลัพธ์ deterministic — retry ก็ได้ผลเดิม)
#   2. อ่านค่า RAM usage % ที่ avr-size รายงานตอน build (ค่าทางทฤษฎีเทียบค่าที่วัดจริง)
#   3. เปิด serial อ่านผลจากบอร์ด 100 trial ต่อจุดข้อมูล จนกว่าจะเจอ "DONE"
#      ถ้าไม่มี "DONE" ภายใน timeout = บอร์ด hang/reset -> ถือเป็นความล้มเหลวชั่วคราวได้
#      (สายหลุด, USB glitch) จึง retry ที่ n เดิมอีก 1 ครั้งก่อนสรุปว่าเป็น Memory Wall จริง
#      *** ข้อแตกต่างจากวิธีวัดของ dataset n=30: รอบนั้นไม่มี retry เลย ล้มเหลวครั้งแรก
#      ที่ n ไหนก็ถือเป็นกำแพงทันที รอบ n=100 นี้ผ่อนเกณฑ์ให้ทนความล้มเหลวชั่วคราวได้ 1
#      ครั้ง — ทำให้ตัวเลข Memory Wall ระหว่างสอง dataset "ไม่ได้เปรียบเทียบกันตรง ๆ
#      ได้ทันที" ต้องดูคอลัมน์ retry_count ใน *_memory_wall.csv ประกอบ (ดู run_log.md) ***
#   4. เขียนทุกแถวลง data/raw/phase2/uno_raw.csv (ไฟล์ดิบ ไม่ทับข้อมูลเดิม, append)
#      และสรุป Memory Wall ต่อจุดข้อมูลลง data/raw/phase2/uno_memory_wall.csv
#      (คอลัมน์ retry_count: 0 = สำเร็จ/ล้มเหลวตั้งแต่ครั้งแรก, 1 = ต้อง retry ก่อนได้
#      ผลลัพธ์นี้ — ไม่ว่าผลจะเป็น ok หรือ wall จริงก็ตาม)
#
# การใช้งาน:
#   .venv/bin/python pc/phase2_sweep/uno_sweep.py --port /dev/cu.usbmodemXXXX \
#       --circuits h_all bell_ghz qft grover qpe steane_encode --n-start 2 --n-max 12
#
# steane_encode คงที่ที่ n=7 เสมอ (pc/shared/circuit_ids.n_values_for_sweep จัดการ
# ให้อัตโนมัติ) — ถ้า n=7 ไม่อยู่ใน [n-start, n-max] ที่ขอ จะข้ามวงจรนี้ไปเฉย ๆ

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

FW_DIR = REPO_ROOT / "firmware" / "uno"
RESULTS_DIR = REPO_ROOT / "data" / "raw" / "phase2"
PIO = os.environ.get("PIO_PATH") or shutil.which("pio")

BAUD = 115200
SERIAL_TIMEOUT_S = 70  # เวลารอสูงสุดต่อจุดข้อมูล (100 trial, scaled from 20s@REPS=30)
TOTAL_SRAM_BYTES = 2048  # ATmega328P


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


def build_and_upload(circuit: str, n: int, port_hint: str):
    port = find_uno_port(port_hint)
    env_extra = {"N_QUBITS": str(n), "CIRCUIT_ID": str(CIRCUIT_IDS[circuit])}
    env = os.environ.copy()
    env.update(env_extra)

    try:
        proc = subprocess.run(
            [PIO, "run", "-e", "uno", "-t", "upload", "--upload-port", port],
            cwd=str(FW_DIR), env=env, capture_output=True, text=True, timeout=120,
        )
        stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        stderr = "pio run timed out after 120s (stuck avrdude / stuck port)"
        returncode = -1

    ram_pct, ram_bytes = None, None
    m = re.search(r"RAM:\s*\[.*?\]\s*([\d.]+)%\s*\(used (\d+) bytes", stdout)
    if m:
        ram_pct, ram_bytes = float(m.group(1)), int(m.group(2))
    ok = returncode == 0
    return ok, ram_pct, ram_bytes, stdout[-4000:] + stderr[-2000:], port


class HardTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise HardTimeout()


def read_serial_trials(port: str, circuit: str, n: int):
    """เปิด serial แล้วอ่านจนเจอ DONE หรือ timeout (=hang/reset)

    ใช้ signal.alarm บังคับ deadline แข็ง (hard deadline) ครอบทั้งฟังก์ชัน
    เพราะพบจริงระหว่างทดลองว่า pyserial's readline() timeout เพียงอย่างเดียว
    "ไม่" รับประกันว่าจะ return ตรงเวลาเสมอเมื่อพอร์ต USB-CDC ของ Uno หลุด
    (เจอค้างเกิน 16 นาทีทั้งที่ตั้ง timeout=2 มาแล้วครั้งหนึ่ง) — ถ้าไม่มี
    hard deadline นี้ การสวีปทั้งชุดจะค้างได้โดยไม่มีทางฟื้นเอง
    """
    rows = []
    reset_count = 0
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(SERIAL_TIMEOUT_S + 10)
    try:
        with serial.Serial(port, BAUD, timeout=2) as ser:
            deadline = time.time() + SERIAL_TIMEOUT_S
            done = False
            while time.time() < deadline:
                line = ser.readline().decode("utf-8", errors="replace").strip()
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
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="เช่น /dev/cu.usbmodem1101")
    ap.add_argument("--circuits", nargs="+",
                     default=["h_all", "bell_ghz", "qft", "grover", "qpe", "steane_encode"])
    ap.add_argument("--n-start", type=int, default=2)
    ap.add_argument("--n-max", type=int, default=14)
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RESULTS_DIR / "uno_raw.csv"
    wall_path = RESULTS_DIR / "uno_memory_wall.csv"

    raw_is_new = not raw_path.exists()
    wall_is_new = not wall_path.exists()
    raw_f = open(raw_path, "a", newline="")
    wall_f = open(wall_path, "a", newline="")
    raw_w = csv.writer(raw_f)
    wall_w = csv.writer(wall_f)
    if raw_is_new:
        raw_w.writerow(["board", "circuit", "n", "rep", "exec_time_us", "free_heap_before", "free_heap_after"])
    if wall_is_new:
        wall_w.writerow([
            "board", "circuit", "n", "theoretical_bytes", "compile_ram_used_bytes",
            "compile_ram_pct", "status", "timestamp_utc", "retry_count",
        ])

    for circuit in args.circuits:
        print(f"\n=== circuit={circuit} ===")
        n_values = n_values_for_sweep(circuit, args.n_start, args.n_max)
        if not n_values:
            print(f"skip: {circuit} is fixed-n and its n is outside [{args.n_start}, {args.n_max}]")
            continue
        for n in n_values:
            theoretical_bytes = (1 << n) * 8
            wall_found = False
            retry_used = 0

            # attempt 0 = ครั้งแรก, attempt 1 = retry เดียว — เฉพาะความล้มเหลวแบบ
            # runtime hang/reset/serial error เท่านั้นที่ retry ได้ (อาจเป็นสายหลุด/USB
            # glitch ชั่วคราว) build/upload fail ไม่ retry เพราะ deterministic
            for attempt in range(2):
                print(f"n={n:2d}  theoretical={theoretical_bytes:6d} bytes  ", end="", flush=True)
                if attempt == 1:
                    print("(retry) ", end="", flush=True)

                ok, ram_pct, ram_bytes, log, used_port = build_and_upload(circuit, n, args.port)
                ts = datetime.now(timezone.utc).isoformat()
                args.port = used_port  # จำ port ล่าสุดที่ใช้สำเร็จ ไว้เป็น hint รอบถัดไป

                if not ok:
                    print("UPLOAD/BUILD FAIL -> Memory Wall found (link/flash stage)")
                    wall_w.writerow(["uno", circuit, n, theoretical_bytes, ram_bytes, ram_pct,
                                      "build_or_upload_fail", ts, retry_used])
                    wall_f.flush()
                    print(log[-800:])
                    wall_found = True
                    break

                time.sleep(1.0)  # เผื่อบอร์ด reset ตัวเองหลัง upload แล้วเริ่ม setup() ใหม่
                done, rows, note = read_serial_trials(find_uno_port(args.port), circuit, n)

                if done:
                    for line in rows:
                        raw_w.writerow(line.split(","))
                    raw_f.flush()
                    wall_w.writerow(["uno", circuit, n, theoretical_bytes, ram_bytes, ram_pct,
                                      "ok", ts, retry_used])
                    wall_f.flush()
                    suffix = f"  (succeeded after {retry_used} retry)" if retry_used else ""
                    print(f"OK  compile_ram={ram_pct}%  trials_captured={len(rows)}{suffix}")
                    break

                status = f"runtime_hang_or_reset({note})"
                if attempt == 0:
                    retry_used = 1
                    print(f"NO 'DONE' within {SERIAL_TIMEOUT_S}s -> {status}  "
                          "-- transient failure, retrying once at same n before declaring "
                          "Memory Wall (deviation from n=30 methodology, see run_log.md)")
                    continue

                print(f"NO 'DONE' within {SERIAL_TIMEOUT_S}s -> {status} (after retry)")
                wall_w.writerow(["uno", circuit, n, theoretical_bytes, ram_bytes, ram_pct,
                                  status, ts, retry_used])
                wall_f.flush()
                wall_found = True

            if wall_found:
                break

    raw_f.close()
    wall_f.close()
    print(f"\nraw -> {raw_path}\nmemory wall -> {wall_path}")


if __name__ == "__main__":
    main()
