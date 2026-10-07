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
#       --circuits h_all bell_ghz qft grover --n-start 2 --n-max 7 \
#       --bauds 115200 250000
#
# qpe/steane_encode ถูกถอดออกจากแผนการทดลองแล้ว (2026-10-03) — สคริปต์จะปฏิเสธทันที
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
PIO = os.environ.get("PIO_PATH") or shutil.which("pio")

sys.path.insert(0, str(REPO_ROOT / "analysis"))
sys.path.insert(0, str(REPO_ROOT / "pc"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol import FRAME_REQ_START, parse_request, pack_response  # noqa: E402
from phase1_compare import build_qiskit_circuit  # noqa: E402
from shared.circuit_ids import CIRCUIT_IDS, CIRCUIT_NAMES, n_values_for_sweep, EXPERIMENT_CIRCUITS, reject_removed_circuits  # noqa: E402
from shared import timing_model as tm  # noqa: E402
from shared import resume as rs  # noqa: E402
from shared import telemetry as tel  # noqa: E402
from shared import paths as sp  # noqa: E402
from counter import hooks as refhooks  # noqa: E402

RESUME_KEY_SPEC = [("circuit", str), ("n", int), ("baud_rate", int)]
BOOT_WAIT_S = 1.5  # เผื่อบอร์ด reset ตัวเองหลัง upload แล้วเริ่ม setup() ใหม่

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


def build_and_upload(board: str, circuit: str, n: int, baud: int, port_hint: str,
                      build_timeout_s=None, reps=None, response_timeout_ms=None):
    """แยก compile กับ upload เป็นสอง subprocess (เดิมเป็นคำสั่งเดียว `-t upload`) เพื่อ
    จับเวลาแยกกันได้จริง — ดู uno_sweep.py::build_and_upload สำหรับเหตุผลเต็ม

    คืน dict (ไม่ใช่ tuple)"""
    if build_timeout_s is None:
        build_timeout_s = tm.BUILD_TIMEOUT_S
    cfg = BOARDS[board]
    port = find_port(board, port_hint)
    env = os.environ.copy()
    env.update({"N_QUBITS": str(n), "CIRCUIT_ID": str(CIRCUIT_IDS[circuit]), "BAUD_RATE": str(baud)})
    # per-point firmware settings (defaults in main_offload.cpp: 100 reps, 5 s): the reps that fit the 2 h cap, and a
    # response timeout longer than the PC's simulation time
    extra = []
    if reps is not None:
        extra.append(f"-D REPS={int(reps)}")
    if response_timeout_ms is not None:
        extra.append(f"-D RESPONSE_TIMEOUT_MS={int(response_timeout_ms)}UL")
    if extra:
        env["PLATFORMIO_BUILD_FLAGS"] = " ".join(filter(None, [env.get("PLATFORMIO_BUILD_FLAGS", ""), *extra]))

    timed_out = False
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [PIO, "run", "-e", cfg["env"]],
            cwd=str(cfg["fw_dir"]), env=env, capture_output=True, text=True, timeout=build_timeout_s,
        )
        c_stdout, c_stderr, c_rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        c_stdout = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        c_stderr = f"pio run (compile) timed out after {build_timeout_s}s"
        c_rc = -1
        timed_out = True
    compile_s = time.perf_counter() - t0

    if c_rc != 0:
        return {"ok": False, "log": c_stdout[-3000:] + c_stderr[-1500:], "port": port,
                "compile_s": compile_s, "upload_s": 0.0, "timed_out": timed_out}

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [PIO, "run", "-e", cfg["env"], "-t", "upload", "--upload-port", port],
            cwd=str(cfg["fw_dir"]), env=env, capture_output=True, text=True, timeout=build_timeout_s,
        )
        u_stdout, u_stderr, u_rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        u_stdout = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode("utf-8", "replace")
        u_stderr = f"pio run (upload) timed out after {build_timeout_s}s"
        u_rc = -1
        timed_out = True
    upload_s = time.perf_counter() - t0

    ok = u_rc == 0
    return {"ok": ok, "log": u_stdout[-3000:] + u_stderr[-1500:], "port": port,
            "compile_s": compile_s, "upload_s": upload_s, "timed_out": timed_out}


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
    """สตรีมไบต์เดียว รับมือทั้งเฟรมไบนารีและบรรทัด CSV ข้อความ (ดู docstring บนไฟล์)

    เพิ่ม pc_sim_durations (list ของเวลาที่ simulate_and_sample ใช้ต่อคำขอ) และ
    bytes_transferred สำหรับ telemetry — จับเวลาด้วย perf_counter "รอบ" การเรียก
    simulate_and_sample() เท่านั้น ไม่แตะภายในฟังก์ชันนั้นเลย และไม่กระทบ e2e_latency_us
    ที่ MCU วัดเอง (ตัวเลขนั้นมาจาก micros() ฝั่ง MCU ล้วน ๆ อยู่แล้ว การจับเวลาฝั่ง PC
    นี้แค่ "อ่านเพิ่ม" ไม่ได้เปลี่ยนจังหวะการตอบสนองต่อเฟรมแต่อย่างใด)"""
    old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(session_timeout_s)
    text_buf = bytearray()
    csv_rows = []
    got_header = False
    done = False
    frames_served = 0
    frames_dropped_bad_crc = 0
    last_sim_error = ""
    pc_sim_durations = []
    bytes_transferred = 0
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
                bytes_transferred += 4  # เฟรม request เสมอ 4 byte ไม่ว่าจะ parse ผ่านหรือไม่
                frame = bytes([byte]) + rest
                parsed = parse_request(frame)
                if parsed is None:
                    frames_dropped_bad_crc += 1
                    continue  # CRC ผิด: ไม่ตอบ ปล่อยให้ MCU timeout รอบนั้น (ข้อมูลจริง)
                n_qubits, circuit_id = parsed
                sim_t0 = time.perf_counter()
                try:
                    outcome = simulate_and_sample(sim, n_qubits, circuit_id)
                except Exception as e:
                    # บันทึกสาเหตุจริง (เช่น MemoryError จาก Aer ตอน n สูงมาก) เพื่อรายงาน
                    # ตามที่วัดได้จริง ไม่ใช่แค่ "ล้มเหลว" เฉย ๆ
                    last_sim_error = f"{type(e).__name__}: {e}"
                    continue
                pc_sim_durations.append(time.perf_counter() - sim_t0)
                ser.write(pack_response(outcome))
                bytes_transferred += 6  # เฟรม response เสมอ 6 byte
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
        return done, csv_rows, frames_served, frames_dropped_bad_crc, last_sim_error, pc_sim_durations, bytes_transferred
    except HardTimeout:
        return (False, csv_rows, frames_served, frames_dropped_bad_crc,
                last_sim_error or "hard_timeout", pc_sim_durations, bytes_transferred)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True, choices=list(BOARDS.keys()))
    ap.add_argument("--port", required=True)
    ap.add_argument("--circuits", nargs="+",
                     default=list(EXPERIMENT_CIRCUITS))
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
    ap.add_argument("--build-timeout", dest="build_timeout_s", type=int, default=tm.BUILD_TIMEOUT_S,
                     help=f"วินาทีสูงสุดต่อการเรียก pio run หนึ่งครั้ง (compile และ upload แยกกัน) "
                          f"ค่าเริ่มต้น {tm.BUILD_TIMEOUT_S}s — timeout บันทึกเป็น build_timeout "
                          f"ไม่ใช่ build_or_upload_fail (ดู docs/preflight_report.md H2)")
    ap.add_argument("--fresh", "--no-resume", dest="fresh", action="store_true",
                     help="ไม่ resume จากผลลัพธ์เดิม — ย้ายไฟล์ raw/session_log เดิมไปเป็น "
                          "*.pre-fresh-<timestamp>.csv (ไม่ลบทิ้ง) แล้วเริ่มนับใหม่หมด")
    refhooks.add_args(ap)   # --ref {none,counter}, --counter-port (pc/counter/hooks.py)
    args = ap.parse_args()
    reject_removed_circuits(args.circuits)
    n_max = args.n_max if args.n_max is not None else N_SAFETY_CAP

    from qiskit_aer import AerSimulator
    sim = AerSimulator(method="statevector")

    ref_active = refhooks.ref_active(args)
    try:
        for circuit in args.circuits:
            print(f"\n=== circuit={circuit} ===")
            _run_circuit(args, circuit, n_max, sim, ref_active)
    finally:
        refhooks.shutdown()   # disarm the counter and close its port (no-op without --ref counter)


