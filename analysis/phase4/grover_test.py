#!/usr/bin/env python3
"""Item 1f: grover theory-vs-implementation tests and 'Phase 1 reference == firmware circuit' tests.
Builds the unmodified firmware circuit on the PC (float32: pc/phase1_validate/main.cpp; double: build_double.sh) and compares with the closed form
P(marked) = sin^2((2k+1) theta). Run: .venv/bin/python analysis/phase4/grover_test.py   (about 2-3 minutes: n=2..12 live in both precisions)"""
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "analysis"))
import gatecount as G  # noqa: E402
import grover_diagnosis as GD  # noqa: E402
from phase1_compare import build_qiskit_circuit  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def firmware_sequence(tmp, circuit, n):
    exe = os.path.join(tmp, "seq")
    if not os.path.exists(exe):
        shutil.copy(os.path.join(ROOT, "firmware", "common", "circuits.hpp"), os.path.join(tmp, "circuits.hpp"))
        for f in ("qsim.hpp", "harness.cpp"):
            shutil.copy(os.path.join(HERE, "seq_stub", f), tmp)
        subprocess.run(["g++", "-std=c++11", "-O1", "-o", exe, os.path.join(tmp, "harness.cpp")], check=True, capture_output=True)
    out = subprocess.run([exe, circuit, str(n)], check=True, capture_output=True, text=True).stdout.splitlines()
    seq = []
    for line in out:
        p = line.split()
        seq.append((p[0], *[int(x) for x in p[1:3 if p[0] == "CP" else (3 if p[0] == "CX" else 2)]], *([float(p[3])] if p[0] == "CP" else [])))
    return seq


def qiskit_sequence(circuit, n):
    seq = []
    for inst in build_qiskit_circuit(circuit, n).data:
        name, q = inst.operation.name, [inst.qubits[i]._index for i in range(len(inst.qubits))]
        if name == "h":
            seq.append(("H", q[0]))
        elif name == "cx":
            seq.append(("CX", q[0], q[1]))
        elif name == "cp":
            seq.append(("CP", q[0], q[1], float(inst.operation.params[0])))
        elif name == "p":                                   # the firmware's cphase(q, q, theta): control == target
            seq.append(("CP", q[0], q[0], float(inst.operation.params[0])))
        else:
            seq.append((name,))
    return seq


def main():
    # ---- k and theory, n = 2..22, no simulation needed
    bad_k = [(n, G.grover_iterations(n), max(int((np.pi / 4) * np.sqrt(1 << n)), 1)) for n in range(2, 23)
             if G.grover_iterations(n) != max(int((np.pi / 4) * np.sqrt(1 << n)), 1)]
    check("iteration count k: firmware float32 formula == Qiskit float64 formula for every n = 2..22", not bad_k, str(bad_k))
    pt = {n: float(np.sin((2 * G.grover_iterations(n) + 1) * np.arcsin(1 / np.sqrt(2 ** n))) ** 2) for n in range(2, 23)}
    check("closed-form P(marked) of the firmware's k is a valid Grover circuit: >= 0.94 for every n = 2..22 (min over n)", min(pt.values()) >= 0.94, str(min(pt.values())))
    check("... and >= 0.99 for n >= 8 where k is large", all(pt[n] >= 0.99 for n in range(8, 23)), str({n: pt[n] for n in range(8, 23) if pt[n] < 0.99}))

    with tempfile.TemporaryDirectory() as tmp:
        # ---- the Phase 1 reference IS the firmware circuit: same gate sequence, qubits and angles (n = 2..7 in full)
        def same_seq(a, b):
            return len(a) == len(b) and all((x[:-1] == y[:-1] and abs(x[-1] - y[-1]) <= 1e-6 * max(1.0, abs(y[-1]))) if x[0] == "CP" else x == y for x, y in zip(a, b))
        mism = [(c, n) for c in ("h_all", "bell_ghz", "qft", "grover") for n in (2, 3, 4, 5, 6, 7, 8)
                if not same_seq(firmware_sequence(tmp, c, n), qiskit_sequence(c, n))]
        check("Phase 1 / Phase 3 Qiskit circuit == firmware circuit: gate by gate (kind, qubits, angle <= 1e-6 relative), 4 circuits, n = 2..8 (grover n=8: 38 089 gates)", not mism, str(mism))
        a = firmware_sequence(tmp, "grover", 2)
        check("sanity of the comparison itself: a deliberately altered angle is detected", not same_seq(a, [(x[0], *x[1:-1], x[-1] + 1e-3) if x[0] == "CP" else x for x in a]) if any(x[0] == "CP" for x in a) else True)

        # ---- implementations vs closed form, n = 2..12, both precisions
        f32, f64 = GD.build_runners(tmp)
        worst_dir32, worst_norm = 0.0, []
        for n in range(2, 13):
            ideal, k, th = GD.ideal_state(n)
            s32, s64 = GD.run_cpp(f32, n), GD.run_cpp(f64, n)
            p_th = float(np.sin((2 * k + 1) * th) ** 2)
            check(f"n={n}: double build: P(marked) == sin^2((2k+1)theta) to 1e-8 and norm^2 == 1", abs(abs(s64[-1]) ** 2 - p_th) < 1e-8 and abs(np.vdot(s64, s64).real - 1) < 1e-8,
                  f"{abs(s64[-1]) ** 2} vs {p_th}")
            check(f"n={n}: double build: state equals the closed-form Grover state (infidelity < 1e-8)", GD.infid(ideal, s64) < 1e-8, str(GD.infid(ideal, s64)))
            d32 = GD.infid_norm(ideal, s32)
            worst_dir32 = max(worst_dir32, d32)
            n2 = float(np.vdot(s32, s32).real)
            nh = G.counts("grover", n)[0]
            c32 = float(np.float32(0.70710678118654752))
            pred_n2 = (2 * c32 * c32) ** nh                   # every H multiplies norm^2 by 2 c^2 with c the float32 constant 1/sqrt(2)
            if n >= 8:
                worst_norm.append(np.log(pred_n2) / np.log(n2))   # predicted log norm loss / measured log norm loss
            check(f"n={n}: float32 build: marked state is the argmax and direction matches (normalised infidelity < 1e-4)", int(np.argmax(np.abs(s32))) == len(s32) - 1 and d32 < 1e-4, str(d32))
        check("the biased float32 constant predicts the measured norm loss within +10..+25 % (it over-predicts: predicted/measured log loss in 1.10..1.25) for n = 8..12",
              min(worst_norm) > 1.10 and max(worst_norm) < 1.25, str(worst_norm))
    print(f"\n{len(FAILS)} failed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
