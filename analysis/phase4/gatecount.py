"""Gate-call counts per circuit and n, derived from firmware/common/circuits.hpp (read-only).

Each count mirrors the C++ control flow; `verify_against_cpp()` runs the UNMODIFIED circuits.hpp
with counting kernels (count_stub/) and asserts equality, so the Python is not trusted on its own.

Source lines (firmware/common/circuits.hpp):
  h_all     :20-25   n x H
  bell_ghz  :33-39   1 H + (n-1) CNOT
  qft       :53-61, 80-83   n H + n(n-1)/2 CPHASE
  grover    :152-181 init H^n, then floor(pi/4 * sqrtf(2^n)) iterations (:158-160) of
            oracle MC-phase(n-1) (:164), diffusion H^n, n x (H CP H), MC-phase(n-1), n x (H CP H), H^n (:166-179)
  mc_phase  :108-125  k<=1: 1 CPHASE; else 2 CPHASE + 2 mc_x(k-1) + mc_phase(k-1)
  mc_x      :127-135  k==1: 1 CNOT; else 2 H + mc_phase(k)      (G(1)=1, G(2)=5, G(3)=21 as in the :102 comment)
Every kernel loops over all 2^n indices (firmware/common/qsim.hpp:65, 86, 107), so one gate call = 2^n loop iterations.
"""
import hashlib
import os
import shutil
import subprocess
import tempfile
from functools import lru_cache

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
KINDS = ("H", "CNOT", "CPHASE")


def _add(a, b, m=1):
    return tuple(x + m * y for x, y in zip(a, b))


@lru_cache(maxsize=None)
def mc_phase(k):
    if k <= 1:
        return (0, 0, 1)
    c = (0, 0, 2)
    c = _add(c, mc_x(k - 1), 2)
    return _add(c, mc_phase(k - 1))


@lru_cache(maxsize=None)
def mc_x(k):
    if k == 1:
        return (0, 1, 0)
    return _add((2, 0, 0), mc_phase(k))


def grover_iterations(n):
    # float32 arithmetic exactly as circuits.hpp:158-160
    pi = np.float32(3.14159265358979323846)
    it = int((pi / np.float32(4.0)) * np.sqrt(np.float32(2 ** n)))
    return max(it, 1)


def counts(circuit, n):
    """(n_H, n_CNOT, n_CPHASE) gate calls, excluding the init sweep."""
    if circuit == "h_all":
        return (n, 0, 0)
    if circuit == "bell_ghz":
        return (1, n - 1, 0)
    if circuit == "qft":
        return (n, 0, n * (n - 1) // 2)
    if circuit == "grover":
        # per iteration: 2 x MC-phase(n-1) (oracle :164, :173); H: n + 2n + 2n + n = 6n; CPHASE: n + n = 2n (:167-179)
        per = _add(_add((0, 0, 0), mc_phase(n - 1), 2), (6 * n, 0, 2 * n))
        return _add((n, 0, 0), per, grover_iterations(n))
    raise ValueError(circuit)


def total_gates(circuit, n):
    return sum(counts(circuit, n))


def work(circuit, n):
    """Loop iterations over the state vector: gate calls x 2^n (every kernel sweeps all 2^n indices)."""
    return total_gates(circuit, n) * 2 ** n


def verify_against_cpp(nmax=14):
    """Compile the unmodified circuits.hpp with counting kernels and compare. Returns the C++ table."""
    src = os.path.join(ROOT, "firmware", "common", "circuits.hpp")
    with tempfile.TemporaryDirectory() as td:
        shutil.copy(src, os.path.join(td, "circuits.hpp"))
        assert hashlib.sha256(open(src, "rb").read()).digest() == hashlib.sha256(
            open(os.path.join(td, "circuits.hpp"), "rb").read()).digest()
        for f in ("qsim.hpp", "harness.cpp"):
            shutil.copy(os.path.join(HERE, "count_stub", f), td)
        exe = os.path.join(td, "harness")
        subprocess.run(["g++", "-std=c++11", "-O1", "-o", exe, os.path.join(td, "harness.cpp")], check=True)
        out = subprocess.run([exe, str(nmax)], check=True, capture_output=True, text=True).stdout
    rows = []
    for line in out.strip().splitlines():
        c, n, init, h, cn, cp = line.split(",")
        n = int(n)
        assert int(init) == 1
        assert (int(h), int(cn), int(cp)) == counts(c, n), (c, n, (int(h), int(cn), int(cp)), counts(c, n))
        rows.append((c, n, int(h), int(cn), int(cp)))
    return rows


if __name__ == "__main__":
    rows = verify_against_cpp(14)
    print(f"python counts == C++ counts for {len(rows)} (circuit, n) pairs; grover iterations n=2..14:",
          [grover_iterations(n) for n in range(2, 15)])
    for k in (1, 2, 3, 11):
        print("G(%d) =" % k, sum(mc_phase(k)))
