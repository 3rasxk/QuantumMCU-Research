#!/usr/bin/env python3
# sweep.py — Phase 3: Offload Benchmark
# รวม PC-side serial server (ตอบเฟรม request ด้วยผล Qiskit Aer ที่จำลองสดใหม่ทุกครั้ง
# ไม่ cache — ตามที่ตัดสินใจไว้ เพื่อให้ e2e_latency_us สะท้อนต้นทุนจริงของการ offload)
# กับตัว orchestrator (build+upload เฟิร์มแวร์ offload แล้วรัน session เก็บผล) ไว้ใน
# ไฟล์เดียว เพราะทั้งสองส่วนต้องทำงานพร้อมกันบน serial port เดียวกัน
#
# กลไกสำคัญ: ระหว่าง session เดียวกัน สตรีมไบต์จากพอร์ตมีทั้งเฟรมไบนารี (เริ่มด้วย
# 0xAA) และบรรทัดข้อความ CSV สรุปท้าย session (มาหลังแลกเปลี่ยนครบ 100 รอบ) โค้ดนี้
# แยกสองแบบด้วย byte แรกที่อ่านได้ — ถ้าเป็น 0xAA ถือเป็นจุดเริ่มเฟรม ถ้าไม่ใช่ถือเป็น
# ตัวอักษรของบรรทัดข้อความ สะสมจนเจอ \n
#
# การใช้งาน:
#   .venv/bin/python pc/phase3_offload/sweep.py --board uno --port /dev/cu.usbmodemXXXX \
#       --circuits h_all bell_ghz qft grover qpe steane_encode --n-start 2 --n-max 7 \
#       --bauds 115200 250000
#
# steane_encode คงที่ที่ n=7 เสมอ (pc/shared/circuit_ids.n_values_for_sweep จัดการให้
# อัตโนมัติ) — ถ้า n=7 ไม่อยู่ใน [n-start, n-max] ที่ขอ จะข้ามวงจรนี้ไปเฉย ๆ
#
# *** ต้นทุนการจำลองฝั่ง PC (สำคัญมากสำหรับ grover) ***
# simulate_and_sample() จำลองวงจรใหม่หมดทุกคำขอ ไม่ cache — เป็นการตัดสินใจเชิงระเบียบวิธี
# ที่ตั้งใจ (ดู docstring ของฟังก์ชัน) เพราะบริการ offload จริงก็ต้องแบกต้นทุนนี้เหมือนกัน
# ผลคือต้นทุนต่อคำขอแปรผันตามจำนวนเกท ไม่ใช่ตามความเร็วบอร์ด ตัวเลขที่วัดจริงในรอบ
# Phase 1 ของเครื่องนี้:
#   qft n=12    ~0.05 วินาที/คำขอ -> 100 reps = ~5 วินาทีต่อจุด      (สบาย)
#   grover n=8  ~2.2  วินาที/คำขอ -> 100 reps = ~3.7 นาทีต่อจุด      (ไหว)
#   grover n=10 ~40   วินาที/คำขอ -> 100 reps = ~1.1 ชั่วโมงต่อจุด   (ไหวแต่หนัก)
#   grover n=12 ~725  วินาที/คำขอ -> 100 reps = ~20 ชั่วโมงต่อจุด    (ไม่ไหว -> ข้าม)
# grover n=12 จึงถูกข้ามด้วย status=skipped_sim_cost_infeasible แทนที่จะเปิด cache
# ให้ตัวเลขดูดีขึ้น — การ cache จะเปลี่ยนความหมายของสิ่งที่ Phase 3 วัด (กลายเป็นวัดแค่
# ต้นทุนการสื่อสาร ไม่รวมต้นทุนการคำนวณ) และข้อสรุปเรื่อง Crossover Point ทั้งหมด
# ขึ้นอยู่กับความซื่อตรงของเส้นทางนี้ ถ้าจะเปิด cache ต้องเป็นการตัดสินใจที่บันทึกไว้
# ชัดเจนว่าเปลี่ยนนิยามของการวัด ไม่ใช่การปรับแต่งเงียบ ๆ เพื่อให้รันทัน
#
# ข้อสังเกตที่ตัวเลขชุดนี้เปิดเผย: grover n=10 บน ESP8266 รัน local ไม่ไหวเลย (ประเมิน
# ~1.3 วันต่อจุด) แต่ offload ได้ใน ~1.1 ชั่วโมง — เป็น crossover ที่ชัดที่สุดในชุดข้อมูล
#
# *** resume (ค่าเริ่มต้น): มีแถวใน <board>_session_log.csv = จุด (circuit, n, baud) นั้น
# "เสร็จสิ้น" แล้วไม่ว่าผลจะเป็นอะไร (ok, session_incomplete, build_or_upload_fail,
# skipped_sim_cost_infeasible) — resume ข้ามได้เลย ไม่ทำ known-wall inference แบบ Phase 2
# ที่นี่โดยตั้งใจ: ความล้มเหลวที่ n หนึ่งของ Phase 3 มักมาจาก baud ไม่เสถียร (ปัญหาลิงก์
# ที่แก้ได้ด้วยการเปลี่ยนสาย/พอร์ตแล้วลองที่ n เดิมใหม่) ไม่ใช่ขีดจำกัดการคำนวณที่
# deterministic เหมือน build_or_upload_fail ของ Phase 2 จึงไม่ปลอดภัยที่จะสรุปว่า n สูง
# กว่าจะล้มเหลวซ้ำเสมอ ลำดับการเขียน raw/meta ถูกสลับ (raw ก่อน meta) เพื่อให้ orphan
# raw rows (กรณีโปรเซสตายกลางคัน) ตรวจจับได้แบบเดียวกับ Phase 2 — ถ้าเขียน meta ก่อนแล้ว
# ตายก่อนเขียน raw จะได้ meta ที่อ้างว่า "เสร็จ" ทั้งที่ไม่มีข้อมูลรองรับ ใช้ --fresh เพื่อ
# ย้ายผลลัพธ์เดิมออกไป (ไม่ลบทิ้ง) แล้วเริ่มนับใหม่หมด — ดู pc/shared/resume.py ***

