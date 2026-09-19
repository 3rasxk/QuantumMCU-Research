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
#      ได้ทันที" ต้องดูคอลัมน์ retry_count ใน *_memory_wall.csv ประกอบ (ดู run_log.md) ***
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
# *** resume (ค่าเริ่มต้น): มีแถวใน uno_memory_wall.csv = จุดนั้น "เสร็จสิ้น" แล้วไม่ว่า
# ผลจะเป็นอะไร (ok, build_or_upload_fail, skipped_compute_infeasible, ...) — resume ข้าม
# ได้เลย ไม่ต้องแตะฮาร์ดแวร์ซ้ำ วงจรที่เคยเจอ "กำแพงจริง" แล้ว (build_or_upload_fail,
# runtime_hang_or_reset หลัง retry หมด) จะไม่ถูกลอง n ที่สูงกว่านั้นซ้ำอีก แม้ n เหล่านั้น
# ไม่เคยมี record ก็ตาม (ตรรกะเดียวกับที่ sweep เดิม break ออกจาก n-loop ทันทีที่เจอ
# กำแพง) แถวกำพร้าใน raw CSV (จุดที่โปรเซสตายระหว่างเขียนผล ไม่มี terminal record คู่กัน)
# จะถูกกวาดทิ้งก่อนแล้วรันจุดนั้นใหม่ทั้งหมด — ห้าม "เติม" ให้ครบ 100 trial เพราะ trial
# จาก 2 sessions ไม่ใช่ตัวอย่างสม่ำเสมอเดียวกัน (บอร์ด reset/reflash/อุณหภูมิเครื่องต่างกัน
# ระหว่าง session) ใช้ --fresh เพื่อย้ายผลลัพธ์เดิมออกไป (ไม่ลบทิ้ง) แล้วเริ่มนับใหม่หมด
# — ดู pc/shared/resume.py สำหรับเหตุผลเต็ม ***
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
from shared import timing_model as tm  # noqa: E402
from shared import resume as rs  # noqa: E402
from shared import telemetry as tel  # noqa: E402

RESUME_KEY_SPEC = [("circuit", str), ("n", int)]

FW_DIR = REPO_ROOT / "firmware" / "uno"
RESULTS_DIR = REPO_ROOT / "data" / "raw" / "phase2"
PIO = os.environ.get("PIO_PATH") or shutil.which("pio")

BAUD = 115200
F_CPU = 16_000_000  # ATmega328P — เมตาดาต้าเท่านั้น ไม่ได้ใช้คำนวณอะไร
BOOT_WAIT_S = 1.0  # เผื่อบอร์ด reset ตัวเองหลัง upload แล้วเริ่ม setup() ใหม่
# เวลารอสูงสุดต่อจุดข้อมูลไม่ใช่ค่าคงที่อีกต่อไป — คำนวณต่อ (circuit, n) จาก
# pc/shared/timing_model.timeout_budget_s() ดูเหตุผลใน header ของไฟล์นี้
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
    """แยก compile กับ upload เป็นสอง subprocess (เดิมเป็นคำสั่งเดียว `-t upload` ที่
    ทำทั้งสองอย่างในตัว) เพื่อจับเวลาแยกกันได้จริง (compile_s, upload_s) — PlatformIO
    ทำ dependency tracking เอง: เรียก `pio run` เฉย ๆ (compile) แล้วเรียก `-t upload`
    ต่อจะไม่ compile ซ้ำถ้าไม่มีอะไรเปลี่ยน จึงยังเป็นพฤติกรรมเดิมทุกประการ แค่วัดเป็น
    2 ช่วงแทนช่วงเดียว — เวลารวม (compile_s+upload_s) ควรใกล้เคียงของเดิมมาก

    คืน dict เดียว (ไม่ใช่ tuple) เพราะจำนวนค่าที่ต้องส่งกลับเพิ่มขึ้นมากจนใช้ positional
    tuple แล้วอ่านโค้ดเรียกยาก"""
    port = find_uno_port(port_hint)
    env = os.environ.copy()
    env.update({"N_QUBITS": str(n), "CIRCUIT_ID": str(CIRCUIT_IDS[circuit])})

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [PIO, "run", "-e", "uno"],
            cwd=str(FW_DIR), env=env, capture_output=True, text=True, timeout=120,
        )
        c_stdout, c_stderr, c_rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        c_stdout = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        c_stderr = "pio run (compile) timed out after 120s"
        c_rc = -1
    compile_s = time.perf_counter() - t0

    ram_pct, ram_bytes = None, None
    m = re.search(r"RAM:\s*\[.*?\]\s*([\d.]+)%\s*\(used (\d+) bytes", c_stdout)
    if m:
        ram_pct, ram_bytes = float(m.group(1)), int(m.group(2))
    compile_ok = c_rc == 0

    if not compile_ok:
        return {"ok": False, "ram_pct": ram_pct, "ram_bytes": ram_bytes,
                "log": c_stdout[-4000:] + c_stderr[-2000:], "port": port,
                "compile_s": compile_s, "upload_s": 0.0, "stage": "compile"}

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [PIO, "run", "-e", "uno", "-t", "upload", "--upload-port", port],
            cwd=str(FW_DIR), env=env, capture_output=True, text=True, timeout=120,
        )
        u_stdout, u_stderr, u_rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        u_stdout = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        u_stderr = "pio run (upload) timed out after 120s (stuck avrdude / stuck port)"
        u_rc = -1
    upload_s = time.perf_counter() - t0

    ok = u_rc == 0
    return {"ok": ok, "ram_pct": ram_pct, "ram_bytes": ram_bytes,
            "log": u_stdout[-4000:] + u_stderr[-2000:], "port": port,
            "compile_s": compile_s, "upload_s": upload_s, "stage": "upload"}


class HardTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise HardTimeout()


def read_serial_trials(port: str, circuit: str, n: int, timeout_s: int):
    """เปิด serial แล้วอ่านจนเจอ DONE หรือ timeout (=hang/reset)

    timeout_s มาจาก pc/shared/timing_model.timeout_budget_s() ต่อจุดข้อมูล ไม่ใช่ค่าคงที่
    ค่าเดียวทั้งสวีปอีกต่อไป — grover ที่ n สูงต้องการเวลามากกว่า h_all หลักพันเท่า

    ใช้ signal.alarm บังคับ deadline แข็ง (hard deadline) ครอบทั้งฟังก์ชัน
    เพราะพบจริงระหว่างทดลองว่า pyserial's readline() timeout เพียงอย่างเดียว
    "ไม่" รับประกันว่าจะ return ตรงเวลาเสมอเมื่อพอร์ต USB-CDC ของ Uno หลุด
    (เจอค้างเกิน 16 นาทีทั้งที่ตั้ง timeout=2 มาแล้วครั้งหนึ่ง) — ถ้าไม่มี
    hard deadline นี้ การสวีปทั้งชุดจะค้างได้โดยไม่มีทางฟื้นเอง
    """
    rows = []
    reset_count = 0
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(timeout_s + 10)
    try:
        with serial.Serial(port, BAUD, timeout=2) as ser:
            deadline = time.time() + timeout_s
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
    ap.add_argument("--force-infeasible", action="store_true",
                     help="พยายามรันจุดที่ timing_model บอกว่าเกินเพดานเวลาไปแล้วด้วย "
                          "(ปกติจะข้ามพร้อมบันทึกเหตุผล เพราะได้แค่ timeout เปล่า ๆ)")
    ap.add_argument("--fresh", "--no-resume", dest="fresh", action="store_true",
                     help="ไม่ resume จากผลลัพธ์เดิม — ย้ายไฟล์ raw/memory_wall เดิมไปเป็น "
                          "*.pre-fresh-<timestamp>.csv (ไม่ลบทิ้ง) แล้วเริ่มนับใหม่หมด")
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RESULTS_DIR / "uno_raw.csv"
    wall_path = RESULTS_DIR / "uno_memory_wall.csv"

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

    # preflight: โชว์ budget ของทุกจุดก่อนเริ่ม ให้คนกดรันเห็นว่าจุดไหนแพง/จุดไหนทำไม่ได้
    # ตั้งแต่ก่อนเริ่ม ไม่ใช่ไปเจอตอนชั่วโมงที่หก
    planned = [(c, n) for c in args.circuits
               for n in n_values_for_sweep(c, args.n_start, args.n_max)]
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
    remaining_human = tm.human_duration(est_s)
    if n_inf_remaining:
        remaining_human += f" (+{n_inf_remaining} infeasible point(s), skipped near-instantly)"
    rs.print_resume_summary("uno", planned, completed, remaining_human)
    wall_n_by_circuit = rs.known_wall_n(completed)

    # telemetry: session wrapper + environment metadata ครั้งเดียวตอนเริ่ม session
    # (ไม่ใช่ต่อจุด) — ดู pc/shared/telemetry.py สำหรับ schema เต็มและเหตุผลที่แยกจาก
    # *_raw.csv/*_memory_wall.csv เดิมโดยสิ้นเชิง (ไม่แตะ resume logic ที่ทดสอบแล้ว)
    resumed_from_previous = bool(completed)
    last_end = tel.last_session_end_utc("uno", 2) if resumed_from_previous else None
    session = tel.SessionRecorder(phase=2, board="uno", circuits=args.circuits,
                                   resumed_from_previous=resumed_from_previous,
                                   estimated_total_s=round(est_s, 1))
    with session:
        if last_end is not None:
            from datetime import datetime as _dt, timezone as _tz
            gap = (_dt.now(_tz.utc) - last_end).total_seconds()
            if gap > 0:
                session.note_interruption_gap(gap)
        env_path = tel.write_environment_metadata(
            session.session_id, "uno", args.port, BAUD, F_CPU, FW_DIR / "src")
        session.env_json_path = str(env_path)

        _sweep_body(args, completed, wall_n_by_circuit, infeasible,
                    raw_w, raw_f, wall_w, wall_f, session)

    raw_f.close()
    wall_f.close()
    print(f"\nraw -> {raw_path}\nmemory wall -> {wall_path}")
    print(f"telemetry -> {tel.SESSIONS_CSV}, {tel.POINTS_CSV}")