def _run_circuit(args, circuit, n_max, sim, ref_active=False):
    """One algorithm's directory/files/telemetry session — see pc/shared/paths.py
    and uno_sweep.py's module docstring for the per-board-per-algorithm layout
    this replaced (2026-09-20, run_log.md). Every baud in --bauds is still swept
    for this one circuit (baud is a data dimension within one algorithm's
    directory, not a separate algorithm) -- only the "skip every later circuit
    once a baud is found unstable" cross-circuit shortcut was dropped, since
    circuits are now fully independent calls; each circuit now probes every
    configured baud on its own. Disclosed in run_log.md, not a correctness
    change -- Phase 3 has no collected data yet either way."""
    n_values = n_values_for_sweep(circuit, args.n_start, n_max)
    if not n_values:
        print(f"skip: {circuit} is fixed-n and its n is outside [{args.n_start}, {n_max}]")
        return

    raw_directory = sp.raw_dir(args.board, circuit, phase=3, ref=ref_active)
    raw_directory.mkdir(parents=True, exist_ok=True)
    raw_path = sp.raw_csv_path(args.board, circuit, phase=3, ref=ref_active)
    meta_path = sp.session_log_csv_path(args.board, circuit, phase=3, ref=ref_active)
    points_csv = sp.points_csv_path(args.board, circuit, phase=3, ref=ref_active)
    sessions_csv = sp.sessions_csv_path(args.board, circuit, phase=3, ref=ref_active)
    env_directory = sp.env_dir(args.board, circuit, phase=3, ref=ref_active)

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

    ref = refhooks.from_args(args, args.board, circuit, phase=3)   # SweepRef; disabled (no-op) unless --ref counter
    raw_is_new = not raw_path.exists() or raw_path.stat().st_size == 0  # empty file (killed before first flush) still needs its header
    meta_is_new = not meta_path.exists() or meta_path.stat().st_size == 0  # empty file (killed before first flush) still needs its header
    raw_f = open(raw_path, "a", newline="")
    meta_f = open(meta_path, "a", newline="")
    if raw_is_new:
        raw_f.write("board,circuit,n,baud_rate,rep,e2e_latency_us,crc_error,timed_out\n")
    if meta_is_new:
        meta_f.write("board,circuit,n,baud_rate,status,frames_served,frames_dropped_bad_crc,rows_captured,last_sim_error,timestamp_utc,session_timeout_budget_s,expected_session_s,pc_sim_s_per_request\n")

    try:
        # preflight: ต้นทุนของ Phase 3 อยู่ฝั่ง PC ทั้งหมด จึงไม่ขึ้นกับบอร์ด — แผนเดียวกัน
        # ใช้ได้ทุกบอร์ด แสดงก่อนเริ่มเพื่อให้เห็นว่าจุดไหนเก็บครบ 100 reps ไม่ไหว
        planned = [(circuit, n) for n in n_values]
        infeasible = tm.print_budget_plan(args.board, planned, phase=3)
        if args.force_infeasible:
            print("--force-infeasible: จะพยายามรันจุดที่เกินเพดานด้วย\n")
            infeasible = set()

        # resume summary ต้องรวม baud เข้าไปใน key ด้วย (ต่างจาก preflight budget plan ด้านบน
        # ที่ไม่สนใจ baud เพราะต้นทุน PC ไม่ขึ้นกับ baud) เนื่องจากจุดเดียวกันอาจสำเร็จที่ baud
        # หนึ่งแต่ยังไม่เคยลองที่อีก baud หนึ่ง
        planned_with_baud = [(circuit, n, b) for b in args.bauds for n in n_values]
        remaining_preview = [p for p in planned_with_baud if p not in completed]
        real_remaining = [(c, n) for c, n, b in remaining_preview if (c, n) not in infeasible]
        est_s = sum(tm.phase3_rep_time_s(c, n) * tm.phase3_point_reps(c, n) for c, n in real_remaining)
        n_inf_remaining = len(remaining_preview) - len(real_remaining)
        remaining_human = tm.human_duration(est_s)
        if n_inf_remaining:
            remaining_human += f" (+{n_inf_remaining} infeasible point(s), skipped near-instantly)"
        rs.print_resume_summary(args.board, planned_with_baud, completed, remaining_human)

        # telemetry: session wrapper + environment metadata ครั้งเดียวตอน circuit นี้เริ่ม —
        # ดู pc/shared/telemetry.py และ uno_sweep.py สำหรับ schema เต็ม/เหตุผล
        resumed_from_previous = bool(completed)
        last_end = (tel.last_session_end_utc(args.board, 3, sessions_csv=sessions_csv)
                    if resumed_from_previous else None)
        session = tel.SessionRecorder(phase=3, board=args.board, circuits=[circuit],
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
                session.session_id, args.board, args.port, args.bauds[0], None,
                BOARDS[args.board]["fw_dir"] / "src_offload",
                env_dir=env_directory,
                pio_project_dir=BOARDS[args.board]["fw_dir"],
                pio_env=BOARDS[args.board]["env"], ref=ref_active)
            session.env_json_path = str(env_path)
            refhooks.write_sidecar(env_directory, session.session_id, args, args.board)   # no-op without --ref counter

            _sweep_body(args, circuit, n_values, completed, infeasible, raw_f, meta_f,
                        sim, session, points_csv, ref=ref)
    finally:
        raw_f.close()
        meta_f.close()

    print(f"\nraw -> {raw_path}\nsession log -> {meta_path}")
    print(f"telemetry -> {sessions_csv}, {points_csv}")


