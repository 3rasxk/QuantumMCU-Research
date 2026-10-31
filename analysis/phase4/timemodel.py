"""Phase 4 time model with held-out validation (items 3, 4 and 5 of the fixes).

Models (all fitted per board on small n only, relative-error least squares):
  M1   t = c x W(n)                       one constant per board, W = gate calls x 2^n loop iterations     (1 parameter)
  M1c  t = c_circuit x W(n)               one constant per (board, circuit)                                (1 per series)
  M2   t = sum_k c_k N_k 2^n + a G        per-gate-kind costs (H, CNOT, CPHASE) + per-call term, NNLS     (4 parameters)
  M2g  M2 fitted without any grover point

Honest status of the choice of M2 (also written in docs/phase4_report.md): M2 has the functional form of "Model B" of
analysis/phase2_gate_cost_fit.py / docs/report/paper_outline.md, whose out-of-sample errors on grover were already known before the Phase 4
analysis was started. M2 was written down in the first Phase 4 commit (bf9b692) before this analysis was first run, but it was NOT blind with
respect to grover. What was fixed before any test point was scored: the split (held-out = largest N_TEST = 3 n) and FLOOR_US. What was NOT: the weak
rule (reps < 30; the base analysis had used 10), the hash classes and the identifiability rule were all added in the fix round, after the
first test scores were known. Their effect is small (M2 overall 18.0 -> 18.7 % when the weak points are dropped). The sensitivity to
N_TEST in {2, 3, 4} is reported in full and N_TEST = 3 stays primary.

A point is
  weak        reps < 30 (analysis/common/weak.py): not fitted, not in the primary test MAPE (secondary number only)
  hash-flagged its firmware hash is in a timing class other than A (analysis/phase4/firmware_hash_classes.csv): not fitted; reported separately
Identifiability: a model fit is identifiable if n_fit >= p + 2, the design matrix has full column rank, its column-scaled condition number
is <= COND_MAX, and no NNLS coefficient is <= 1e-12 (the zero boundary). COND_MAX = 1e4 never binds (the largest condition number is about 5).
WARNING: the boundary condition is a knife edge. A coefficient of 0.0013 passes and 0.0000 fails, and the verdict for a board changes with
the held-out size (see time_sensitivity.csv, column identifiable_boards). Read 'identifiable' as 'the NNLS solution has no exact zero', not as
'the parameters are physically determined'.
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy.optimize import nnls

import p4common as C
import gatecount as G

sys.path.insert(0, os.path.join(C.ROOT, "analysis"))
from common import weak  # noqa: E402

COND_MAX = 1e4
CLASSES = os.path.join(C.HERE, "firmware_hash_classes.csv")
MODELS = ["M1", "M1c", "M2", "M2g"]


# ---------------------------------------------------------------------------------------------- data
def hash_table():
    """firmware hash and timing class of every Phase 2 point (board, circuit, n)"""
    import audit
    pts = pd.concat([audit.audit_selected(2, b, c) for b in C.BOARDS for c in C.CIRCUITS], ignore_index=True)
    pts = pts[pts.ok_rows > 0][["board", "circuit", "n", "fw_hashes", "n_hashes"]]
    assert (pts.n_hashes == 1).all(), "a point with several hashes"
    cls = pd.read_csv(CLASSES)
    cls = cls[cls.phase == 2].set_index(["board", "hash"]).timing_class
    pts["hash"] = pts.fw_hashes
    pts["timing_class"] = [cls.get((b, h)) for b, h in zip(pts.board, pts.hash)]
    missing = pts[pts.timing_class.isna()]
    assert missing.empty, f"hash without a class: {missing[['board', 'hash']].drop_duplicates().to_dict('records')}"
    return pts[["board", "circuit", "n", "hash", "timing_class"]]


def load_points():
    loc = C.load_local().merge(hash_table(), on=["board", "circuit", "n"], how="left")
    loc["weak"] = [weak.is_weak(r) for r in loc.reps]
    loc["hash_flagged"] = loc.timing_class != "A"
    loc["work"] = [G.work(r.circuit, int(r.n)) for r in loc.itertuples()]
    loc["gates"] = [G.total_gates(r.circuit, int(r.n)) for r in loc.itertuples()]
    X = []
    for r in loc.itertuples():
        nh, nc, np_ = G.counts(r.circuit, int(r.n))
        X.append([nh * 2 ** r.n, nc * 2 ** r.n, np_ * 2 ** r.n, nh + nc + np_])
    loc[["x_h", "x_cn", "x_cp", "x_g"]] = np.array(X, dtype=float)
    return loc


def split(loc, n_test=C.N_TEST, floor=C.FLOOR_US):
    """role per point: test (largest n_test n of the series), fit, or why it is not used. The test set is chosen BEFORE the weak and
    hash rules, so a weak or flagged test point is reported, not silently replaced by a different n."""
    loc = loc.copy()
    loc["role"] = "dropped_below_floor"
    for (b, c), g in loc.groupby(["board", "circuit"]):
        test = set(sorted(g.n)[-n_test:])
        for i, r in g.iterrows():
            if r.n in test:
                loc.at[i, "role"] = "test"
            elif r.weak:
                loc.at[i, "role"] = "not_fitted_weak"
            elif r.hash_flagged:
                loc.at[i, "role"] = "not_fitted_hash"
            elif r.median_us >= floor:
                loc.at[i, "role"] = "fit"
    return loc


# ---------------------------------------------------------------------------------------------- fitting
def assert_homogeneous(fit, allow_mixed=False):
    """a fit must not mix firmware versions with timing-relevant differences (item 4d): fails if the fit rows span more than one timing class"""
    classes = sorted(set(fit.timing_class))
    if len(classes) > 1 and not allow_mixed:
        raise ValueError(f"fit mixes timing classes {classes} (boards: {sorted(set(fit.board))}); pass allow_mixed=True to override explicitly")
    return classes


def fit_m1(d):
    """t = c W, relative-error least squares: c = sum(w/t) / sum((w/t)^2)"""
    w = d.work.to_numpy() / d.median_us.to_numpy()
    return float(w.sum() / (w ** 2).sum())


COLS = ["x_h", "x_cn", "x_cp", "x_g"]


def fit_m2(d):
    A = d[COLS].to_numpy() / d.median_us.to_numpy()[:, None]
    coef, _ = nnls(A, np.ones(len(d)))
    return coef


def design_diagnostics(d, params, coef=None):
    """-> dict(n_fit, params, rank, cond, boundary, identifiable) for a design matrix with the given parameter columns"""
    cols = COLS if params == 4 else ["work"]
    A = d[cols].to_numpy(float) / d.median_us.to_numpy(float)[:, None]
    n = len(d)
    if n == 0 or not np.isfinite(A).all():
        return dict(n_fit=n, params=params, rank=0, cond=float("inf"), boundary=False, identifiable=False)
    norms = np.linalg.norm(A, axis=0)
    keep = norms > 0
    An = A[:, keep] / norms[keep]
    sv = np.linalg.svd(An, compute_uv=False)
    rank = int((sv > sv.max() * 1e-10).sum()) if len(sv) else 0
    rank_full = rank if keep.all() else min(rank, int(keep.sum()))
    cond = float(sv.max() / sv.min()) if len(sv) and sv.min() > 0 else float("inf")
    if not keep.all():
        cond = float("inf")          # an all-zero column: that parameter is not constrained at all
    boundary = bool(coef is not None and np.any(np.asarray(coef) <= 1e-12))
    ident = bool(n >= params + 2 and rank_full == params and cond <= COND_MAX and not boundary)
    return dict(n_fit=n, params=params, rank=rank_full, cond=cond, boundary=boundary, identifiable=ident)


def mape_rows(g, col):
    e = (g[col] - g.median_us) / g.median_us * 100
    return e.abs().mean(), e.abs().max(), e.mean()


def time_model(n_test=C.N_TEST, floor=C.FLOOR_US, write=True, loc=None, allow_mixed=False):
    loc = split(load_points() if loc is None else loc, n_test, floor)
    preds, fit_rows, ident_rows = [], [], []
    for b in C.BOARDS:
        lb = loc[loc.board == b].copy()
        fit = lb[lb.role == "fit"]
        assert_homogeneous(fit, allow_mixed)
        c1 = fit_m1(fit)
        coef = fit_m2(fit)
        coef_g = fit_m2(fit[fit.circuit != "grover"])
        lb["pred_M1"] = c1 * lb.work
        lb["pred_M2"] = lb[COLS].to_numpy() @ coef
        lb["pred_M2g"] = lb[COLS].to_numpy() @ coef_g
        lb["pred_M1c"] = np.nan
        c1c = {}
        for c in C.CIRCUITS:
            fc = fit[fit.circuit == c]
            if len(fc) >= 2:
                c1c[c] = fit_m1(fc)
                m = lb.circuit == c
                lb.loc[m, "pred_M1c"] = c1c[c] * lb.loc[m, "work"]
        fit_rows.append(dict(board=b, model="M1", c=c1, n_fit=len(fit)))
        fit_rows += [dict(board=b, model="M1c", circuit=c, c=v, n_fit=int((fit.circuit == c).sum())) for c, v in c1c.items()]
        fit_rows.append(dict(board=b, model="M2", c_H=coef[0], c_CNOT=coef[1], c_CPHASE=coef[2], a_call=coef[3], n_fit=len(fit)))
        fit_rows.append(dict(board=b, model="M2g", c_H=coef_g[0], c_CNOT=coef_g[1], c_CPHASE=coef_g[2], a_call=coef_g[3],
                             n_fit=int((fit.circuit != "grover").sum())))
        d1 = design_diagnostics(fit, 1)
        d2 = design_diagnostics(fit, 4, coef)
        for c in C.CIRCUITS:
            fc = fit[fit.circuit == c]
            s1 = design_diagnostics(fc, 1)
            s2 = design_diagnostics(fc, 4, None)          # M2 fitted to this series alone
            ident_rows.append(dict(
                board=b, circuit=c, fit_points=len(fc), fit_n=" ".join(map(str, fc.n)),
                M1_params=1, M1_identifiable=bool(len(fc) >= 3), M1_c=c1c.get(c, np.nan),
                M2_params_shared_per_board=4, M2_board_fit_points=d2["n_fit"], M2_board_rank=d2["rank"], M2_board_cond=d2["cond"],
                M2_board_boundary_coef=d2["boundary"], M2_board_identifiable=d2["identifiable"],
                M2_series_alone_rank=s2["rank"], M2_series_alone_identifiable=s2["identifiable"],
                M2_c_H=coef[0], M2_c_CNOT=coef[1], M2_c_CPHASE=coef[2], M2_a_call=coef[3],
                M2_min_over_max_kernel_coef=float(min(coef[:3]) / max(coef[:3])) if max(coef[:3]) > 0 else float("nan")))
        preds.append(lb)
    P = pd.concat(preds)
    ident = pd.DataFrame(ident_rows)
    P = P.merge(ident[["board", "circuit", "M1_identifiable", "M2_board_identifiable"]], on=["board", "circuit"], how="left")
    P["pred_M1"] = P["pred_M1"].astype(float)
    if write:
        P.to_csv(os.path.join(C.PROC, "time_predictions.csv"), index=False)
        pd.DataFrame(fit_rows).to_csv(os.path.join(C.PROC, "time_fit.csv"), index=False)
        ident.to_csv(os.path.join(C.PROC, "time_identifiability.csv"), index=False)
    return P, ident


# ---------------------------------------------------------------------------------------------- scoring
def identifiable_mask(P, model):
    if model in ("M1", "M1c"):
        return P.M1_identifiable.fillna(False).astype(bool)
    return P.M2_board_identifiable.fillna(False).astype(bool)


def score(P, model, board=None, scope="all", include_weak=False, clean=False):
    """point-weighted MAPE over held-out points. scope: all | identifiable | no_grover. include_weak: add weak test points (secondary).
    clean: drop hash-flagged test points."""
    col = "pred_" + model
    g = P[(P.role == "test") & P[col].notna()]
    if board:
        g = g[g.board == board]
    if not include_weak:
        g = g[~g.weak]
    if clean:
        g = g[~g.hash_flagged]
    if scope == "identifiable":
        g = g[identifiable_mask(g, model)]
    elif scope == "no_grover":
        g = g[g.circuit != "grover"]
    if g.empty:
        return dict(n=0, mape=float("nan"), max_abs=float("nan"))
    m, mx, _ = mape_rows(g, col)
    return dict(n=len(g), mape=float(m), max_abs=float(mx))


def score_table(P):
    rows = []
    for model in MODELS:
        for scope in ("all", "identifiable", "no_grover"):
            for tag, kw in (("primary (non-weak)", {}), ("secondary (weak included)", dict(include_weak=True)),
                            ("clean (non-weak, hash class A)", dict(clean=True))):
                for b in C.BOARDS + [None]:
                    r = score(P, model, b, scope, **kw)
                    rows.append(dict(model=model, scope=scope, test_set=tag, board=b or "all", n_points=r["n"], mape_pct=r["mape"], max_abs_pct=r["max_abs"]))
    return pd.DataFrame(rows)


def validation_table(P):
    """per (board, circuit): test points, MAPE with weak / flagged points marked"""
    rows = []
    for model in MODELS:
        col = "pred_" + model
        for (b, c), g in P.groupby(["board", "circuit"]):
            t = g[(g.role == "test") & g[col].notna()]
            if t.empty:
                continue
            for tag, tt in (("primary", t[~t.weak]), ("with_weak", t), ("clean", t[(~t.weak) & (~t.hash_flagged)])):
                if tt.empty:
                    rows.append(dict(model=model, board=b, circuit=c, test_set=tag, n_points=0, n_list="", mape_pct=np.nan, max_abs_pct=np.nan, mean_signed_pct=np.nan))
                    continue
                m, mx, ms = mape_rows(tt, col)
                rows.append(dict(model=model, board=b, circuit=c, test_set=tag, n_points=len(tt), n_list=" ".join(map(str, tt.n)),
                                 mape_pct=float(m), max_abs_pct=float(mx), mean_signed_pct=float(ms)))
    return pd.DataFrame(rows)


def time_sensitivity():
    """pre-registered: held-out = largest 2, 3, 4 n. N_TEST = 3 is primary."""
    rows = []
    for nt in (2, 3, 4):
        P, ident_nt = time_model(nt, write=False)
        idb = ",".join(sorted(ident_nt[ident_nt.M2_board_identifiable].board.unique()))
        for model in MODELS:
            for scope in ("all", "identifiable", "no_grover"):
                r = score(P, model, None, scope)
                rw = score(P, model, None, scope, include_weak=True)
                rc = score(P, model, None, scope, clean=True)
                rows.append(dict(n_test=nt, model=model, scope=scope, identifiable_boards=idb, n_primary=r["n"], mape_primary=r["mape"], n_with_weak=rw["n"],
                                 mape_with_weak=rw["mape"], n_clean=rc["n"], mape_clean=rc["mape"]))
    S = pd.DataFrame(rows)
    S.to_csv(os.path.join(C.PROC, "time_sensitivity.csv"), index=False)
    return S


def run_all():
    P, ident = time_model()
    S = score_table(P)
    S.to_csv(os.path.join(C.PROC, "time_scores.csv"), index=False)
    V = validation_table(P)
    V.to_csv(os.path.join(C.PROC, "time_validation.csv"), index=False)
    sens = time_sensitivity()
    return P, ident, S, V, sens


if __name__ == "__main__":
    pd.set_option("display.width", 250, "display.max_columns", 40)
    P, ident, S, V, sens = run_all()
    print(ident.round(3).to_string())
    print(S[(S.board == "all")].round(1).to_string())
    print(sens.round(1).to_string())
