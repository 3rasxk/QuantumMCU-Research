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

CIRCUITS = ["h_all", "bell_ghz", "qft", "grover", "qpe", "steane_encode"]
N_VALUES_DEFAULT = [2, 3, 4, 6, 8, 10, 12]
# grover: n >= 2 (needs >= 1 control qubit for the oracle's multi-controlled-Z)
# qpe: n >= 3 (needs >= 2 counting qubits + 1 eigenstate qubit)
# steane_encode: fixed at exactly n = 7 (Steane [[7,1,3]] code), never scales with n
CIRCUIT_N_VALUES = {
    "h_all": N_VALUES_DEFAULT,
    "bell_ghz": N_VALUES_DEFAULT,
    "qft": N_VALUES_DEFAULT,
    "grover": N_VALUES_DEFAULT,
    "qpe": [n for n in N_VALUES_DEFAULT if n >= 3],
    "steane_encode": [7],
}
INFIDELITY_THRESHOLD = 1e-3
QPE_TRUE_PHI = 0.25  # U = P(pi/2) บน eigenstate |1>, phi แท้จริงที่ทฤษฎีรู้ค่าแน่นอน


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

    if circuit == "steane_encode":
        n = 7  # คงที่เสมอ ไม่สนใจค่า n ที่ส่งเข้ามา (ดู circuit_steane_encode)

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
    elif circuit == "qpe":
        # ตรงกับ circuit_qpe ใน circuits.hpp ทุกประการ: U = P(pi/2), eigenstate = |1>
        t = n - 1
        eigen = n - 1
        qc.h(eigen)
        qc.p(np.pi, eigen)
        qc.h(eigen)
        u_theta = np.pi / 2
        for q in range(t):
            qc.h(q)
        for q in range(t):
            theta_q = (u_theta * (2 ** q)) % (2 * np.pi)
            qc.cp(theta_q, q, eigen)
        _qft_inverse_qiskit(qc, t)
    elif circuit == "steane_encode":
        # ตรงกับ circuit_steane_encode ใน circuits.hpp ทุกประการ
        qc.h(0)
        qc.cx(0, 2)
        qc.cx(0, 4)
        qc.cx(0, 6)
        qc.h(1)
        qc.cx(1, 2)
        qc.cx(1, 5)
        qc.cx(1, 6)
        qc.h(3)
        qc.cx(3, 4)
        qc.cx(3, 5)
        qc.cx(3, 6)
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


def qpe_estimated_phase(psi: np.ndarray, n: int):
    """หา basis state ที่มีความน่าจะเป็นสูงสุด แล้วถอดรหัสเป็น phi โดยอ่านบิตของ
    counting register แบบกลับด้าน (bit-reversed) — ดูเหตุผลใน circuit_qpe (circuits.hpp):
    QFT ที่นี่ตัด SWAP ท้ายวงจรออก ผลลัพธ์จึงกลับบิตเทียบกับข้อตกลง qubit0=LSB ปกติ
    คืน (phi_estimate, dominant_index, dominant_probability)"""
    t = n - 1
    probs = np.abs(psi) ** 2
    best = int(np.argmax(probs))
    counting_val = 0
    for i in range(t):
        bit = (best >> i) & 1
        counting_val |= bit << (t - 1 - i)
    return counting_val / (2 ** t), best, float(probs[best])


_STEANE_GENERATORS = [
    ("S1_X", (0, 2, 4, 6), "X"),
    ("S2_X", (1, 2, 5, 6), "X"),
    ("S3_X", (3, 4, 5, 6), "X"),
    ("S1_Z", (0, 2, 4, 6), "Z"),
    ("S2_Z", (1, 2, 5, 6), "Z"),
    ("S3_Z", (3, 4, 5, 6), "Z"),
]


def steane_stabilizer_check(psi: np.ndarray) -> dict:
    """ตรวจว่า state ที่ C++ ผลิตจริง (float32, ไม่ใช่ทฤษฎี) เป็น +1-eigenstate ของ
    stabilizer ทั้ง 6 ตัวของ Steane [[7,1,3]] code จริงหรือไม่ (Part 3 — ไม่ใช่แค่
    เทียบ state vector กับ Qiskit เฉย ๆ แต่ตรวจสมบัติทางฟิสิกส์ของโค้ดโดยตรง)
    คืน dict {generator_label: bool}"""
    n = 7
    n_states = 1 << n

    def apply_x_set(state, qubits):
        out = state.copy()
        for q in qubits:
            mask = 1 << q
            nxt = np.empty_like(out)
            for i in range(n_states):
                nxt[i ^ mask] = out[i]
            out = nxt
        return out

    def apply_z_set(state, qubits):
        out = state.copy()
        for q in qubits:
            mask = 1 << q
            signs = np.array([-1.0 if (i & mask) else 1.0 for i in range(n_states)])
            out = out * signs
        return out

    results = {}
    for label, qubits, kind in _STEANE_GENERATORS:
        transformed = apply_x_set(psi, qubits) if kind == "X" else apply_z_set(psi, qubits)
        results[label] = bool(np.allclose(transformed, psi, atol=1e-2))
    return results


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
    args = ap.parse_args()

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
                  "grover_marked_prob", "qpe_estimated_phi", "qpe_phi_error", "steane_stabilizers_ok"]
    all_pass = True
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        f.flush()

        for circuit in CIRCUITS:
            for n in CIRCUIT_N_VALUES[circuit]:
                t_start = time.monotonic()
                psi_cpp = run_cpp_simulator(circuit, n)
                psi_qiskit, depth = run_qiskit_aer(circuit, n)

                infid = infidelity(psi_cpp, psi_qiskit)
                tvd = total_variation_distance(psi_cpp, psi_qiskit)
                passed = infid <= INFIDELITY_THRESHOLD

                extra = ""
                marked_prob = est_phi = est_phi_error = stabilizers_ok = ""
                if circuit == "grover":
                    marked_prob = grover_marked_probability(psi_cpp)
                    extra = f"  P(marked)={marked_prob:.4f}"
                elif circuit == "qpe":
                    est_phi, dom_idx, dom_prob = qpe_estimated_phase(psi_cpp, n)
                    est_phi_error = abs(est_phi - QPE_TRUE_PHI)
                    extra = f"  phi_est={est_phi:.6f} (true={QPE_TRUE_PHI}) P(peak)={dom_prob:.4f}"
                elif circuit == "steane_encode":
                    stab_results = steane_stabilizer_check(psi_cpp)
                    stabilizers_ok = all(stab_results.values())
                    extra = "  stabilizers=" + ",".join(
                        f"{k}:{'OK' if v else 'FAIL'}" for k, v in stab_results.items()
                    )

                all_pass = all_pass and passed
                w.writerow({
                    "circuit": circuit,
                    "n": n,
                    "depth": depth,
                    "infidelity": infid,
                    "tvd": tvd,
                    "pass": passed,
                    "grover_marked_prob": marked_prob,
                    "qpe_estimated_phi": est_phi,
                    "qpe_phi_error": est_phi_error,
                    "steane_stabilizers_ok": stabilizers_ok,
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
