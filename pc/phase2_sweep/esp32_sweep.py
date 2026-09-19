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
from shared import timing_model as tm  # noqa: E402
from shared import resume as rs  # noqa: E402

RESUME_KEY_SPEC = [("circuit", str), ("n", int)]

FW_DIR = REPO_ROOT / "firmware" / "esp32"
RESULTS_DIR = REPO_ROOT / "data" / "raw" / "phase2"
PIO = os.environ.get("PIO_PATH") or shutil.which("pio")

BAUD = 115200
# เวลารอสูงสุดต่อจุดข้อมูลไม่ใช่ค่าคงที่อีกต่อไป — คำนวณต่อ (circuit, n) จาก
# pc/shared/timing_model.timeout_budget_s() ดูเหตุผลใน header ของไฟล์นี้


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
    ap.add_argument("--force-infeasible", action="store_true",
                     help="พยายามรันจุดที่ timing_model บอกว่าเกินเพดานเวลาไปแล้วด้วย "
                          "(ปกติจะข้ามพร้อมบันทึกเหตุผล เพราะได้แค่ timeout เปล่า ๆ)")
    ap.add_argument("--fresh", "--no-resume", dest="fresh", action="store_true",
                     help="ไม่ resume จากผลลัพธ์เดิม — ย้ายไฟล์ raw/memory_wall เดิมไปเป็น "
                          "*.pre-fresh-<timestamp>.csv (ไม่ลบทิ้ง) แล้วเริ่มนับใหม่หมด")
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RESULTS_DIR / "esp32_raw.csv"
    wall_path = RESULTS_DIR / "esp32_memory_wall.csv"

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
                        "free_heap_before", "free_heap_after", "largest_block",
                        "timeout_budget_s"])
    if wall_is_new:
        wall_w.writerow([
            "board", "circuit", "n", "theoretical_bytes", "compile_ram_used_bytes",
            "compile_ram_pct", "status", "timestamp_utc", "retry_count",
            "timeout_budget_s", "expected_point_s", "retry_policy",
        ])

    # preflight: โชว์ budget ของทุกจุดก่อนเริ่ม ให้คนกดรันเห็นว่าจุดไหนแพง/จุดไหนทำไม่ได้
    # ตั้งแต่ก่อนเริ่ม ไม่ใช่ไปเจอตอนชั่วโมงที่หก
    planned = [(c, n) for c in args.circuits
               for n in n_values_for_sweep(c, args.n_start, args.n_max)]
    infeasible = tm.print_budget_plan("esp32", planned, phase=2)
    if args.force_infeasible:
        print("--force-infeasible: จะพยายามรันจุดที่เกินเพดานด้วย\n")
        infeasible = set()

    remaining_preview = [p for p in planned if p not in completed]
    real_remaining = [p for p in remaining_preview if p not in infeasible]
    est_s = sum(tm.expected_point_time_s("esp32", c, n) for c, n in real_remaining)
    n_inf_remaining = len(remaining_preview) - len(real_remaining)
    remaining_human = tm.human_duration(est_s)
    if n_inf_remaining:
        remaining_human += f" (+{n_inf_remaining} infeasible point(s), skipped near-instantly)"
    rs.print_resume_summary("esp32", planned, completed, remaining_human)
    wall_n_by_circuit = rs.known_wall_n(completed)

    for circuit in args.circuits:
        print(f"\n=== circuit={circuit} ===")
        n_values = n_values_for_sweep(circuit, args.n_start, args.n_max)
        if not n_values:
            print(f"skip: {circuit} is fixed-n and its n is outside [{args.n_start}, {args.n_max}]")
            continue
        for n in n_values:
            if (circuit, n) in completed:
                print(f"n={n:2d}  SKIP (resume): already {completed[(circuit, n)].get('status', '?')}")
                continue
            if circuit in wall_n_by_circuit and n > wall_n_by_circuit[circuit]:
                print(f"n={n:2d}  SKIP (resume): {circuit} already hit its wall at "
                      f"n={wall_n_by_circuit[circuit]} in a previous session")
                continue

            theoretical_bytes = (1 << n) * 8
            budget_s = tm.timeout_budget_s("esp32", circuit, n)
            expected_s = tm.expected_point_time_s("esp32", circuit, n)
            may_retry = tm.retry_allowed(budget_s)
            retry_policy = "allowed" if may_retry else "skipped_high_budget"
            ts = datetime.now(timezone.utc).isoformat()

            if (circuit, n) in infeasible:
                # ไม่ใช่ Memory Wall และไม่ใช่ hang — เป็นขีดจำกัดเชิงเวลาคำนวณล้วน ๆ
                # บันทึกค่าประมาณไว้ด้วย เพื่อให้แถวนี้อ่านเป็น "ผลการทดลอง" ได้จริง
                print(f"n={n:2d}  SKIP compute-infeasible: expected "
                      f"{tm.human_duration(expected_s)} > ceiling {tm.CEILING_S}s")
                wall_w.writerow(["esp32", circuit, n, theoretical_bytes, None, None,
                                  "skipped_compute_infeasible", ts, 0,
                                  budget_s, round(expected_s, 1), "n/a"])
                wall_f.flush()
                continue

            wall_found = False
            retry_used = 0

            # attempt 0 = ครั้งแรก, attempt 1 = retry เดียว — เฉพาะ runtime_hang_or_reset
            # เท่านั้นที่ retry ได้ (อาจเป็นสายหลุด/USB glitch ชั่วคราว) build/upload fail
            # และ malloc_failed ไม่ retry เพราะเป็น deterministic
            # ข้อยกเว้นใหม่ (REPS=100 + 6 วงจร): จุดที่ budget สูงกว่า
            # RETRY_MAX_BUDGET_S จะไม่ retry เพราะต้นทุน retry แปรผันตาม budget
            # แต่ประโยชน์คงที่ — รันซ้ำเฉพาะจุดนั้นทีหลังถูกกว่ามาก (ไฟล์เป็น
            # append-only) ดู timing_model.retry_allowed()
            max_attempts = 2 if may_retry else 1
            for attempt in range(max_attempts):
                print(f"n={n:2d}  theoretical={theoretical_bytes:6d} bytes  "
                      f"budget={budget_s}s (expected {tm.human_duration(expected_s)})  ",
                      end="", flush=True)
                if attempt == 1:
                    print("(retry) ", end="", flush=True)

                ok, log, used_port = build_and_upload(circuit, n, args.port)
                ts = datetime.now(timezone.utc).isoformat()
                args.port = used_port

                if not ok:
                    print("UPLOAD/BUILD FAIL")
                    wall_w.writerow(["esp32", circuit, n, theoretical_bytes, None, None,
                                      "build_or_upload_fail", ts, retry_used,
                                      budget_s, round(expected_s, 1), retry_policy])
                    wall_f.flush()
                    print(log[-800:])
                    wall_found = True
                    break

                time.sleep(1.5)  # เผื่อบอร์ด reset ตัวเองหลัง upload แล้วเริ่ม setup() ใหม่
                done, rows, malloc_failed, note = read_serial_trials(find_esp_port(args.port), budget_s)

                if malloc_failed:
                    print(f"MALLOC_FAILED -> Memory Wall found (n={n})")
                    wall_w.writerow(["esp32", circuit, n, theoretical_bytes, None, None,
                                      "malloc_failed", ts, retry_used,
                                      budget_s, round(expected_s, 1), retry_policy])
                    wall_f.flush()
                    wall_found = True
                    break

                if done:
                    for line in rows:
                        raw_w.writerow(line.split(",") + [budget_s])
                    raw_f.flush()
                    wall_w.writerow(["esp32", circuit, n, theoretical_bytes, None, None,
                                      "ok", ts, retry_used,
                                      budget_s, round(expected_s, 1), retry_policy])
                    wall_f.flush()
                    suffix = f"  (succeeded after {retry_used} retry)" if retry_used else ""
                    print(f"OK  trials_captured={len(rows)}{suffix}")
                    break

                status = f"runtime_hang_or_reset({note})"
                if attempt == 0 and may_retry:
                    retry_used = 1
                    print(f"NO 'DONE' within {budget_s}s -> {status}  "
                          "-- transient failure, retrying once at same n before declaring "
                          "Memory Wall (deviation from n=30 methodology, see run_log.md)")
                    continue

                tail = "(after retry)" if retry_used else f"(no retry: {retry_policy})"
                print(f"NO 'DONE' within {budget_s}s -> {status} {tail}")
                wall_w.writerow(["esp32", circuit, n, theoretical_bytes, None, None,
                                  status, ts, retry_used,
                                      budget_s, round(expected_s, 1), retry_policy])
                wall_f.flush()
                wall_found = True

            if wall_found:
                break

    raw_f.close()
    wall_f.close()
    print(f"\nraw -> {raw_path}\nmemory wall -> {wall_path}")


if __name__ == "__main__":
    main()
