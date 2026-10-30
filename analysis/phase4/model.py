"""Phase 4 Step 1: memory-wall model, time model with held-out validation, micros()-vs-counter agreement.

Writes data/processed/phase4/{memory_model,time_fit,time_validation,time_predictions,counter_agreement,offload}.csv.
Every number in docs/phase4_report.md comes from these files.
"""
import os

import numpy as np
import pandas as pd
from scipy.optimize import nnls

import p4common as C
import gatecount as G
from common import weak  # noqa: E402

os.makedirs(C.PROC, exist_ok=True)


# ----------------------------------------------------------------------------------------------
# Memory model
# ----------------------------------------------------------------------------------------------
def memory_model():
    """n_max(pred) = max n such that  overhead + 8 * 2^n <= B  (8 B = complex float32).

    B and overhead are read from the n = 2 .. low-n runs only (never from the wall point):
      Uno      B = 2048 B SRAM (compile_ram_pct = used / 2048, audit B2b); overhead = compile_ram_used - 8*2^n
               from the ok points (constant 200 B). The state is a static array, so the wall is a link-time overflow.
      ESP8266  B = free_heap_before + 8*2^n at n = 2 (free_heap_before is read AFTER malloc of the state,
               firmware/esp32/src/main.cpp:66 vs :80, same pattern on the ESP8266); overhead 0 beyond that.
      ESP32    two candidates: total free heap (same construction) and the largest free block
               heap_caps_get_largest_free_block (also read after the malloc). The state needs ONE contiguous block.
    """
    loc = C.load_local()
    walls = C.load_walls()
    rows = []
    for b in C.BOARDS:
        last_ok = {c: int(loc[(loc.board == b) & (loc.circuit == c)].n.max()) for c in C.CIRCUITS}
        for c in C.CIRCUITS:
            raw = pd.read_csv(os.path.join(C.series_dir(2, b, c), "raw.csv"))
            n_lo = int(raw.n.min())
            r0 = raw[raw.n == n_lo].iloc[0]
            w = walls[(walls.board == b) & (walls.circuit == c)]
            wall_n = int(w.n.iloc[0]) if len(w) else None
            wall_ev = (w.status.iloc[0] + " (" + w.file.iloc[0] + ")") if len(w) else "none observed"
            cands = {}
            if b == "uno":
                mw = pd.read_csv(os.path.join(C.series_dir(2, b, c), "memory_wall.csv"))
                ok = mw[mw.status == "ok"]
                over = (ok.compile_ram_used_bytes - ok.theoretical_bytes).unique()
                assert len(over) == 1, over
                cands["static_ram"] = (2048.0 - float(over[0]), float(over[0]))
            else:
                free_total = float(r0.free_heap_before + 8 * 2 ** n_lo)
                cands["total_free_heap"] = (free_total, 0.0)
                if b == "esp32":
                    cands["largest_block"] = (float(r0.largest_block), 0.0)
            for name, (B, over) in cands.items():
                n_pred = int(np.floor(np.log2(B / 8.0)))
                rows.append(dict(board=b, circuit=c, predictor=name, B_bytes=B, overhead_bytes=over,
                                 n_max_pred=n_pred, last_ok_n=last_ok[c], wall_n=wall_n,
                                 wall_evidence=wall_ev,
                                 match=("n/a (no wall observed)" if wall_n is None else str(n_pred == wall_n - 1)),
                                 state_bytes_at_pred=8 * 2 ** n_pred, state_bytes_at_pred_plus1=8 * 2 ** (n_pred + 1)))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(C.PROC, "memory_model.csv"), index=False)
    return df


# Time model: see timemodel.py (items 3-5 of the fixes)
from timemodel import time_model, time_sensitivity, run_all as time_run_all  # noqa: E402,F401


