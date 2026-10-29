"""Do Phase 2 (firmware/common/circuits.hpp) and Phase 3 (analysis/phase1_compare.build_qiskit_circuit) run the same circuit?
Compares gate-call counts per kind for n = 2..N (Qiskit build is memory-heavy for grover, so N_GROVER_BUILD caps the build) and the
grover iteration count (C++ float32 vs Qiskit float64) up to n = 22. Read-only; writes data/derived/circuit_equivalence.csv."""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
sys.path.insert(0, os.path.join(ROOT, "analysis", "phase4"))
import gatecount as G  # noqa: E402  (counts mirrored from circuits.hpp, itself verified against the real header in C++)
from phase1_compare import build_qiskit_circuit  # noqa: E402

N_BUILD = {"h_all": 14, "bell_ghz": 14, "qft": 14, "grover": 10}


def qiskit_counts(c, n):
    ops = build_qiskit_circuit(c, n).count_ops()
    return (ops.get("h", 0), ops.get("cx", 0), ops.get("cp", 0) + ops.get("p", 0))


rows = []
for c, nmax in N_BUILD.items():
    for n in range(2, nmax + 1):
        a, b = G.counts(c, n), qiskit_counts(c, n)
        rows.append(dict(circuit=c, n=n, firmware_H_CNOT_CPHASE=a, qiskit_H_CX_CP_P=b, equal=a == b))
df = pd.DataFrame(rows)
it = []
for n in range(2, 23):
    c32 = G.grover_iterations(n)
    c64 = max(int((np.pi / 4) * np.sqrt(1 << n)), 1)
    it.append(dict(n=n, grover_iters_firmware_float32=c32, grover_iters_qiskit_float64=c64, equal=c32 == c64))
it = pd.DataFrame(it)
os.makedirs(os.path.join(ROOT, "data", "derived"), exist_ok=True)
df.to_csv(os.path.join(ROOT, "data", "derived", "circuit_equivalence.csv"), index=False)
it.to_csv(os.path.join(ROOT, "data", "derived", "grover_iterations_equivalence.csv"), index=False)
print("gate-count comparison:", len(df), "points, all equal:", bool(df.equal.all()))
print(df[~df.equal].to_string())
print("grover iterations n=2..22 all equal:", bool(it.equal.all()))
print(it[~it.equal].to_string())
sys.exit(0 if df.equal.all() and it.equal.all() else 1)
