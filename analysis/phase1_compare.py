#!/usr/bin/env python3
# phase1_compare.py
# Phase 1: System Validation — เทียบผลลัพธ์ของ C++ simulator (ที่จะพอร์ตลง MCU
# ใน Phase 2) กับ Qiskit Aer เพื่อพิสูจน์ว่าตัวจำลองที่เขียนเองถูกต้อง
#
# ขั้นตอน:
#   1. เรียก C++ binary (pc/phase1_validate) รันแต่ละวงจร/จำนวนคิวบิต -> ได้ state vector
#   2. สร้างวงจรเดียวกันใน Qiskit ด้วยลำดับเกทเดียวกันทุกประการ -> รันผ่าน Qiskit Aer
#   3. คำนวณ Infidelity (1-F) และ Total Variation Distance (TVD)
#   4. บันทึกผลเป็น CSV ดิบ (ไม่สรุปทิ้งค่าเดิม) พร้อม log ตัวแปรควบคุมทั้งหมด
#
# เกณฑ์ผ่าน (pass criterion): Infidelity <= 1e-3 ทุกวงจร ทุกค่า n

import argparse
import csv
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
BINARY = REPO_ROOT / "pc" / "phase1_validate" / "phase1_validate"
RESULTS_DIR = REPO_ROOT / "data" / "raw" / "phase1"
CXXFLAGS = "-O2 -std=c++11 -Wall -Wextra"  # ต้องตรงกับ pc/phase1_validate/build.sh

sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared.circuit_ids import EXPERIMENT_CIRCUITS, reject_removed_circuits  # noqa: E402
from shared import experiment_plan as plan  # noqa: E402

# Scope (2026-10-03 restart): h_all, bell_ghz, qft, grover. n values are every n
# the experiment plan collects on ANY board/phase (pc/shared/experiment_plan.py),
# including n=1 for h_all/qft and the odd n never validated before.
# grover: n >= 2 (needs >= 1 control qubit for the oracle's multi-controlled-Z).
# Grover validation is capped by --grover-n-max (default 12): the oracle costs
# O(3^n) gates, so n=13/14 take hours-to-days in Qiskit and are reported as NOT RUN.
CIRCUITS = list(EXPERIMENT_CIRCUITS)
GROVER_N_MAX_DEFAULT = 12
CIRCUIT_N_VALUES = {c: plan.phase1_n_values(c) for c in CIRCUITS}
INFIDELITY_THRESHOLD = 1e-3


def run_cpp_simulator(circuit: str, n: int) -> np.ndarray:
    """เรียก C++ binary แล้ว parse CSV ออกมาเป็น numpy complex array (index ตรงกับ Qiskit)"""
    proc = subprocess.run(
        [str(BINARY), circuit, str(n)],
        capture_output=True, text=True, check=True,
    )
    lines = proc.stdout.strip().splitlines()
    assert lines[0] == f"n={n}", f"unexpected header: {lines[0]}"
    assert lines[1] == "index,re,im"
    n_states = 1 << n
    amps = np.zeros(n_states, dtype=complex)
    for line in lines[2:]:
        idx_s, re_s, im_s = line.split(",")
        amps[int(idx_s)] = float(re_s) + 1j * float(im_s)
    return amps


def _qft_inverse_qiskit(qc, num_qubits):
    """exact inverse ของลำดับ QFT ด้านล่าง — ต้องตรงกับ qft_apply_inverse ใน
    circuits.hpp เป๊ะ ๆ (กลับลำดับเกท, H ไม่กลับเฟส, CPhase กลับเฟส)"""
    for j in range(num_qubits - 1, -1, -1):
        for k in range(num_qubits - 1, j, -1):
            theta = np.pi / (2 ** (k - j))
            qc.cp(-theta, k, j)
        qc.h(j)