import argparse
import glob
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import serial

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = REPO_ROOT / "data" / "raw" / "phase3"
PIO = os.environ.get("PIO_PATH") or shutil.which("pio")

sys.path.insert(0, str(REPO_ROOT / "analysis"))
sys.path.insert(0, str(REPO_ROOT / "pc"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import FRAME_REQ_START, parse_request, pack_response  # noqa: E402
from phase1_compare import build_qiskit_circuit  # noqa: E402
from shared.circuit_ids import CIRCUIT_IDS, CIRCUIT_NAMES, n_values_for_sweep  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared import resume as rs  # noqa: E402

RESUME_KEY_SPEC = [("circuit", str), ("n", int), ("baud_rate", int)]

BOARDS = {
    "uno": {
        "fw_dir": REPO_ROOT / "firmware" / "uno",
        "env": "uno_offload",
        "port_globs": ["/dev/cu.usbmodem*"],
    },
    "esp8266": {
        "fw_dir": REPO_ROOT / "firmware" / "esp8266",
        "env": "nodemcuv2_offload",
        "port_globs": ["/dev/cu.usbserial*", "/dev/cu.wchusbserial*", "/dev/cu.SLAB_USBtoUART*"],
    },
    "esp32": {
        "fw_dir": REPO_ROOT / "firmware" / "esp32",
        "env": "esp32dev_offload",
        "port_globs": ["/dev/cu.usbserial*", "/dev/cu.wchusbserial*", "/dev/cu.SLAB_USBtoUART*"],
    },
}

# timeout ต่อ session ไม่ใช่ค่าคงที่แล้ว — คำนวณต่อ (circuit, n) จาก
# pc/shared/timing_model.phase3_session_budget_s() เพราะคอขวดของ Phase 3 คือ
# "เวลาที่ PC จำลองด้วย Qiskit Aer ใหม่ทุกคำขอ" ซึ่งแปรผันตามจำนวนเกทของวงจร
# ไม่ใช่ความเร็วบอร์ด: grover n=10 ใช้ ~40 วินาที/คำขอ (วัดจริงใน Phase 1) แปลว่า
# 100 reps = ~1.1 ชั่วโมงต่อจุด ในขณะที่ qft n=12 ใช้ ~5 วินาทีต่อ 100 reps ทั้งจุด
N_SAFETY_CAP = 22  # เพดานสูงสุดที่ยอมให้ทดสอบ (2^22 amplitude * 16 bytes = 64MB, ปลอดภัยต่อ RAM เครื่อง PC)


class HardTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise HardTimeout()


def find_port(board: str, hint: str) -> str:
    globs = BOARDS[board]["port_globs"]
    candidates = sorted(sum((glob.glob(g) for g in globs), []))
    if not candidates:
        return hint
    if hint in candidates:
        return hint
    return candidates[0]


def build_and_upload(board: str, circuit: str, n: int, baud: int, port_hint: str):
    cfg = BOARDS[board]
    port = find_port(board, port_hint)
    env = os.environ.copy()
    env.update({"N_QUBITS": str(n), "CIRCUIT_ID": str(CIRCUIT_IDS[circuit]), "BAUD_RATE": str(baud)})

    try:
        proc = subprocess.run(
            [PIO, "run", "-e", cfg["env"], "-t", "upload", "--upload-port", port],
            cwd=str(cfg["fw_dir"]), env=env, capture_output=True, text=True, timeout=150,
        )
        stdout, stderr, returncode = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        stderr = "pio run timed out after 150s"
        returncode = -1

    ok = returncode == 0
    return ok, stdout[-3000:] + stderr[-1500:], port


def read_exact(ser, n, deadline):
    buf = bytearray()
    while len(buf) < n and time.time() < deadline:
        chunk = ser.read(n - len(buf))
        if chunk:
            buf += chunk
    return bytes(buf)


def simulate_and_sample(sim, n_qubits: int, circuit_id: int) -> int:
    """จำลองวงจรใหม่ทั้งหมดทุกครั้ง (ไม่ cache) แล้วสุ่มตัวอย่างผลวัด 1 shot จาก
    การแจกแจงความน่าจะเป็นที่ได้ — เทียบเท่าการวัดจริง 1 ครั้ง"""
    circuit_name = CIRCUIT_NAMES[circuit_id]
    qc = build_qiskit_circuit(circuit_name, n_qubits)
    qc.save_statevector()
    result = sim.run(qc).result()
    sv = np.asarray(result.get_statevector(qc).data)
    probs = np.abs(sv) ** 2
    probs = probs / probs.sum()
    outcome = int(np.random.choice(len(probs), p=probs))
    return outcome


def run_offload_session(ser, sim, session_timeout_s):
    """สตรีมไบต์เดียว รับมือทั้งเฟรมไบนารีและบรรทัด CSV ข้อความ (ดู docstring บนไฟล์)"""
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(session_timeout_s)
    text_buf = bytearray()
    csv_rows = []
    got_header = False
    done = False
    frames_served = 0
    frames_dropped_bad_crc = 0
    last_sim_error = ""
    try:
        deadline = time.time() + session_timeout_s
        while time.time() < deadline and not done:
            b = ser.read(1)
            if not b:
                continue
            byte = b[0]
            if byte == FRAME_REQ_START:
                text_buf.clear()
                rest = read_exact(ser, 3, time.time() + 2.0)
                if len(rest) < 3:
                    continue
                frame = bytes([byte]) + rest
                parsed = parse_request(frame)
                if parsed is None:
                    frames_dropped_bad_crc += 1
                    continue  # CRC ผิด: ไม่ตอบ ปล่อยให้ MCU timeout รอบนั้น (ข้อมูลจริง)
                n_qubits, circuit_id = parsed
                try:
                    outcome = simulate_and_sample(sim, n_qubits, circuit_id)
                except Exception as e:
                    # บันทึกสาเหตุจริง (เช่น MemoryError จาก Aer ตอน n สูงมาก) เพื่อรายงาน
                    # ตามที่วัดได้จริง ไม่ใช่แค่ "ล้มเหลว" เฉย ๆ
                    last_sim_error = f"{type(e).__name__}: {e}"
                    continue
                ser.write(pack_response(outcome))
                frames_served += 1
            else:
                if byte == 0x0A:
                    line = text_buf.decode("utf-8", errors="replace").strip()
                    text_buf.clear()
                    if line:
                        if line.startswith("board,circuit"):
                            got_header = True
                        elif line == "DONE":
                            done = True
                        elif got_header:
                            csv_rows.append(line)
                elif byte == 0x0D:
                    pass
                else:
                    text_buf.append(byte)
        return done, csv_rows, frames_served, frames_dropped_bad_crc, last_sim_error
    except HardTimeout:
        return False, csv_rows, frames_served, frames_dropped_bad_crc, last_sim_error or "hard_timeout"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=list(BOARDS.keys()))
    ap.add_argument("--port", required=True)
    ap.add_argument("--circuits", nargs="+",
                     default=["h_all", "bell_ghz", "qft", "grover", "qpe", "steane_encode"])
    ap.add_argument("--n-start", type=int, default=2)
    ap.add_argument("--n-max", type=int, default=None,
                     help="ถ้าไม่ระบุ จะไล่ n ขึ้นเรื่อย ๆ จนกว่าจะพบ error จริง "
                          "(offload ไม่ผูกกับ Memory Wall ฝั่ง MCU เพราะ MCU ไม่ได้จองหน่วยความจำเอง "
                          "ขีดจำกัดจริงคือฝั่ง PC — เวลาจำลอง/หน่วยความจำของ Qiskit Aer) "
                          f"เพดานความปลอดภัยสูงสุดคือ n={N_SAFETY_CAP} กัน PC หน่วยความจำพัง")
    ap.add_argument("--bauds", nargs="+", type=int, default=[115200])
    ap.add_argument("--force-infeasible", action="store_true",
                     help="พยายามรันจุดที่ timing_model บอกว่าเก็บครบ 100 reps ไม่ไหว "
                          "(ปกติจะข้ามพร้อมบันทึกเหตุผล)")
    ap.add_argument("--fresh", "--no-resume", dest="fresh", action="store_true",
                     help="ไม่ resume จากผลลัพธ์เดิม — ย้ายไฟล์ raw/session_log เดิมไปเป็น "
                          "*.pre-fresh-<timestamp>.csv (ไม่ลบทิ้ง) แล้วเริ่มนับใหม่หมด")
    args = ap.parse_args()
    n_max = args.n_max if args.n_max is not None else N_SAFETY_CAP

    from qiskit_aer import AerSimulator
    sim = AerSimulator(method="statevector")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RESULTS_DIR / f"{args.board}_raw.csv"
    meta_path = RESULTS_DIR / f"{args.board}_session_log.csv"

    # resume (ค่าเริ่มต้น): มีแถวใน session_log.csv = จุดนั้น (circuit, n, baud) "เสร็จสิ้น"
    # แล้วไม่ว่าผลจะเป็นอะไร (ok, session_incomplete, build_or_upload_fail,
    # skipped_sim_cost_infeasible) — ข้ามได้เลย ไม่ต้องแตะฮาร์ดแวร์/PC ซ้ำ ไม่ทำ known-wall
    # inference แบบ Phase 2 ที่นี่ (ต่างจาก uno/esp32/esp8266_sweep.py โดยตั้งใจ): ความ
    # "ล้มเหลว" ของ Phase 3 ที่ n หนึ่งอาจเป็นเพราะ baud ไม่เสถียร (ปัญหาลิงก์ ไม่ใช่ขีด
    # จำกัดการคำนวณ) ซึ่งอาจหายไปได้ถ้าเปลี่ยนสาย/พอร์ตแล้วรันใหม่ที่ n เดิม — จึงไม่ปลอดภัย
    # ที่จะสรุปเหมารวมว่า n สูงกว่าจะล้มเหลวเหมือนกันเสมอ (ต่างจาก build_or_upload_fail ของ
    # Phase 2 ที่ deterministic จริง ๆ) แถวกำพร้าใน raw CSV (จุดที่โปรเซสตายระหว่างเขียนผล
    # ไม่มี terminal record คู่กัน) จะถูกกวาดทิ้งก่อนแล้วรันจุดนั้นใหม่ทั้งหมด
    if args.fresh:
        moved = rs.archive_existing(meta_path, raw_path)
        for src, dest in moved:
            print(f"--fresh: archived {src.name} -> {dest.name}")
        completed = {}
    else:
        completed = rs.load_terminal_points(meta_path, RESUME_KEY_SPEC)
        kept, removed, removed_keys = rs.purge_orphan_rows(raw_path, RESUME_KEY_SPEC, set(completed.keys()))
        if removed:
            print(f"resume: purged {removed} orphan raw row(s) from interrupted point(s) "
                  f"{sorted(removed_keys)} — these will be redone from scratch, not topped up")

    raw_is_new = not raw_path.exists()
    meta_is_new = not meta_path.exists()
    raw_f = open(raw_path, "a", newline="")
    meta_f = open(meta_path, "a", newline="")
    if raw_is_new:
        raw_f.write("board,circuit,n,baud_rate,rep,e2e_latency_us,crc_error,timed_out\n")
    if meta_is_new:
        meta_f.write("board,circuit,n,baud_rate,status,frames_served,frames_dropped_bad_crc,rows_captured,last_sim_error,timestamp_utc,session_timeout_budget_s,expected_session_s,pc_sim_s_per_request\n")

    # preflight: ต้นทุนของ Phase 3 อยู่ฝั่ง PC ทั้งหมด จึงไม่ขึ้นกับบอร์ด — แผนเดียวกัน
    # ใช้ได้ทุกบอร์ด แสดงก่อนเริ่มเพื่อให้เห็นว่าจุดไหนเก็บครบ 100 reps ไม่ไหว
    planned = [(c, n) for c in args.circuits
               for n in n_values_for_sweep(c, args.n_start, n_max)]
    infeasible = tm.print_budget_plan(args.board, planned, phase=3)
    if args.force_infeasible:
        print("--force-infeasible: จะพยายามรันจุดที่เกินเพดานด้วย\n")
        infeasible = set()

    # resume summary ต้องรวม baud เข้าไปใน key ด้วย (ต่างจาก preflight budget plan ด้านบน
    # ที่ไม่สนใจ baud เพราะต้นทุน PC ไม่ขึ้นกับ baud) เนื่องจากจุดเดียวกันอาจสำเร็จที่ baud
    # หนึ่งแต่ยังไม่เคยลองที่อีก baud หนึ่ง
    planned_with_baud = [(c, n, b) for b in args.bauds for c in args.circuits
                         for n in n_values_for_sweep(c, args.n_start, n_max)]
    remaining_preview = [p for p in planned_with_baud if p not in completed]
    real_remaining = [(c, n) for c, n, b in remaining_preview if (c, n) not in infeasible]
    est_s = sum(tm.pc_sim_time_s(c, n) * tm.REPS for c, n in real_remaining)
    n_inf_remaining = len(remaining_preview) - len(real_remaining)
    remaining_human = tm.human_duration(est_s)
    if n_inf_remaining:
        remaining_human += f" (+{n_inf_remaining} infeasible point(s), skipped near-instantly)"
    rs.print_resume_summary(args.board, planned_with_baud, completed, remaining_human)

    for baud in args.bauds:
        print(f"\n########## baud={baud} ##########")
        baud_unstable = False
        for circuit in args.circuits:
            if baud_unstable:
                print(f"ข้าม circuit={circuit} เพราะ baud={baud} ไม่เสถียรจากรอบก่อนหน้าแล้ว")
                continue
            print(f"\n=== circuit={circuit} ===")
            n_succeeded = 0
            n_values = n_values_for_sweep(circuit, args.n_start, n_max)
            if not n_values:
                print(f"skip: {circuit} is fixed-n and its n is outside [{args.n_start}, {n_max}]")
                continue
            for n in n_values:
                if (circuit, n, baud) in completed:
                    print(f"n={n:2d}  SKIP (resume): already "
                          f"{completed[(circuit, n, baud)].get('status', '?')}")
                    continue

                budget_s = tm.phase3_session_budget_s(circuit, n)
                per_req = tm.pc_sim_time_s(circuit, n)
                expected_s = per_req * tm.REPS
                ts = datetime.now(timezone.utc).isoformat()

                if (circuit, n) in infeasible:
                    # ไม่ใช่ปัญหาของลิงก์ serial หรือของบอร์ด — เป็นต้นทุนการจำลองฝั่ง PC
                    # ล้วน ๆ (ไม่ cache โดยตั้งใจ) บันทึกค่าประมาณไว้ให้อ่านออกว่าทำไมถึงข้าม
                    print(f"n={n:2d}  SKIP: PC-side sim needs {tm.human_duration(expected_s)} "
                          f"for {tm.REPS} reps ({per_req:.1f}s/request, uncached) "
                          f"> ceiling {tm.PHASE3_CEILING_S}s")
                    meta_f.write(f"{args.board},{circuit},{n},{baud},skipped_sim_cost_infeasible,"
                                 f"0,0,0,,{ts},{budget_s},{expected_s:.1f},{per_req:.3f}\n")
                    meta_f.flush()
                    continue

                print(f"n={n:2d}  budget={budget_s}s ({per_req:.2f}s/request)  ", end="", flush=True)

                ok, log, used_port = build_and_upload(args.board, circuit, n, baud, args.port)
                args.port = used_port
                ts = datetime.now(timezone.utc).isoformat()

                if not ok:
                    print("UPLOAD/BUILD FAIL")
                    meta_f.write(f"{args.board},{circuit},{n},{baud},build_or_upload_fail,0,0,0,,{ts},{budget_s},{expected_s:.1f},{per_req:.3f}\n")
                    meta_f.flush()
                    print(log[-600:])
                    break

                time.sleep(1.5)
                port = find_port(args.board, args.port)
                with serial.Serial(port, baud, timeout=1) as ser:
                    ser.dtr = False
                    ser.rts = False
                    time.sleep(0.3)
                    ser.reset_input_buffer()
                    done, rows, served, dropped, sim_error = run_offload_session(ser, sim, budget_s)
                sim_error_safe = sim_error.replace(",", ";").replace("\n", " ")

                status = "ok" if (done and len(rows) > 0) else "session_incomplete"

                # เขียน raw ก่อน meta เสมอ (สลับจากลำดับเดิม) — ให้ตรงกับ pattern เดียวกับ
                # Phase 2 (uno/esp32/esp8266_sweep.py): แถวใน meta คือ "บันทึกการตัดสิน
                # ชะตากรรม" ที่ resume ใช้ตัดสินว่าจุดนี้เสร็จแล้วหรือยัง ถ้าเขียน meta ก่อน
                # แล้วโปรเซสตายก่อนเขียน raw จะได้ meta ที่อ้างว่า "เสร็จ" ทั้งที่ไม่มีข้อมูล
                # raw รองรับเลย — resume จะข้ามจุดนั้นไปทั้งที่ไม่มีข้อมูลจริง ลำดับใหม่นี้
                # ทำให้กรณีแย่ที่สุดกลายเป็น "มี raw กำพร้าไม่มี meta คู่กัน" ซึ่ง
                # purge_orphan_rows (pc/shared/resume.py) จัดการได้ตรง ๆ อยู่แล้ว
                for line in rows:
                    raw_f.write(line + "\n")
                raw_f.flush()

                meta_f.write(f"{args.board},{circuit},{n},{baud},{status},{served},{dropped},{len(rows)},{sim_error_safe},{ts},{budget_s},{expected_s:.1f},{per_req:.3f}\n")
                meta_f.flush()

                error_rows = sum(1 for r in rows if r.split(",")[-1] == "1" or r.split(",")[-2] == "1")
                error_rate = (error_rows / len(rows)) if rows else 1.0
                err_note = f"  sim_error={sim_error_safe}" if sim_error_safe else ""
                print(f"status={status}  rows={len(rows)}  crc_dropped={dropped}  error_rate={error_rate:.0%}{err_note}")

                failed = (not done) or error_rate > 0.5
                if failed:
                    if n_succeeded == 0:
                        # ล้มเหลวตั้งแต่ n แรกที่ทดสอบของ baud นี้ = ปัญหาการเชื่อมต่อ/สาย
                        # ไม่ใช่ขีดจำกัดการคำนวณ -> ข้าม baud นี้ไปเลยทุกวงจร
                        print(f"baud={baud} ไม่เสถียรตั้งแต่ n={n} (จุดแรกของวงจรนี้) — ข้าม baud นี้ทั้งหมด")
                        baud_unstable = True
                    else:
                        # เคยสำเร็จมาก่อนหน้านี้แล้วเพิ่งมาล้มที่ n สูง = เจอขีดจำกัดจริง
                        # ฝั่ง PC (เวลาจำลอง/หน่วยความจำ Qiskit Aer) ไม่ใช่ปัญหา baud
                        # -> หยุดแค่วงจรนี้ ไปวงจรถัดไปตามปกติ
                        print(f"พบขีดจำกัดจริงของวงจร {circuit} ที่ n={n} (baud={baud} ยังถือว่าเสถียร)")
                    break
                n_succeeded += 1

    raw_f.close()
    meta_f.close()
    print(f"\nraw -> {raw_path}\nsession log -> {meta_path}")


if __name__ == "__main__":
    main()
