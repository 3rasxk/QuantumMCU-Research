"""Phase 4 Step 1: memory-wall model, time model with held-out validation, micros()-vs-counter agreement.

Writes data/processed/phase4/{memory_model,time_fit,time_validation,time_predictions,counter_agreement,offload}.csv.
Every number in docs/phase4_report.md comes from these files.
"""
import os

import numpy as np
import pandas as pd
from scipy.optimize import nnls

import common as C
import gatecount as G

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


# ----------------------------------------------------------------------------------------------
# Time model
# ----------------------------------------------------------------------------------------------
def design(df):
    """Rows of per-kind work (gate calls x 2^n) and gate-call count for each point."""
    X = []
    for _, r in df.iterrows():
        nh, nc, np_ = G.counts(r.circuit, int(r.n))
        X.append([nh * 2 ** r.n, nc * 2 ** r.n, np_ * 2 ** r.n, nh + nc + np_])
    return np.array(X, dtype=float)


def split(loc, n_test=C.N_TEST, floor=C.FLOOR_US):
    """Per (board, circuit): the largest n_test ok n are test; all other points with median >= floor are fit."""
    loc = loc.copy()
    loc["role"] = "dropped_below_floor"
    for (b, c), g in loc.groupby(["board", "circuit"]):
        ns = sorted(g.n)
        test = set(ns[-n_test:])
        for i, r in g.iterrows():
            if r.n in test:
                loc.at[i, "role"] = "test"
            elif r.median_us >= floor:
                loc.at[i, "role"] = "fit"
    return loc


def fit_m1_pooled(d):
    """t = c * W, W = gate calls x 2^n. Relative-error least squares: c = sum(w/t) / sum((w/t)^2)."""
    w = d.work.to_numpy() / d.median_us.to_numpy()
    return float(w.sum() / (w ** 2).sum())


def fit_m2(d):
    """t = sum_k c_k N_k 2^n + a G   (k = H, CNOT, CPHASE), non-negative, relative-error NNLS."""
    A = d[["x_h", "x_cn", "x_cp", "x_g"]].to_numpy() / d.median_us.to_numpy()[:, None]
    coef, _ = nnls(A, np.ones(len(d)))
    return coef


def time_model(n_test=C.N_TEST, floor=C.FLOOR_US, write=True):
    loc = split(C.load_local(), n_test, floor)
    loc["work"] = [G.work(r.circuit, int(r.n)) for _, r in loc.iterrows()]
    loc["gates"] = [G.total_gates(r.circuit, int(r.n)) for _, r in loc.iterrows()]
    X = design(loc)
    loc[["x_h", "x_cn", "x_cp", "x_g"]] = X
    fit_rows, preds = [], []
    for b in C.BOARDS:
        lb = loc[loc.board == b].copy()
        fit = lb[lb.role == "fit"]
        c1 = fit_m1_pooled(fit)
        coef = fit_m2(fit)
        lb["pred_M1"] = c1 * lb.work
        lb["pred_M2"] = lb[["x_h", "x_cn", "x_cp", "x_g"]].to_numpy() @ coef
        # per-circuit c (M1c)
        lb["pred_M1c"] = np.nan
        c1c = {}
        for c in C.CIRCUITS:
            fc = fit[fit.circuit == c]
            if len(fc) >= 2:
                c1c[c] = fit_m1_pooled(fc)
                m = lb.circuit == c
                lb.loc[m, "pred_M1c"] = c1c[c] * lb.loc[m, "work"]
        # M2 with grover held out of the fit (circuit-level generalisation)
        fit_ng = fit[fit.circuit != "grover"]
        coef_ng = fit_m2(fit_ng)
        lb["pred_M2_nogrover_fit"] = lb[["x_h", "x_cn", "x_cp", "x_g"]].to_numpy() @ coef_ng
        fit_rows.append(dict(board=b, model="M1_pooled", c_us_per_iter=c1, n_fit=len(fit)))
        for c, v in c1c.items():
            fit_rows.append(dict(board=b, model="M1_per_circuit", circuit=c, c_us_per_iter=v,
                                 n_fit=int((fit.circuit == c).sum())))
        fit_rows.append(dict(board=b, model="M2_pooled", c_H_us=coef[0] * 1e0, c_CNOT_us=coef[1], c_CPHASE_us=coef[2],
                             a_call_us=coef[3], n_fit=len(fit)))
        fit_rows.append(dict(board=b, model="M2_grover_held_out", c_H_us=coef_ng[0], c_CNOT_us=coef_ng[1],
                             c_CPHASE_us=coef_ng[2], a_call_us=coef_ng[3], n_fit=len(fit_ng)))
        preds.append(lb)
    P = pd.concat(preds)
    if write:
        P.to_csv(os.path.join(C.PROC, "time_predictions.csv"), index=False)
        pd.DataFrame(fit_rows).to_csv(os.path.join(C.PROC, "time_fit.csv"), index=False)

    val = []
    for model in ["M1", "M1c", "M2", "M2_nogrover_fit"]:
        col = "pred_" + model
        for (b, c), g in P.groupby(["board", "circuit"]):
            for part, gg in [("test", g[g.role == "test"]), ("fit", g[g.role == "fit"])]:
                gg = gg[gg[col].notna()]
                if len(gg) == 0:
                    continue
                e = (gg[col] - gg.median_us) / gg.median_us * 100
                val.append(dict(model=model, board=b, circuit=c, part=part, n_points=len(gg),
                                n_list=" ".join(map(str, gg.n)), mape_pct=float(e.abs().mean()),
                                max_abs_pct=float(e.abs().max()), mean_signed_pct=float(e.mean()),
                                min_reps=int(gg.reps.min()),
                                weak=bool(len(gg) < 3 or gg.reps.min() < C.SMALL_REPS)))
    V = pd.DataFrame(val)
    if not write:
        return P, V
    V.to_csv(os.path.join(C.PROC, "time_validation.csv"), index=False)
    # per-board pooled over circuits (test points only)
    agg = []
    for model in ["M1", "M1c", "M2", "M2_nogrover_fit"]:
        col = "pred_" + model
        for b in C.BOARDS + [None]:
            g = P[(P.role == "test") & P[col].notna()]
            if b:
                g = g[g.board == b]
            e = (g[col] - g.median_us) / g.median_us * 100
            agg.append(dict(model=model, board=b or "all", n_test=len(g), mape_pct=float(e.abs().mean()),
                            max_abs_pct=float(e.abs().max())))
    pd.DataFrame(agg).to_csv(os.path.join(C.PROC, "time_validation_by_board.csv"), index=False)
    return P, V