def _mc_phase_qiskit(qc, k, target, theta):
    """ตรงกับ mc_phase_apply ใน circuits.hpp ทุกประการ: controls = คิวบิต [0,k-1]
    ระวัง: qsim_cphase(q,q,theta) ของ C++ (control==target) แปลว่าเกทเฟสเดี่ยวธรรมดา
    บนคิวบิตนั้น — Qiskit ไม่มี "self-controlled-phase" จึงใช้ qc.p(theta,q) ที่เป็น
    เกทเดียวกันทางคณิตศาสตร์เป๊ะ (ไม่ใช่แค่ใกล้เคียง) แทนในกรณี k=0"""
    if k == 0:
        qc.p(theta, target)
        return
    if k == 1:
        qc.cp(theta, 0, target)
        return
    c_last = k - 1
    qc.cp(theta / 2, c_last, target)
    _mc_x_qiskit(qc, k - 1, c_last)
    qc.cp(-theta / 2, c_last, target)
    _mc_x_qiskit(qc, k - 1, c_last)
    _mc_phase_qiskit(qc, k - 1, target, theta / 2)


def _mc_x_qiskit(qc, k, target):
    """ตรงกับ mc_x_apply ใน circuits.hpp ทุกประการ"""
    if k == 1:
        qc.cx(0, target)
        return
    qc.h(target)
    _mc_phase_qiskit(qc, k, target, np.pi)
    qc.h(target)


def build_qiskit_circuit(circuit: str, n: int):
    """สร้างวงจรใน Qiskit ให้ลำดับเกทตรงกับ firmware/common/circuits.hpp ทุกประการ
    เพื่อให้การเทียบผลมีความหมาย (เทียบวงจรเดียวกัน ไม่ใช่แค่ผลลัพธ์ปลายทางบังเอิญตรงกัน)"""
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(n)
    if circuit == "h_all":
        for q in range(n):
            qc.h(q)
    elif circuit == "bell_ghz":
        qc.h(0)
        for q in range(1, n):
            qc.cx(q - 1, q)
    elif circuit == "qft":
        # ตรงกับ circuit_qft ใน circuits.hpp: ไม่มี SWAP ท้ายวงจร (do_swaps=False)
        # เพราะโจทย์จำกัดเกทที่ใช้ได้แค่ H, CNOT, CPhase
        for j in range(n):
            qc.h(j)
            for k in range(j + 1, n):
                theta = np.pi / (2 ** (k - j))
                qc.cp(theta, k, j)
    elif circuit == "grover":
        # ตรงกับ circuit_grover ใน circuits.hpp ทุกประการ รวม decomposition ของ
        # multi-controlled-Z (mc_phase_apply/mc_x_apply) และ X ผ่าน H-Z-H
        for q in range(n):
            qc.h(q)
        n_states = 1 << n
        iterations = int((np.pi / 4) * np.sqrt(n_states))
        iterations = max(iterations, 1)
        for _ in range(iterations):
            _mc_phase_qiskit(qc, n - 1, n - 1, np.pi)
            for q in range(n):
                qc.h(q)
            for q in range(n):
                qc.h(q)
                qc.p(np.pi, q)
                qc.h(q)
            _mc_phase_qiskit(qc, n - 1, n - 1, np.pi)
            for q in range(n):
                qc.h(q)
                qc.p(np.pi, q)
                qc.h(q)
            for q in range(n):
                qc.h(q)
    else:
        raise ValueError(f"unknown circuit {circuit}")
    return qc


def run_qiskit_aer(circuit: str, n: int):
    from qiskit_aer import AerSimulator

    qc = build_qiskit_circuit(circuit, n)
    depth = qc.depth()  # ความลึกวงจรจริง นับจาก Qiskit (ใช้พล็อตกราฟ Infidelity vs Circuit Depth)
    qc.save_statevector()
    sim = AerSimulator(method="statevector")
    result = sim.run(qc).result()
    sv = result.get_statevector(qc)
    return np.asarray(sv.data), depth


def infidelity(psi_a: np.ndarray, psi_b: np.ndarray) -> float:
    """1 - F, F = |<psi_a|psi_b>|^2  (phase-invariant โดยธรรมชาติของ inner product)"""
    inner = np.vdot(psi_a, psi_b)
    fidelity = float(np.abs(inner) ** 2)
    return 1.0 - fidelity


