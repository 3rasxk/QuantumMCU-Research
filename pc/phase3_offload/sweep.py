#!/usr/bin/env python3
# sweep.py — Phase 3: Offload Benchmark
# รวม PC-side serial server (ตอบเฟรม request ด้วยผล Qiskit Aer ที่จำลองสดใหม่ทุกครั้ง
# ไม่ cache — ตามที่ตัดสินใจไว้ เพื่อให้ e2e_latency_us สะท้อนต้นทุนจริงของการ offload)
# กับตัว orchestrator (build+upload เฟิร์มแวร์ offload แล้วรัน session เก็บผล) ไว้ใน
# ไฟล์เดียว เพราะทั้งสองส่วนต้องทำงานพร้อมกันบน serial port เดียวกัน
#
# กลไกสำคัญ: ระหว่าง session เดียวกัน สตรีมไบต์จากพอร์ตมีทั้งเฟรมไบนารี (เริ่มด้วย
# 0xAA) และบรรทัดข้อความ CSV สรุปท้าย session (มาหลังแลกเปลี่ยนครบ 30 รอบ) โค้ดนี้
# แยกสองแบบด้วย byte แรกที่อ่านได้ — ถ้าเป็น 0xAA ถือเป็นจุดเริ่มเฟรม ถ้าไม่ใช่ถือเป็น
# ตัวอักษรของบรรทัดข้อความ สะสมจนเจอ \n
#
# การใช้งาน:
#   .venv/bin/python pc/phase3_offload/sweep.py --board uno --port /dev/cu.usbmodemXXXX \
#       --circuits h_all bell_ghz qft --n-start 2 --n-max 7 --bauds 115200 250000

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
from shared.circuit_ids import CIRCUIT_IDS, CIRCUIT_NAMES  # noqa: E402

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

SESSION_TIMEOUT_S = 90
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


def run_offload_session(ser, sim):
    """สตรีมไบต์เดียว รับมือทั้งเฟรมไบนารีและบรรทัด CSV ข้อความ (ดู docstring บนไฟล์)"""
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(SESSION_TIMEOUT_S)
    text_buf = bytearray()
    csv_rows = []
    got_header = False
    done = False
    frames_served = 0
    frames_dropped_bad_crc = 0
    last_sim_error = ""
    try:
        deadline = time.time() + SESSION_TIMEOUT_S
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
    ap.add_argument("--circuits", nargs="+", default=["h_all", "bell_ghz", "qft"])
    ap.add_argument("--n-start", type=int, default=2)
    ap.add_argument("--n-max", type=int, default=None,
                     help="ถ้าไม่ระบุ จะไล่ n ขึ้นเรื่อย ๆ จนกว่าจะพบ error จริง "
                          "(offload ไม่ผูกกับ Memory Wall ฝั่ง MCU เพราะ MCU ไม่ได้จองหน่วยความจำเอง "
                          "ขีดจำกัดจริงคือฝั่ง PC — เวลาจำลอง/หน่วยความจำของ Qiskit Aer) "
                          f"เพดานความปลอดภัยสูงสุดคือ n={N_SAFETY_CAP} กัน PC หน่วยความจำพัง")
    ap.add_argument("--bauds", nargs="+", type=int, default=[115200])
    args = ap.parse_args()
    n_max = args.n_max if args.n_max is not None else N_SAFETY_CAP

    from qiskit_aer import AerSimulator
    sim = AerSimulator(method="statevector")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RESULTS_DIR / f"{args.board}_raw.csv"
    meta_path = RESULTS_DIR / f"{args.board}_session_log.csv"

    raw_is_new = not raw_path.exists()
    meta_is_new = not meta_path.exists()
    raw_f = open(raw_path, "a", newline="")
    meta_f = open(meta_path, "a", newline="")
    if raw_is_new:
        raw_f.write("board,circuit,n,baud_rate,rep,e2e_latency_us,crc_error,timed_out\n")
    if meta_is_new:
        meta_f.write("board,circuit,n,baud_rate,status,frames_served,frames_dropped_bad_crc,rows_captured,last_sim_error,timestamp_utc\n")

    for baud in args.bauds:
        print(f"\n########## baud={baud} ##########")
        baud_unstable = False
        for circuit in args.circuits:
            if baud_unstable:
                print(f"ข้าม circuit={circuit} เพราะ baud={baud} ไม่เสถียรจากรอบก่อนหน้าแล้ว")
                continue
            print(f"\n=== circuit={circuit} ===")
            n_succeeded = 0
            for n in range(args.n_start, n_max + 1):
                print(f"n={n:2d}  ", end="", flush=True)

                ok, log, used_port = build_and_upload(args.board, circuit, n, baud, args.port)
                args.port = used_port
                ts = datetime.now(timezone.utc).isoformat()

                if not ok:
                    print("UPLOAD/BUILD FAIL")
                    meta_f.write(f"{args.board},{circuit},{n},{baud},build_or_upload_fail,0,0,0,,{ts}\n")
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
                    done, rows, served, dropped, sim_error = run_offload_session(ser, sim)
                sim_error_safe = sim_error.replace(",", ";").replace("\n", " ")

                status = "ok" if (done and len(rows) > 0) else "session_incomplete"
                meta_f.write(f"{args.board},{circuit},{n},{baud},{status},{served},{dropped},{len(rows)},{sim_error_safe},{ts}\n")
                meta_f.flush()

                for line in rows:
                    raw_f.write(line + "\n")
                raw_f.flush()

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
