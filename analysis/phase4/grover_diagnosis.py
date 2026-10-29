"""Phase 4 item 1: why does the float32 grover state differ from Qiskit Aer (Phase 1: infidelity 0.109, P(marked) 0.89 at n=12)?

Per n it compares four things for the SAME circuit:
  ideal   closed form of Grover after k iterations: marked amplitude sin((2k+1)t), every other amplitude cos((2k+1)t)/sqrt(N-1),
          t = asin(1/sqrt(N)). Independent of every simulator.
  f32     the firmware's circuit (firmware/common/circuits.hpp, float32) run on the PC (pc/phase1_validate/main.cpp, as in Phase 1)
  f64     the SAME circuit source evaluated in double (pc/phase1_validate/build_double.sh)
  aer     Qiskit Aer statevector (double) of analysis/phase1_compare.build_qiskit_circuit (sliced for n >= 11)
Metrics: norm^2, P(marked) raw (|psi[2^n-1]|^2, what Phase 1 reports) and normalised, infidelity 1-|<a|b>|^2 as Phase 1 defines it
(NO renormalisation) and with both states normalised first.
Heavy n (13, 14: float32 and double C++ runs, no Aer) via --ns; results merge into data/derived/grover_diagnosis.csv.
"""
import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "analysis"))
import gatecount as G  # noqa: E402

OUT = os.path.join(ROOT, "data", "derived", "grover_diagnosis.csv")
AER_MAX_N = 12   # Aer is infeasible above this on the project PC (Phase 3: n=13 takes about 3200 s per Aer run, n=14 over 3 h)


def build_runners(tmp):
    f32 = os.path.join(tmp, "phase1_validate_f32")
    subprocess.run(["g++", "-O2", "-std=c++11", "-o", f32, os.path.join(ROOT, "pc", "phase1_validate", "main.cpp")], check=True,
                   capture_output=True)
    subprocess.run([os.path.join(ROOT, "pc", "phase1_validate", "build_double.sh"), os.path.join(tmp, "dbl")], check=True, capture_output=True)
    return f32, os.path.join(tmp, "dbl", "phase1_validate_double")


def run_cpp(exe, n):
    out = subprocess.run([exe, "grover", str(n)], check=True, capture_output=True, text=True).stdout.splitlines()
    arr = np.array([[float(x) for x in line.split(",")[1:]] for line in out[2:]])
    return arr[:, 0] + 1j * arr[:, 1]


def ideal_state(n):
    k = G.grover_iterations(n)
    N = 2 ** n
    t = np.arcsin(1 / np.sqrt(N))
    psi = np.full(N, np.cos((2 * k + 1) * t) / np.sqrt(N - 1), dtype=complex)
    psi[-1] = np.sin((2 * k + 1) * t)
    return psi, k, t


def infid(a, b):
    return 1.0 - float(np.abs(np.vdot(a, b)) ** 2)


def infid_norm(a, b):
    return infid(a / np.linalg.norm(a), b / np.linalg.norm(b))


def describe(name, psi, ideal):
    return {f"{name}_norm2": float(np.vdot(psi, psi).real), f"{name}_p_marked_raw": float(abs(psi[-1]) ** 2),
            f"{name}_p_marked_normalised": float(abs(psi[-1]) ** 2 / np.vdot(psi, psi).real),
            f"{name}_infid_vs_ideal_raw": infid(ideal, psi), f"{name}_infid_vs_ideal_normalised": infid_norm(ideal, psi)}


def diagnose(n, f32, f64, with_aer):
    ideal, k, t = ideal_state(n)
    k64 = max(int((np.pi / 4) * np.sqrt(1 << n)), 1)
    nh, ncn, ncp = G.counts("grover", n)
    row = dict(n=n, k_firmware_float32=k, k_qiskit_float64=k64, theta=t,
               p_theory_firmware_k=float(np.sin((2 * k + 1) * t) ** 2), p_theory_qiskit_k=float(np.sin((2 * k64 + 1) * t) ** 2),
               n_gates=nh + ncn + ncp, n_H=nh, n_CNOT=ncn, n_CPHASE=ncp)
    states = {"f32": run_cpp(f32, n), "f64": run_cpp(f64, n)}
    if with_aer:
        from phase1_compare import run_qiskit_aer
        states["aer"] = run_qiskit_aer("grover", n, 1_000_000 if n >= 11 else 0)[0]
    for name, psi in states.items():
        row.update(describe(name, psi, ideal))
        row[f"{name}_argmax_is_all_ones"] = bool(np.argmax(np.abs(psi)) == len(psi) - 1)
    for a, b in (("f32", "aer"), ("f64", "aer"), ("f32", "f64")):
        if a in states and b in states:
            row[f"infid_{a}_vs_{b}_raw"] = infid(states[b], states[a])
            row[f"infid_{a}_vs_{b}_normalised"] = infid_norm(states[b], states[a])
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ns", type=int, nargs="+", default=list(range(2, AER_MAX_N + 1)))
    args = ap.parse_args()
    old = pd.read_csv(OUT) if os.path.exists(OUT) else pd.DataFrame()
    with tempfile.TemporaryDirectory() as tmp:
        f32, f64 = build_runners(tmp)
        rows = []
        for n in args.ns:
            r = diagnose(n, f32, f64, with_aer=n <= AER_MAX_N)
            rows.append(r)
            print(n, {k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items() if k in
                      ("k_firmware_float32", "p_theory_firmware_k", "f32_norm2", "f32_p_marked_raw", "f32_infid_vs_ideal_raw",
                       "f32_infid_vs_ideal_normalised", "f64_infid_vs_ideal_raw", "aer_infid_vs_ideal_raw")}, flush=True)
    new = pd.DataFrame(rows)
    old = old[~old.n.isin(new.n)] if len(old) else old
    df = pd.concat([old, new]).sort_values("n").reset_index(drop=True)
    df.to_csv(OUT, index=False)


if __name__ == "__main__":
    main()
