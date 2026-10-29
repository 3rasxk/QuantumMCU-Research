"""Checks for the Phase 4 analysis. Run:  python3 analysis/phase4/phase4_test.py   (no hardware, reads data/raw only)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import gatecount as G
import model as M

FAILS = []


def check(name, ok):
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        FAILS.append(name)


def main():
    # multi-controlled gate counts quoted in firmware/common/circuits.hpp:102
    check("G(1),G(2),G(3),G(11) = 1,5,21,157461", [sum(G.mc_phase(k)) for k in (1, 2, 3, 11)] == [1, 5, 21, 157461])
    check("qft n=4: 4 H, 6 CPHASE", G.counts("qft", 4) == (4, 0, 6))
    check("bell_ghz n=5: 1 H, 4 CNOT", G.counts("bell_ghz", 5) == (1, 4, 0))
    check("python gate counts equal the unmodified circuits.hpp run in C++", len(G.verify_against_cpp(12)) == 44)

    # closed-form relative-error fit recovers an exact constant
    import pandas as pd
    d = pd.DataFrame({"work": [1e3, 4e3, 1.6e4], "median_us": [2e3, 8e3, 3.2e4]})
    check("fit_m1_pooled recovers c=2", abs(M.fit_m1_pooled(d) - 2.0) < 1e-12)

    # no leakage: held-out points are never in the fit set, and are the largest n of their series
    loc = M.split(C.load_local())
    ok = True
    for (b, c), g in loc.groupby(["board", "circuit"]):
        t = g[g.role == "test"]
        f = g[g.role == "fit"]
        ok &= len(t) == C.N_TEST and t.n.min() > g[g.role != "test"].n.max() and set(t.n).isdisjoint(set(f.n))
        ok &= bool((f.median_us >= C.FLOOR_US).all())
    check("split: test = largest n, disjoint from fit, fit medians above the floor", bool(ok))

    # predictions for test points do not depend on test medians (perturb them, refit, compare)
    P, _ = M.time_model(write=False)
    orig = C.load_local
    def perturbed():
        x = orig().copy()
        top = x.n >= (x.groupby(["board", "circuit"]).n.transform(lambda s: sorted(s)[-C.N_TEST]))
        x.loc[top, ["median_us"]] *= 7.0
        return x
    C.load_local = perturbed
    try:
        P2, _ = M.time_model(write=False)
    finally:
        C.load_local = orig
    check("predictions unchanged when test-point measurements are altered",
          bool(np.allclose(P.pred_M1.to_numpy(), P2.pred_M1.to_numpy()) and np.allclose(P.pred_M2.to_numpy(), P2.pred_M2.to_numpy())))
    check("memory prediction: Uno 7, ESP8266 12, ESP32 largest-block 13",
          {(r.board, r.predictor): r.n_max_pred for r in M.memory_model().itertuples() if r.circuit == "qft"}
          == {("uno", "static_ram"): 7, ("esp8266", "total_free_heap"): 12, ("esp32", "total_free_heap"): 14, ("esp32", "largest_block"): 13})
    print(f"\n{len(FAILS)} failed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