def time_sensitivity():
    """Robustness only: the headline split (N_TEST=3, floor 100 us) was fixed before any test point was scored.
    This table shows how the test MAPE moves if that choice had been different; it is NOT used to choose a model."""
    rows = []
    for nt in (2, 3, 4):
        for fl in (50.0, 100.0, 200.0):
            P, V = time_model(nt, fl, write=False)
            for model in ["M1", "M1c", "M2", "M2_nogrover_fit"]:
                t = V[(V.model == model) & (V.part == "test")]
                for b in C.BOARDS + [None]:
                    tb = t[t.board == b] if b else t
                    # point-weighted mean of per-series MAPE
                    mape = float((tb.mape_pct * tb.n_points).sum() / tb.n_points.sum())
                    rows.append(dict(n_test=nt, floor_us=fl, model=model, board=b or "all",
                                     n_test_points=int(tb.n_points.sum()), mape_pct=mape))
    S = pd.DataFrame(rows)
    S.to_csv(os.path.join(C.PROC, "time_sensitivity.csv"), index=False)
    return S


# ----------------------------------------------------------------------------------------------
# micros() vs counter (Phase 2 only; Phase 3 counter data are excluded by policy)
# ----------------------------------------------------------------------------------------------
def counter_agreement():
    rows = []
    for b in C.BOARDS:
        for c in C.CIRCUITS:
            base = C.series_dir(2, b, c)
            pr = pd.read_csv(os.path.join(base, "ref", "ref_compare_points.csv"))
            rc = pd.read_csv(os.path.join(base, "ref", "ref_compare.csv"))
            for _, p in pr.iterrows():
                g = rc[rc.n == p.n]
                g = g[(g.counter_us > 0) & (g.micros_us > 0)]
                if len(g) == 0:
                    continue
                ratio = g.micros_us / g.counter_us
                rows.append(dict(board=b, circuit=c, n=int(p.n), n_pairs=len(g), ref_status=p.ref_status,
                                 median_micros_us=float(g.micros_us.median()),
                                 median_counter_us=float(g.counter_us.median()),
                                 median_ratio=float(ratio.median()),
                                 ratio_q1=float(np.percentile(ratio, 25)), ratio_q3=float(np.percentile(ratio, 75))))
    D = pd.DataFrame(rows)
    D.to_csv(os.path.join(C.PROC, "counter_agreement.csv"), index=False)
    return D


def counter_summary(D):
    out = []
    for b in C.BOARDS:
        for stat in ["ok", "not_ok"]:
            for sel_name, sel in [("all", lambda g: g), ("median>=100us", lambda g: g[g.median_micros_us >= C.FLOOR_US])]:
                g = D[D.board == b]
                g = g[(g.ref_status == "ok")] if stat == "ok" else g[g.ref_status != "ok"]
                g = g[g.n_pairs >= 10]
                g = sel(g)
                if len(g) == 0:
                    continue
                out.append(dict(board=b, counter_status=stat, subset=sel_name, n_points=len(g),
                                median_of_median_ratio=float(g.median_ratio.median()),
                                ratio_min=float(g.median_ratio.min()), ratio_max=float(g.median_ratio.max()),
                                iqr_of_point_medians=float(np.percentile(g.median_ratio, 75) - np.percentile(g.median_ratio, 25))))
    S = pd.DataFrame(out)
    S.to_csv(os.path.join(C.PROC, "counter_summary.csv"), index=False)
    return S


# ----------------------------------------------------------------------------------------------
# Offload crossover
# ----------------------------------------------------------------------------------------------
def offload_crossover():
    loc, off = C.load_local(), C.load_offload()
    m = loc.merge(off, on=["board", "circuit", "n"], suffixes=("_local", "_offload"))
    m["offload_over_local"] = m.median_us_offload / m.median_us_local
    m.to_csv(os.path.join(C.PROC, "offload_vs_local.csv"), index=False)
    rows = []
    for (b, c), g in m.groupby(["board", "circuit"]):
        g = g.sort_values("n")
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
                         ratio_at_n_local_max=float(g.offload_over_local.iloc[-1]),
                         min_offload_req=int(g.reps_offload.min())))
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