def _sweep_body(args, completed, wall_n_by_circuit, infeasible,
                 raw_w, raw_f, wall_w, wall_f, session):
    for circuit in args.circuits:
        print(f"\n=== circuit={circuit} ===")
        n_values = n_values_for_sweep(circuit, args.n_start, args.n_max)
        if not n_values:
            print(f"skip: {circuit} is fixed-n and its n is outside [{args.n_start}, {args.n_max}]")
            continue
        for n in n_values:
            skip_ts = datetime.now(timezone.utc).isoformat()
            if (circuit, n) in completed:
                print(f"n={n:2d}  SKIP (resume): already {completed[(circuit, n)].get('status', '?')}")
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 2, "board": "uno",
                    "circuit": circuit, "n": n, "attempt_index": 0,
                    "start_utc": skip_ts, "end_utc": skip_ts, "wall_s": 0,
                    "retry_count": 0, "timeout_hit": False, "failure_type": "none",
                    "status": "skipped_resume",
                })
                session.note_point(status="skipped_resume")
                continue
            if circuit in wall_n_by_circuit and n > wall_n_by_circuit[circuit]:
                print(f"n={n:2d}  SKIP (resume): {circuit} already hit its wall at "
                      f"n={wall_n_by_circuit[circuit]} in a previous session")
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 2, "board": "uno",
                    "circuit": circuit, "n": n, "attempt_index": 0,
                    "start_utc": skip_ts, "end_utc": skip_ts, "wall_s": 0,
                    "retry_count": 0, "timeout_hit": False, "failure_type": "none",
                    "status": "skipped_known_wall",
                })
                session.note_point(status="skipped_known_wall")
                continue

            theoretical_bytes = (1 << n) * 8
            budget_s = tm.timeout_budget_s("uno", circuit, n)
            expected_s = tm.expected_point_time_s("uno", circuit, n)
            may_retry = tm.retry_allowed(budget_s)
            retry_policy = "allowed" if may_retry else "skipped_high_budget"
            ts = datetime.now(timezone.utc).isoformat()

            if (circuit, n) in infeasible:
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
                })
                session.note_point(status="skipped_compute_infeasible")
                continue

            wall_found = False
            retry_used = 0
            point_device_s = 0.0
            point_reflash_s = 0.0

            # attempt 0 = ครั้งแรก, attempt 1 = retry เดียว — เฉพาะความล้มเหลวแบบ
            # runtime hang/reset/serial error เท่านั้นที่ retry ได้ (อาจเป็นสายหลุด/USB
            # glitch ชั่วคราว) build/upload fail ไม่ retry เพราะ deterministic
            #
            # ข้อยกเว้นใหม่ (REPS=100 + 6 วงจร): จุดที่ budget สูงกว่า RETRY_MAX_BUDGET_S
            # จะไม่ retry เพราะต้นทุน retry แปรผันตาม budget แต่ประโยชน์คงที่ — ที่ 70
            # วินาทีคุ้ม ที่ 4 ชั่วโมงไม่คุ้ม รันซ้ำเฉพาะจุดนั้นทีหลังถูกกว่ามาก (ไฟล์
            # ผลลัพธ์เป็น append-only) ดู timing_model.retry_allowed()
            max_attempts = 2 if may_retry else 1
            for attempt in range(max_attempts):
                print(f"n={n:2d}  theoretical={theoretical_bytes:6d} bytes  "
                      f"budget={budget_s}s (expected {tm.human_duration(expected_s)})  ",
                      end="", flush=True)
                if attempt == 1:
                    print("(retry) ", end="", flush=True)

                attempt_start = datetime.now(timezone.utc).isoformat()
                result = build_and_upload(circuit, n, args.port)
                ts = datetime.now(timezone.utc).isoformat()
                args.port = result["port"]  # จำ port ล่าสุดที่ใช้สำเร็จ ไว้เป็น hint รอบถัดไป
                reflash_s = result["compile_s"] + result["upload_s"]
                point_reflash_s += reflash_s

                if not result["ok"]:
                    print("UPLOAD/BUILD FAIL -> Memory Wall found (link/flash stage)")
                    wall_w.writerow(["uno", circuit, n, theoretical_bytes, result["ram_bytes"], result["ram_pct"],
                                      "build_or_upload_fail", ts, retry_used,
                                      budget_s, round(expected_s, 1), retry_policy])
                    wall_f.flush()
                    print(result["log"][-800:])
                    tel.write_point_row({
                        "session_id": session.session_id, "phase": 2, "board": "uno",
                        "circuit": circuit, "n": n, "attempt_index": attempt,
                        "start_utc": attempt_start, "end_utc": ts, "wall_s": round(reflash_s, 3),
                        "build_compile_s": round(result["compile_s"], 3),
                        "upload_s": round(result["upload_s"], 3),
                        "retry_count": retry_used, "timeout_hit": False,
                        "failure_type": "build", "failure_message": result["log"][-300:],
                        "status": "failed",
                    })
                    session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="failed")
                    wall_found = True
                    break

                time.sleep(BOOT_WAIT_S)  # เผื่อบอร์ด reset ตัวเองหลัง upload แล้วเริ่ม setup() ใหม่
                exec_t0 = time.perf_counter()
                done, rows, note = read_serial_trials(find_uno_port(args.port), circuit, n, budget_s)
                device_exec_s = time.perf_counter() - exec_t0
                point_device_s += device_exec_s
                attempt_end = datetime.now(timezone.utc).isoformat()

                if done:
                    for line in rows:
                        raw_w.writerow(line.split(",") + [budget_s])
                    raw_f.flush()
                    wall_w.writerow(["uno", circuit, n, theoretical_bytes, result["ram_bytes"], result["ram_pct"],
                                      "ok", ts, retry_used,
                                      budget_s, round(expected_s, 1), retry_policy])
                    wall_f.flush()
                    suffix = f"  (succeeded after {retry_used} retry)" if retry_used else ""
                    print(f"OK  compile_ram={result['ram_pct']}%  trials_captured={len(rows)}{suffix}")
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
                    })
                    session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="ok")
                    break

                status = f"runtime_hang_or_reset({note})"
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 2, "board": "uno",
                    "circuit": circuit, "n": n, "attempt_index": attempt,
                    "start_utc": attempt_start, "end_utc": attempt_end,
                    "wall_s": round(reflash_s + BOOT_WAIT_S + device_exec_s, 3),
                    "build_compile_s": round(result["compile_s"], 3),
                    "upload_s": round(result["upload_s"], 3),
                    "boot_wait_s": BOOT_WAIT_S, "device_exec_s": round(device_exec_s, 3),
                    "retry_count": retry_used, "timeout_hit": True,
                    "failure_type": "hang", "failure_message": note,
                    "status": "failed" if not (attempt == 0 and may_retry) else "retrying",
                })

                if attempt == 0 and may_retry:
                    retry_used = 1
                    print(f"NO 'DONE' within {budget_s}s -> {status}  "
                          "-- transient failure, retrying once at same n before declaring "
                          "Memory Wall (deviation from n=30 methodology, see run_log.md)")
                    continue

                tail = "(after retry)" if retry_used else f"(no retry: {retry_policy})"
                print(f"NO 'DONE' within {budget_s}s -> {status} {tail}")
                wall_w.writerow(["uno", circuit, n, theoretical_bytes, result["ram_bytes"], result["ram_pct"],
                                  status, ts, retry_used,
                                  budget_s, round(expected_s, 1), retry_policy])
                wall_f.flush()
                session.note_point(device_s=point_device_s, reflash_s=point_reflash_s, status="failed")
                wall_found = True

            if wall_found:
                break


if __name__ == "__main__":
    main()