# ----------------------------------------------------------------------------------------------
# micros() vs counter (Phase 2 only; Phase 3 counter data are excluded by policy)
# ----------------------------------------------------------------------------------------------
def counter_agreement():
    """micros() vs counter from USABLE counter points only (analysis/common/counter_validity.py); see counter_report.py"""
    import counter_report as CR
    vt, ex, a, s = CR.main()
    return a


def counter_summary(D):
    import counter_report as CR
    return CR.summary(D)


# ----------------------------------------------------------------------------------------------
# Offload crossover
# ----------------------------------------------------------------------------------------------
def _bracket_weak(g, first):
    """True if a point that fixes the crossover (the last n before it and the first n after it, local and offload) is weak"""
    if first is None:
        return False
    b = g[g.n.isin([first - 1, first])]
    return bool(((b.reps_local < weak.WEAK_MIN) | (b.reps_offload < weak.WEAK_MIN)).any())


def offload_crossover():
    loc, off = C.load_local(), C.load_offload()
    m = loc.merge(off, on=["board", "circuit", "n"], suffixes=("_local", "_offload"))
    m["offload_over_local"] = m.median_us_offload / m.median_us_local
    m.to_csv(os.path.join(C.PROC, "offload_vs_local.csv"), index=False)
    rows = []
    for (b, c), g in m.groupby(["board", "circuit"]):
        g = g.sort_values("n")
        gn = g[(g.reps_local >= weak.WEAK_MIN) & (g.reps_offload >= weak.WEAK_MIN)]   # non-weak overlapping points only
        faster = g[g.median_us_offload < g.median_us_local]
        first = int(faster.n.min()) if len(faster) else None
        # a crossover is "stable" if offload stays faster at every larger measured n
        stable = bool(first is not None and (g[g.n >= first].median_us_offload < g[g.n >= first].median_us_local).all())
        interp = None
        if first is not None and first > g.n.min():
            lo = g[g.n == first - 1].iloc[0]
            hi = g[g.n == first].iloc[0]
            d0, d1 = np.log(lo.offload_over_local), np.log(hi.offload_over_local)  # >0 then <0
            if d0 > 0 > d1:
                interp = float(first - 1 + d0 / (d0 - d1))
        rows.append(dict(board=b, circuit=c, n_range=f"{g.n.min()}-{g.n.max()}", n_local_max=int(g.n.max()),
                         first_n_offload_faster=first, stable_to_n_local_max=stable,
                         n_star_interpolated=interp,
                         ratio_at_n_largest_overlap=float(g.offload_over_local.iloc[-1]), n_largest_overlap=int(g.n.iloc[-1]),
                         largest_overlap_is_weak=bool(g.iloc[-1].reps_local < weak.WEAK_MIN or g.iloc[-1].reps_offload < weak.WEAK_MIN),
                         n_largest_overlap_nonweak=int(gn.n.iloc[-1]), ratio_at_nonweak=float(gn.offload_over_local.iloc[-1]),
                         min_offload_req=int(g.reps_offload.min()), min_local_reps=int(g.reps_local.min()),
                         crossover_weak=_bracket_weak(g, first),
                         label="interpolated between measured n; never extrapolated" if interp is not None else
                               ("measured: offload already faster at the smallest n" if first is not None else "no crossover in the measured range")))
    X = pd.DataFrame(rows)
    X.to_csv(os.path.join(C.PROC, "offload_crossover.csv"), index=False)
    return m, X


if __name__ == "__main__":
    pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_colwidth", 60)
    print(memory_model().drop(columns=["wall_evidence"]).to_string())
    P, V = time_model()
    print(pd.read_csv(os.path.join(C.PROC, "time_fit.csv")).to_string())
    print(V[V.part == "test"].to_string())
    print(pd.read_csv(os.path.join(C.PROC, "time_validation_by_board.csv")).to_string())
    print(time_sensitivity().pivot_table(index=["model", "board"], columns=["n_test", "floor_us"], values="mape_pct").round(1).to_string())
    D = counter_agreement()
    print(counter_summary(D).to_string())
    m, X = offload_crossover()
    print(X.to_string())
