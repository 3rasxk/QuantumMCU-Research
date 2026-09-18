#!/usr/bin/env python3
# esp32_sweep.py — Phase 2 Edge Benchmark: ไล่ค่า n ขึ้นทีละ 1 จนบอร์ด ESP32 ล้มเหลว
#
# เหมือน esp8266_sweep.py (malloc runtime, build สำเร็จเสมอ, ล้มเหลวจริงตอนรัน) แต่
# raw CSV ของ ESP32 มีคอลัมน์เพิ่ม "largest_block" (heap_caps_get_largest_free_block)
# เพราะ heap ของ ESP32 แบ่งเป็นหลาย region — free heap รวมพอ ไม่ได้แปลว่าจองก้อนใหญ่
# ต่อเนื่องได้เสมอไป (fragmentation)
#
# runtime_hang_or_reset (ไม่ใช่ malloc_failed, ไม่ใช่ build/upload fail — ทั้งคู่
# deterministic) ถือเป็นความล้มเหลวชั่วคราวได้ จึง retry ที่ n เดิมอีก 1 ครั้งก่อนสรุปว่า
# เป็น Memory Wall จริง
# *** ข้อแตกต่างจากวิธีวัดของ dataset n=30: รอบนั้นไม่มี retry เลย รอบ n=100 นี้ผ่อนเกณฑ์
# ให้ทนความล้มเหลวชั่วคราวได้ 1 ครั้ง — Memory Wall ของสอง dataset จึง "ไม่ได้เปรียบเทียบ
# กันตรง ๆ ได้ทันที" ต้องดูคอลัมน์ retry_count ใน esp32_memory_wall.csv ประกอบ (run_log.md) ***
#
# การใช้งาน:
#   .venv/bin/python pc/phase2_sweep/esp32_sweep.py --port /dev/cu.usbserialXXXX \
#       --circuits h_all bell_ghz qft grover qpe steane_encode --n-start 2 --n-max 18
#
# steane_encode คงที่ที่ n=7 เสมอ (pc/shared/circuit_ids.n_values_for_sweep จัดการให้
# อัตโนมัติ) — ถ้า n=7 ไม่อยู่ใน [n-start, n-max] ที่ขอ จะข้ามวงจรนี้ไปเฉย ๆ

import argparse
import csv
import glob
import os
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

FW_DIR = REPO_ROOT / "firmware" / "esp32"
RESULTS_DIR = REPO_ROOT / "data" / "raw" / "phase2"
PIO = os.environ.get("PIO_PATH") or shutil.which("pio")

BAUD = 115200
SERIAL_TIMEOUT_S = 70  # scaled for REPS=100 (was 20 for REPS=30)


