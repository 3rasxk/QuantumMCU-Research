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

import csv
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
BINARY = REPO_ROOT / "pc" / "phase1_validate" / "phase1_validate"
RESULTS_DIR = REPO_ROOT / "results" / "phase1"
CXXFLAGS = "-O2 -std=c++11 -Wall -Wextra"  # ต้องตรงกับ pc/phase1_validate/build.sh

CIRCUITS = ["h_all", "bell_ghz", "qft"]
N_VALUES = [2, 3, 4, 6, 8, 10, 12]
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


def log_metadata():
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
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = RESULTS_DIR / "phase1_metadata.csv"
    with open(meta_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "value"])
        for k, v in meta.items():
            w.writerow([k, v])
    print(f"metadata -> {meta_path}")
    return meta


def main():
    if not BINARY.exists():
        print(f"error: {BINARY} not found. run pc/phase1_validate/build.sh first", file=sys.stderr)
        sys.exit(1)

    log_metadata()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "infidelity_tvd.csv"

    rows = []
    all_pass = True
    for circuit in CIRCUITS:
        for n in N_VALUES:
            psi_cpp = run_cpp_simulator(circuit, n)
            psi_qiskit, depth = run_qiskit_aer(circuit, n)

            infid = infidelity(psi_cpp, psi_qiskit)
            tvd = total_variation_distance(psi_cpp, psi_qiskit)
            passed = infid <= INFIDELITY_THRESHOLD

            all_pass = all_pass and passed
            rows.append({
                "circuit": circuit,
                "n": n,
                "depth": depth,
                "infidelity": infid,
                "tvd": tvd,
                "pass": passed,
            })
            status = "PASS" if passed else "FAIL"
            print(f"[{status}] circuit={circuit:9s} n={n:2d}  infidelity={infid:.3e}  tvd={tvd:.3e}")

    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["circuit", "n", "depth", "infidelity", "tvd", "pass"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nresults -> {csv_path}")

    if all_pass:
        print(f"\nPHASE 1 PASS: infidelity <= {INFIDELITY_THRESHOLD:.0e} for every circuit/n")
        sys.exit(0)
    else:
        print(f"\nPHASE 1 FAIL: some infidelity > {INFIDELITY_THRESHOLD:.0e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