def total_variation_distance(psi_a: np.ndarray, psi_b: np.ndarray) -> float:
    p_a = np.abs(psi_a) ** 2
    p_b = np.abs(psi_b) ** 2
    return 0.5 * float(np.sum(np.abs(p_a - p_b)))


def grover_marked_probability(psi: np.ndarray) -> float:
    """P(|1...1>) หลัง Grover iterations — ต้องครองความน่าจะเป็นส่วนใหญ่ (Part 3):
    ถ้า infidelity ผ่านแต่ค่านี้ต่ำ แปลว่า iteration count หรือ oracle มีปัญหา
    ซึ่ง infidelity อย่างเดียวจับไม่ได้ (เทียบ Qiskit ตัวเดียวกันก็ผิดพลาดแบบเดียวกัน)"""
    return float(np.abs(psi[-1]) ** 2)


def log_metadata(meta_path=None):
    import qiskit
    import qiskit_aer

    gpp_version = subprocess.run(
        ["g++", "--version"], capture_output=True, text=True, check=True
    ).stdout.splitlines()[0]

    meta = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "gpp_version": gpp_version,
        "cxxflags": CXXFLAGS,
        "python_version": platform.python_version(),
        "qiskit_version": qiskit.__version__,
        "qiskit_aer_version": qiskit_aer.__version__,
        "numpy_version": np.__version__,
        "platform": platform.platform(),
    }
    if meta_path is None:
        meta_path = RESULTS_DIR / "phase1_metadata.csv"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "value"])
        for k, v in meta.items():
            w.writerow([k, v])
    print(f"metadata -> {meta_path}")
    return meta


def refuse_to_overwrite(paths, allow_overwrite=False):
    """เกราะกันข้อมูลดิบหาย: ทุกสคริปต์ที่เขียนลง data/raw/ ที่อื่นเป็น append-only
    ทั้งหมด (และ --fresh ของ sweep ก็ "ย้าย" ไฟล์เดิมไม่ได้ลบ) — ไฟล์นี้เคยเป็น
    ข้อยกเว้นเดียวที่เปิดด้วยโหมด "w" ทับผลเดิมทิ้งโดยไม่มีทางกู้ (ดู
    docs/preflight_report.md finding M5) ตอนนี้ต้องเลือกอย่างใดอย่างหนึ่งเสมอ:
    ย้ายไฟล์เดิมออกเอง, ใช้ --out-dir ชี้ที่ใหม่, หรือ --allow-overwrite ให้ชัดเจน

    คืน list ของไฟล์ที่มีอยู่แล้ว (ว่าง = เขียนได้เลย)"""
    existing = [p for p in paths if p.exists()]
    if existing and not allow_overwrite:
        names = "\n  ".join(str(p) for p in existing)
        print(f"error: refusing to overwrite existing Phase 1 results:\n  {names}\n"
              f"These are raw measurement files — overwriting them is unrecoverable.\n"
              f"Pick one:\n"
              f"  * --out-dir <dir>         write this run somewhere else (e.g. /tmp)\n"
              f"  * --timestamped-out       write <name>.<UTC timestamp>.csv next to the originals\n"
              f"  * --allow-overwrite       yes, really replace them\n"
              f"  * move/rename the files yourself first (nothing here deletes data)",
              file=sys.stderr)
        sys.exit(1)
    return existing