def find_esp_port(hint: str) -> str:
    """สแกน port ใหม่ทุกครั้ง กันกรณี re-enumerate เหมือนที่เจอกับ Uno"""
    candidates = sorted(glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.wchusbserial*") + glob.glob("/dev/cu.SLAB_USBtoUART*"))
    if not candidates:
        return hint
    if hint in candidates:
        return hint
    return candidates[0]


def build_and_upload(circuit: str, n: int, port_hint: str):
    port = find_esp_port(port_hint)
    env = os.environ.copy()
    env.update({"N_QUBITS": str(n), "CIRCUIT_ID": str(CIRCUIT_IDS[circuit])})

    try:
        proc = subprocess.run(
            [PIO, "run", "-e", "esp32dev", "-t", "upload", "--upload-port", port],
            cwd=str(FW_DIR), env=env, capture_output=True, text=True, timeout=150,
        )
        stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        stderr = "pio run timed out after 150s (stuck esptool / stuck port)"
        returncode = -1

    ok = returncode == 0
    return ok, stdout[-4000:] + stderr[-2000:], port


class HardTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise HardTimeout()


def read_serial_trials(port: str):
    """เปิด serial อ่านจนเจอ DONE / MALLOC_FAILED / timeout
    ใช้ hard deadline ผ่าน signal.alarm เหมือน uno_sweep.py (บทเรียนจากที่เจอค้างจริง)"""
    rows = []
    malloc_failed = False
    reset_count = 0
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(SERIAL_TIMEOUT_S + 10)
    try:
        with serial.Serial(port, BAUD, timeout=2) as ser:
            ser.dtr = False
            ser.rts = False
            deadline = time.time() + SERIAL_TIMEOUT_S
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
                if "esp32," in line:
                    # ตัดขยะจาก ROM bootloader (ets Jul.../rst:.../configsip:...) ที่อาจติดมา
                    idx = line.index("esp32,")
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
    ap.add_argument("--n-max", type=int, default=18)
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RESULTS_DIR / "esp32_raw.csv"
    wall_path = RESULTS_DIR / "esp32_memory_wall.csv"

    raw_is_new = not raw_path.exists()
    wall_is_new = not wall_path.exists()
    raw_f = open(raw_path, "a", newline="")
    wall_f = open(wall_path, "a", newline="")
    raw_w = csv.writer(raw_f)
    wall_w = csv.writer(wall_f)
    if raw_is_new:
        raw_w.writerow(["board", "circuit", "n", "rep", "exec_time_us", "free_heap_before", "free_heap_after", "largest_block"])
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

            # attempt 0 = ครั้งแรก, attempt 1 = retry เดียว — เฉพาะ runtime_hang_or_reset
            # เท่านั้นที่ retry ได้ (อาจเป็นสายหลุด/USB glitch ชั่วคราว) build/upload fail
            # และ malloc_failed ไม่ retry เพราะเป็น deterministic
            for attempt in range(2):
                print(f"n={n:2d}  theoretical={theoretical_bytes:6d} bytes  ", end="", flush=True)
                if attempt == 1:
                    print("(retry) ", end="", flush=True)

                ok, log, used_port = build_and_upload(circuit, n, args.port)
                ts = datetime.now(timezone.utc).isoformat()
                args.port = used_port

                if not ok:
                    print("UPLOAD/BUILD FAIL")
                    wall_w.writerow(["esp32", circuit, n, theoretical_bytes, None, None,
                                      "build_or_upload_fail", ts, retry_used])
                    wall_f.flush()
                    print(log[-800:])
                    wall_found = True
                    break

                time.sleep(1.5)  # เผื่อบอร์ด reset ตัวเองหลัง upload แล้วเริ่ม setup() ใหม่
                done, rows, malloc_failed, note = read_serial_trials(find_esp_port(args.port))

                if malloc_failed:
                    print(f"MALLOC_FAILED -> Memory Wall found (n={n})")
                    wall_w.writerow(["esp32", circuit, n, theoretical_bytes, None, None,
                                      "malloc_failed", ts, retry_used])
                    wall_f.flush()
                    wall_found = True
                    break

                if done:
                    for line in rows:
                        raw_w.writerow(line.split(","))
                    raw_f.flush()
                    wall_w.writerow(["esp32", circuit, n, theoretical_bytes, None, None,
                                      "ok", ts, retry_used])
                    wall_f.flush()
                    suffix = f"  (succeeded after {retry_used} retry)" if retry_used else ""
                    print(f"OK  trials_captured={len(rows)}{suffix}")
                    break

                status = f"runtime_hang_or_reset({note})"
                if attempt == 0:
                    retry_used = 1
                    print(f"NO 'DONE' within {SERIAL_TIMEOUT_S}s -> {status}  "
                          "-- transient failure, retrying once at same n before declaring "
                          "Memory Wall (deviation from n=30 methodology, see run_log.md)")
                    continue

                print(f"NO 'DONE' within {SERIAL_TIMEOUT_S}s -> {status} (after retry)")
                wall_w.writerow(["esp32", circuit, n, theoretical_bytes, None, None,
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
