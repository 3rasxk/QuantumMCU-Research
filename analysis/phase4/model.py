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
            raw = C.raw_selected(2, b, c)
            n_lo = int(raw.n.min())
            r0 = raw[raw.n == n_lo].iloc[0]
            w = walls[(walls.board == b) & (walls.circuit == c)]
            wall_n = int(w.n.iloc[0]) if len(w) else None
            wall_ev = (w.status.iloc[0] + " (" + w.file.iloc[0] + ")") if len(w) else "none observed"
            cands = {}
            if b == "uno":
                mw = C.raw_selected(2, b, c, "memory_wall.csv")
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
def offload_crossover():
    """Local (Phase 2) vs offload (Phase 3) on the selected sessions: the band and the crossover brackets live in analysis/phase4/offload_band.py.
    Returns (m, X): m = one row per (board, circuit, n) with both a local and an offload point; X = one row per (board, circuit) with the two brackets."""
    import offload_band as OB
    m, allp, rng = OB.band_table()
    m = m.rename(columns={"median_us_local": "median_us_local"})
    m["median_us_offload"] = m.e2e_us
    m["reps_local"] = m.reps
    m["reps_offload"] = m.requests
    m["offload_over_local"] = m.e2e_us / m.median_us
    m["median_us_local"] = m.median_us
    m.to_csv(os.path.join(C.PROC, "offload_band.csv"), index=False)
    m[["board", "circuit", "n", "median_us_local", "median_us_offload", "reps_local", "reps_offload", "offload_over_local"]].to_csv(
        os.path.join(C.PROC, "offload_vs_local.csv"), index=False)
    allp.to_csv(os.path.join(OB.DER, "phase3_decomposition.csv"), index=False)
    rng.to_csv(os.path.join(OB.DER, "phase3_pc_sim_range.csv"), index=False)
    X = OB.crossover_table(m)
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
