#!/usr/bin/env python3
"""Tests for items 3, 4d and 5 of the fixes. Run: .venv/bin/python analysis/phase4/timemodel_test.py"""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "analysis"))
import p4common as C  # noqa: E402
import timemodel as TM  # noqa: E402
import model as M  # noqa: E402
from common import weak  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def synthetic(collinear=False, n=8):
    rng = np.random.default_rng(1)
    rows = []
    for i in range(n):
        nn = i + 3
        x_h = float(nn * 2 ** nn)
        x_cn = 2.0 * x_h if collinear else float((nn - 1) * 2 ** nn + rng.integers(1, 50) * nn)
        x_cp = 3.0 * x_h if collinear else float(nn * (nn - 1) / 2 * 2 ** nn + rng.integers(1, 90))
        x_g = float(nn) if not collinear else 5.0 * x_h
        t = 0.5 * x_h + 0.1 * x_cn + 0.2 * x_cp + 4.0 * x_g
        rows.append(dict(n=nn, x_h=x_h, x_cn=x_cn, x_cp=x_cp, x_g=x_g, median_us=t, work=x_h + x_cn + x_cp))
    return pd.DataFrame(rows)


def main():
    # ---- item 3e: identifiability on a synthetic collinear design matrix
    good = TM.design_diagnostics(synthetic(False, 12), 4, np.array([0.5, 0.1, 0.2, 4.0]))
    bad = TM.design_diagnostics(synthetic(True, 12), 4, np.array([0.5, 0.1, 0.2, 4.0]))
    check("well-posed synthetic design: full rank, identifiable", good["rank"] == 4 and good["identifiable"], str(good))
    check("collinear synthetic design (columns proportional): rank < 4 and NOT identifiable", bad["rank"] < 4 and not bad["identifiable"], str(bad))
    few = TM.design_diagnostics(synthetic(False, 5), 4, np.array([0.5, 0.1, 0.2, 4.0]))
    check("rule n_fit >= params + 2: 5 points for 4 parameters is not identifiable", not few["identifiable"], str(few))
    onbound = TM.design_diagnostics(synthetic(False, 12), 4, np.array([0.5, 0.1, 0.0, 4.0]))
    check("a coefficient on the NNLS zero boundary is not identifiable", not onbound["identifiable"], str(onbound))
    check("an exact synthetic NNLS fit recovers the 4 parameters", np.allclose(TM.fit_m2(synthetic(False, 12)), [0.5, 0.1, 0.2, 4.0], rtol=1e-6))

    # ---- item 3e: the split never puts a test point into the fit; item 5: weak points are never fitted
    P, ident = TM.time_model(write=False)
    ok = True
    for (b, c), g in P.groupby(["board", "circuit"]):
        t, f = g[g.role == "test"], g[g.role == "fit"]
        ok &= len(t) == C.N_TEST and set(t.n).isdisjoint(set(f.n)) and t.n.min() > f.n.max() if len(f) else True
    check("every series: the largest N_TEST n are test, disjoint from and larger than every fit n", bool(ok))
    check("no weak point (reps < 30) is a fit point", not P[(P.role == "fit") & P.weak].any().any() and not ((P.role == "fit") & P.weak).any())
    check("weak rule: 29 weak, 30 not weak (reps and requests share one rule)", weak.is_weak(29) and not weak.is_weak(30) and weak.WEAK_MIN == 30)
    check("the weak points of the data are the expected ones (ESP32 grover n=10 [100 rows, 18 independent], 11, 12; ESP8266 grover n=10)",
          sorted(map(tuple, P[P.weak][["board", "circuit", "n"]].drop_duplicates().to_records(index=False).tolist())) ==
          [("esp32", "grover", 10), ("esp32", "grover", 11), ("esp32", "grover", 12), ("esp8266", "grover", 10)])
    # effective repetitions (exact copies are not independent): synthetic and real cases
    rng = np.random.default_rng(3)
    uniq = list(rng.integers(1000, 2000, 60))
    check("effective_reps: an independent series keeps all its rows", weak.effective_reps(uniq) == 60)
    copied = uniq[:12] + (uniq[12:22] * 8)
    check("effective_reps: rows 22.. are exact copies of rows 12..21 (period 10) -> 22 independent", weak.effective_reps(copied) == 22, str(weak.effective_reps(copied)))
    check("effective_reps: a constant series is NOT flagged as a copy", weak.effective_reps([3] * 100) == 100)
    check("effective_reps: a two-valued series is NOT flagged as a copy", weak.effective_reps([2, 3] * 50) == 100)
    check("a series with 100 rows but 22 independent repetitions is weak", weak.is_weak_values(copied) and not weak.is_weak_values(uniq))
    l = C.load_local()
    r10 = l[(l.board == "esp32") & (l.circuit == "grover") & (l.n == 10)].iloc[0]
    r9 = l[(l.board == "esp32") & (l.circuit == "grover") & (l.n == 9)].iloc[0]
    check("ESP32 grover n=10: 100 recorded rows, 18 independent; n=9: 39 independent (not weak)", r10.reps_recorded == 100 and r10.reps == 18 and r9.reps == 39)
    # the weak and hash rules must act on the points they name: shrink the held-out set so those points become fit CANDIDATES
    s1 = TM.split(TM.load_points(), n_test=1)
    role = lambda b, c, n: s1[(s1.board == b) & (s1.circuit == c) & (s1.n == n)].role.iloc[0]
    check("with held-out = 1, the weak ESP32 grover n=11 is a fit candidate and is refused (role not_fitted_weak)", role("esp32", "grover", 11) == "not_fitted_weak", role("esp32", "grover", 11))
    check("... ESP32 grover n=10 (18 independent reps) is refused too", role("esp32", "grover", 10) == "not_fitted_weak")
    check("... and the hash-flagged ESP8266 grover n=9 (class B) is refused (role not_fitted_hash)", role("esp8266", "grover", 9) == "not_fitted_hash", role("esp8266", "grover", 9))
    check("... and ESP8266 grover n=8 (class X) is refused (role not_fitted_hash)", role("esp8266", "grover", 8) == "not_fitted_hash")
    check("... while an ordinary point (ESP32 grover n=9, 39 independent reps, class A) is a fit point", role("esp32", "grover", 9) == "fit")
    prim, withw = TM.score(P, "M2"), TM.score(P, "M2", include_weak=True)
    check("primary MAPE excludes weak test points; the secondary number includes them (more points)", prim["n"] < withw["n"], f"{prim['n']} vs {withw['n']}")
    # the fit does not change when a weak point's measurement is altered
    base = TM.load_points()
    alt = base.copy()
    m = (alt.board == "esp32") & (alt.circuit == "grover") & (alt.n == 11)
    alt.loc[m, "median_us"] *= 5.0
    P2, _ = TM.time_model(write=False, loc=alt)
    check("altering a weak point (ESP32 grover n=11) leaves every prediction unchanged",
          np.allclose(P.pred_M2.to_numpy(), P2.pred_M2.to_numpy()) and np.allclose(P.pred_M1.to_numpy(), P2.pred_M1.to_numpy()))

    # ---- item 4d: a fit mixing timing-relevant firmware versions fails unless explicitly allowed
    mixed = base[(base.board == "esp8266") & (base.circuit == "grover")].copy()
    mixed["timing_class"] = ["A"] * (len(mixed) - 2) + ["B", "B"]
    raised = False
    try:
        TM.assert_homogeneous(mixed)
    except ValueError:
        raised = True
    check("assert_homogeneous raises when a fit spans timing classes A and B", raised)
    check("... and passes when explicitly allowed", TM.assert_homogeneous(mixed, allow_mixed=True) == ["A", "B"])
    hf = base[base.hash_flagged][["board", "circuit", "n"]]
    base = TM.load_points()
    check("hash-flagged points are exactly ESP8266 grover n=8, 9, 10 (classes X, B, B); none is ever a fit point",
          sorted(map(tuple, hf.to_records(index=False).tolist())) == [("esp8266", "grover", 8), ("esp8266", "grover", 9), ("esp8266", "grover", 10)]
          and not ((P.role == "fit") & P.hash_flagged).any())
    check("the class table has an entry for every Phase 2 hash on disk", set(base.timing_class) <= {"A", "B", "X"})

    # ---- item 5d: Phase 3 covers every Phase 2 ok n for every board x circuit, and F4 plots the full overlapping range
    import make_figures as MF
    series = MF.f4_series()
    miss = []
    for (b, c), (lg, og) in series.items():
        gap = sorted(set(lg.n) - set(og.n))
        if gap:
            miss.append((b, c, gap))
    check("Phase 3 has data at every n where Phase 2 has ok data, all 12 board x circuit rows", not miss, str(miss))
    check("F4 plots 12 series, each with the complete local and the complete offload point set", len(series) == 12 and all(len(lg) > 0 and len(og) > 0 for lg, og in series.values()))
    m, X = M.offload_crossover()
    check("crossover table: every row carries the ratio at the largest overlapping n and a non-weak alternative", X.ratio_at_nonweak.notna().all() and X.n_largest_overlap.notna().all())
    check("crossover label: interpolated or measured, never an extrapolation (n* within the measured local range)",
          all((pd.isna(r.n_star_interpolated)) or (2 <= r.n_star_interpolated <= r.n_local_max) for r in X.itertuples()))
    print(f"\n{len(FAILS)} failed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