def main():
    ap = argparse.ArgumentParser(description="Phase 1: C++ simulator vs Qiskit Aer")
    ap.add_argument("--out-dir", type=Path, default=RESULTS_DIR,
                     help="ไดเรกทอรีปลายทางของผลลัพธ์ (ค่าเริ่มต้น data/raw/phase1)")
    ap.add_argument("--timestamped-out", action="store_true",
                     help="เขียนเป็น <ชื่อไฟล์>.<UTC timestamp>.csv แทนการทับไฟล์เดิม")
    ap.add_argument("--allow-overwrite", action="store_true",
                     help="ยอมให้ทับไฟล์ผลลัพธ์เดิม (ค่าเริ่มต้นคือปฏิเสธและออกด้วย exit 1)")
    ap.add_argument("--circuits", nargs="+", default=CIRCUITS)
    ap.add_argument("--grover-n-max", type=int, default=GROVER_N_MAX_DEFAULT)
    ap.add_argument("--only-n", type=int, nargs="+", default=None,
                    help="restrict to these n (resume a partial run into a new timestamped file)")
    args = ap.parse_args()
    reject_removed_circuits(args.circuits)
    circuits = args.circuits

    if not BINARY.exists():
        print(f"error: {BINARY} not found. run pc/phase1_validate/build.sh first", file=sys.stderr)
        sys.exit(1)

    results_dir = args.out_dir
    suffix = ""
    if args.timestamped_out:
        suffix = "." + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    csv_path = results_dir / f"infidelity_tvd{suffix}.csv"
    meta_path = results_dir / f"phase1_metadata{suffix}.csv"
    refuse_to_overwrite([csv_path, meta_path], args.allow_overwrite)

    log_metadata(meta_path)

    results_dir.mkdir(parents=True, exist_ok=True)

    # เขียนทีละแถวพร้อม flush ทันที (ไม่สะสมใน rows แล้วเขียนตอนจบ) — grover ที่ n สูง
    # ใช้เวลานานมาก (oracle ราคา O(3^n) เกท) ถ้ารันค้าง/ถูก interrupt กลางทาง ผลลัพธ์
    # ของ n ที่ทำเสร็จแล้วต้องไม่หายไปเปล่า ๆ
    fieldnames = ["circuit", "n", "depth", "infidelity", "tvd", "pass",
                  "grover_marked_prob", "flag_above_1e-3"]
    all_pass = True
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        f.flush()

        for circuit in circuits:
            for n in CIRCUIT_N_VALUES[circuit]:
                if args.only_n is not None and n not in args.only_n:
                    continue
                if circuit == "grover" and n > args.grover_n_max:
                    print(f"[NOT RUN] circuit=grover n={n}: above --grover-n-max "
                          f"{args.grover_n_max} (O(3^n) oracle, hours-to-days in Qiskit)",
                          flush=True)
                    continue
                t_start = time.monotonic()
                psi_cpp = run_cpp_simulator(circuit, n)
                psi_qiskit, depth = run_qiskit_aer(circuit, n)

                infid = infidelity(psi_cpp, psi_qiskit)
                tvd = total_variation_distance(psi_cpp, psi_qiskit)
                passed = infid <= INFIDELITY_THRESHOLD

                extra = ""
                marked_prob = ""
                if circuit == "grover":
                    marked_prob = grover_marked_probability(psi_cpp)
                    extra = f"  P(marked)={marked_prob:.4f}"

                all_pass = all_pass and passed
                w.writerow({
                    "circuit": circuit,
                    "n": n,
                    "depth": depth,
                    "infidelity": infid,
                    "tvd": tvd,
                    "pass": passed,
                    "grover_marked_prob": marked_prob,
                    "flag_above_1e-3": infid > INFIDELITY_THRESHOLD,
                })
                f.flush()
                elapsed = time.monotonic() - t_start
                status = "PASS" if passed else "FAIL"
                print(f"[{status}] circuit={circuit:13s} n={n:2d}  infidelity={infid:.3e}  "
                      f"tvd={tvd:.3e}{extra}  ({elapsed:.1f}s)", flush=True)

    print(f"\nresults -> {csv_path}")

    if all_pass:
        print(f"\nPHASE 1 PASS: infidelity <= {INFIDELITY_THRESHOLD:.0e} for every circuit/n")
        sys.exit(0)
    else:
        print(f"\nPHASE 1 FAIL: some infidelity > {INFIDELITY_THRESHOLD:.0e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