def _sweep_body(args, circuit, n_values, completed, infeasible, raw_f, meta_f, sim, session, points_csv, ref=None):
    if ref is None:
        ref = refhooks.SweepRef()   # disabled: every ref.* call is a no-op
    for baud in args.bauds:
        print(f"\n########## baud={baud} ##########")
        n_succeeded = 0
        for n in n_values:
            if (circuit, n, baud) in completed:
                print(f"n={n:2d}  SKIP (resume): already "
                      f"{completed[(circuit, n, baud)].get('status', '?')}")
                skip_ts = datetime.now(timezone.utc).isoformat()
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 3, "board": args.board,
                    "circuit": circuit, "n": n, "baud": baud, "attempt_index": 0,
                    "start_utc": skip_ts, "end_utc": skip_ts, "wall_s": 0,
                    "retry_count": 0, "timeout_hit": False, "failure_type": "none",
                    "status": "skipped_resume",
                }, points_csv)
                session.note_point(status="skipped_resume")
                continue

            point_reps = tm.phase3_point_reps(circuit, n)   # 100, or fewer under the 2 h per-point cap; 0 = skip
            if point_reps == 0 and args.force_infeasible:
                point_reps = 1   # --force-infeasible: try one request of a point the cap would skip
            budget_s = tm.phase3_session_budget_s(circuit, n, point_reps) if point_reps else tm.PHASE3_FLOOR_S
            per_req = tm.phase3_rep_time_s(circuit, n)
            expected_s = per_req * (point_reps or tm.REPS)
            response_timeout_ms = tm.phase3_response_timeout_ms(circuit, n)
            ts = datetime.now(timezone.utc).isoformat()

            if (circuit, n) in infeasible:
                # ไม่ใช่ปัญหาของลิงก์ serial หรือของบอร์ด — เป็นต้นทุนการจำลองฝั่ง PC
                # ล้วน ๆ (ไม่ cache โดยตั้งใจ) บันทึกค่าประมาณไว้ให้อ่านออกว่าทำไมถึงข้าม
                print(f"n={n:2d}  SKIP: one request needs {tm.human_duration(per_req)} "
                      f"(PC-side sim, uncached) > the {tm.human_duration(tm.POINT_TIME_CAP_S)} per-point cap; "
                      f"continuing with the next n")
                meta_f.write(f"{args.board},{circuit},{n},{baud},skipped_sim_cost_infeasible,"
                             f"0,0,0,,{ts},{budget_s},{expected_s:.1f},{per_req:.3f}\n")
                meta_f.flush()
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 3, "board": args.board,
                    "circuit": circuit, "n": n, "baud": baud, "attempt_index": 0,
                    "start_utc": ts, "end_utc": ts, "wall_s": 0,
                    "retry_count": 0, "timeout_hit": False, "failure_type": "none",
                    "status": "skipped_sim_cost_infeasible",
                }, points_csv)
                session.note_point(status="skipped_sim_cost_infeasible")
                continue

            if ref.stop_requested():   # previous points are fully written; stop BEFORE starting a new one
                print("[ref] counter lost for 2 consecutive points -- stopping the run (all latency data so far is intact)")
                return
            cap_note = f"reps={point_reps}/{tm.REPS} (2 h cap)  " if point_reps < tm.REPS else ""
            print(f"n={n:2d}  budget={budget_s}s ({per_req:.2f}s/request)  {cap_note}", end="", flush=True)
            # counter: this point's rep count, and a max pulse width above the firmware's response timeout
            ref.arm(n, reps=point_reps, max_width_s=int(response_timeout_ms / 1000) + 60)   # no-op without --ref counter

            attempt_start = datetime.now(timezone.utc).isoformat()
            result = build_and_upload(args.board, circuit, n, baud, args.port, args.build_timeout_s,
                                      reps=point_reps, response_timeout_ms=response_timeout_ms)
            args.port = result["port"]
            ts = datetime.now(timezone.utc).isoformat()
            reflash_s = result["compile_s"] + result["upload_s"]

            if not result["ok"]:
                ref.target_failed(n)   # board never ran; reference record only
                # timeout ของ toolchain ไม่ใช่ความล้มเหลวของบอร์ด และไม่ใช่กำแพง
                # (Phase 3 ไม่มี known-wall inference อยู่แล้ว แต่ยังต้องแยกให้ชัดในข้อมูล)
                build_status = rs.classify_build_failure(
                    result["log"], None, result.get("timed_out", False))
                is_timeout = build_status == "build_timeout"
                print("BUILD TIMEOUT -> toolchain/host problem, NOT a board failure"
                      if is_timeout else "UPLOAD/BUILD FAIL")
                meta_f.write(f"{args.board},{circuit},{n},{baud},{build_status},0,0,0,,{ts},{budget_s},{expected_s:.1f},{per_req:.3f}\n")
                meta_f.flush()
                print(result["log"][-600:])
                tel.write_point_row({
                    "session_id": session.session_id, "phase": 3, "board": args.board,
                    "circuit": circuit, "n": n, "baud": baud, "attempt_index": 0,
                    "start_utc": attempt_start, "end_utc": ts, "wall_s": round(reflash_s, 3),
                    "build_compile_s": round(result["compile_s"], 3),
                    "upload_s": round(result["upload_s"], 3),
                    "retry_count": 0, "timeout_hit": is_timeout,
                    "failure_type": "build_timeout" if is_timeout else "build",
                    "failure_message": result["log"][-300:],
                    "status": "failed",
                }, points_csv)
                session.note_point(reflash_s=reflash_s, status="failed")
                break

            time.sleep(BOOT_WAIT_S)
            port = find_port(args.board, args.port)
            exec_t0 = time.perf_counter()
            with serial.Serial(port, baud, timeout=1) as ser:
                ser.dtr = False
                ser.rts = False
                time.sleep(0.3)
                ser.reset_input_buffer()
                (done, rows, served, dropped, sim_error,
                 pc_sim_durations, bytes_transferred) = run_offload_session(ser, sim, budget_s)
            device_exec_s = time.perf_counter() - exec_t0
            ref.finish(n, rows, done)   # disarm, store pulses, join e2e_latency_us with the counter; never changes `done`/`rows`
            attempt_end = datetime.now(timezone.utc).isoformat()
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

            # per-rep round-trip latency: ใช้ตัวเลขที่ MCU วัดเอง (e2e_latency_us,
            # คอลัมน์ที่ 6 ของแต่ละบรรทัด CSV) ไม่วัดซ้ำฝั่ง PC — micros() ของ MCU
            # ครอบทั้งรอบ write+read จริง ๆ ที่อุปกรณ์เห็น เชื่อถือได้กว่าประมาณจาก PC
            latencies_us = []
            for line in rows:
                parts = line.split(",")
                if len(parts) >= 6:
                    try:
                        latencies_us.append(float(parts[5]))
                    except ValueError:
                        pass
            avg_latency_s = (sum(latencies_us) / len(latencies_us) / 1e6) if latencies_us else ""
            pc_sim_total = sum(pc_sim_durations)
            pc_sim_median = (sorted(pc_sim_durations)[len(pc_sim_durations) // 2]
                             if pc_sim_durations else "")
            # raw CSV: ...,e2e_latency_us,crc_error,timed_out — crc_error คือ index -2
            # เสมอ (ก่อนหน้า timed_out ตัวสุดท้าย) รวม dropped (CRC ผิดที่ฝั่ง PC เห็น
            # ก่อนตอบด้วยซ้ำ, ไม่มีในแถว rows เลยเพราะ MCU ก็ timeout ไปเงียบ ๆ)
            crc_error_count = dropped + sum(1 for line in rows if line.split(",")[-2] == "1")
            tel.write_point_row({
                "session_id": session.session_id, "phase": 3, "board": args.board,
                "circuit": circuit, "n": n, "baud": baud, "attempt_index": 0,
                "start_utc": attempt_start, "end_utc": attempt_end,
                "wall_s": round(reflash_s + BOOT_WAIT_S + device_exec_s, 3),
                "build_compile_s": round(result["compile_s"], 3),
                "upload_s": round(result["upload_s"], 3),
                "boot_wait_s": BOOT_WAIT_S, "device_exec_s": round(device_exec_s, 3),
                "pc_sim_s_total": round(pc_sim_total, 3),
                "pc_sim_s_median": round(pc_sim_median, 4) if pc_sim_median != "" else "",
                "serial_transfer_s_total": round(max(device_exec_s - pc_sim_total, 0.0), 3),
                "avg_round_trip_latency_s": round(avg_latency_s, 6) if avg_latency_s != "" else "",
                "crc_error_count": crc_error_count, "bytes_transferred": bytes_transferred,
                "retry_count": 0, "timeout_hit": not done,
                "failure_type": "none" if status == "ok" else "serial",
                # points.csv status ใช้ enum ของมันเอง (telemetry.STATUS_TYPES: ok/failed
                # เท่านั้นสำหรับผลจริง ไม่มี "session_incomplete") — session_log.csv
                # (meta_f ด้านบน) ยังเก็บ "session_incomplete" แบบเดิมเป็นบันทึกฝั่ง resume
                # ที่ละเอียดกว่า สองไฟล์นี้ตอบคำถามคนละคำถาม ไม่ต้องใช้ค่าเดียวกัน
                "failure_message": (f"time_capped reps={point_reps}/{tm.REPS} cap_s={tm.POINT_TIME_CAP_S}"
                                    if point_reps < tm.REPS and status == "ok" and not sim_error_safe else sim_error_safe),
                "status": "ok" if status == "ok" else "failed",
            }, points_csv)
            session.note_point(device_s=device_exec_s, reflash_s=reflash_s,
                                status="ok" if status == "ok" else "failed")

            error_rows = sum(1 for r in rows if r.split(",")[-1] == "1" or r.split(",")[-2] == "1")
            error_rate = (error_rows / len(rows)) if rows else 1.0
            err_note = f"  sim_error={sim_error_safe}" if sim_error_safe else ""
            ref_note = f"  {ref.summary_text()}" if ref.enabled else ""
            print(f"status={status}  rows={len(rows)}  crc_dropped={dropped}  error_rate={error_rate:.0%}{err_note}{ref_note}")

            failed = (not done) or error_rate > 0.5
            if failed:
                if n_succeeded == 0:
                    # ล้มเหลวตั้งแต่ n แรกที่ทดสอบของ baud นี้ = ปัญหาการเชื่อมต่อ/สาย
                    # ไม่ใช่ขีดจำกัดการคำนวณ -> ข้าม baud นี้ (แค่ของ circuit นี้ — ดู
                    # _run_circuit docstring: ไม่ข้าม circuit อื่นอีกต่อไป)
                    print(f"baud={baud} ไม่เสถียรตั้งแต่ n={n} (จุดแรกของวงจรนี้) — ข้าม baud นี้")
                else:
                    # เคยสำเร็จมาก่อนหน้านี้แล้วเพิ่งมาล้มที่ n สูง = เจอขีดจำกัดจริง
                    # ฝั่ง PC (เวลาจำลอง/หน่วยความจำ Qiskit Aer) ไม่ใช่ปัญหา baud
                    # -> หยุดแค่ baud นี้ ไป baud ถัดไปตามปกติ
                    print(f"พบขีดจำกัดจริงของวงจร {circuit} ที่ n={n} (baud={baud} ยังถือว่าเสถียร)")
                break
            n_succeeded += 1


if __name__ == "__main__":
    main()
