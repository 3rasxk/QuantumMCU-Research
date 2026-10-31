"""Offload latency decomposition and crossover bands (read-only on data/raw through analysis/common/sessions.py).

Phase 3 point (board, circuit, n, session): e2e = wire + residual + pc_sim (medians of the point; the split is bookkeeping, medians do not add exactly).
  wire      = frame bytes per request x 10 bit / baud  (bytes_transferred / requests, points.csv)
  pc_sim    = pc_sim_s_median  (Aer build + run + sample on the PC, logged per point; it depends on circuit and n, NOT on the board, but on the PC state of the session)
  residual  = e2e - pc_sim - wire  (board compute, USB-serial latency, host scheduling)
PC simulation time varies about 2x between sessions on the same PC (docs/phase4_report.md), so a single offload line would hide that. The band:
  pc_sim_min / pc_sim_max of a circuit x n = observed min / max of pc_sim over EVERY Phase 3 session on EVERY board, replaced sessions included, in-scope n only;
  offload band of (board, circuit, n) = wire + residual(board, selected session) + [pc_sim_min, pc_sim_max].
Crossover per board x circuit, against the Phase 2 local median of the same n (both selected sessions, in-scope n >= 2, Phase 3 up to the board's Phase 2 wall):
  n_fast uses the fast bound, n_slow the slow bound. Each is a BRACKET (n_lo, n_hi) of two measured n: the last n where local is not slower than offload and the
  first n from which offload stays faster at every larger measured n. No extrapolation and no interpolated single value.
  "no crossover up to the wall": local stays faster at the largest measured n under that bound. "offload faster at the smallest measured n": no n_lo.
Labels: within noise = the local IQR and the offload IQR (the measured IQR shifted to the bound) overlap at n_lo or n_hi; weak = a point of the bracket has < 30 reps or requests.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common import sessions as SES  # noqa: E402
from common import weak as W  # noqa: E402
import p4common as C  # noqa: E402

DER = os.path.join(C.ROOT, "data", "derived")


def p3_all_sessions():
    """every in-scope Phase 3 point of every session of every board: board, circuit, n, session, requests, e2e (median, q1, q3), pc_sim, wire, residual (all us)"""
    rows = []
    for b in C.BOARDS:
        for c in C.CIRCUITS:
            for s in SES.buckets(3, b, c):
                d = SES.bucket_dir(3, b, c, s)
                rawp, ptp = os.path.join(d, "raw.csv"), os.path.join(d, "points.csv")
                if not (os.path.exists(rawp) and os.path.exists(ptp)):
                    continue
                raw, pts = pd.read_csv(rawp), pd.read_csv(ptp)
                pts = pts[pts.status == "ok"]
                raw = raw[(raw.timed_out == 0) & (raw.crc_error == 0)]
                for n, g in raw.groupby("n"):
                    n = int(n)
                    if not SES.in_scope(3, b, c, n) or not (pts.n == n).any():
                        continue
                    p = pts[pts.n == n].iloc[-1]                   # several ok records of one n inside a bucket: the last one (its pc_sim, bytes)
                    x = g.e2e_latency_us.to_numpy(float)
                    wire = float(p.bytes_transferred) / len(g) * 10.0 / float(p.baud) * 1e6
                    sim = float(p.pc_sim_s_median) * 1e6
                    med = float(np.median(x))
                    rows.append(dict(board=b, circuit=c, n=n, session=s, requests=len(x), e2e_us=med, e2e_q1_us=float(np.percentile(x, 25)),
                                     e2e_q3_us=float(np.percentile(x, 75)), pc_sim_us=sim, wire_us=wire, residual_us=med - sim - wire,
                                     selected=SES.is_selected(3, b, c, n, s)))
    return pd.DataFrame(rows).sort_values(["board", "circuit", "n", "session"]).reset_index(drop=True)


def pc_sim_range(allp):
    """observed pc_sim min / max per circuit x n over every session of every board (replaced sessions included)"""
    g = allp.groupby(["circuit", "n"]).pc_sim_us
    r = pd.DataFrame({"pc_sim_min_us": g.min(), "pc_sim_max_us": g.max(), "pc_sim_sessions": g.count()}).reset_index()
    # weak sources of the extremes: a pooled extreme taken from a point with < WEAK_MIN requests is flagged
    lo = allp.loc[allp.groupby(["circuit", "n"]).pc_sim_us.idxmin()][["circuit", "n", "requests"]].rename(columns={"requests": "min_from_requests"})
    hi = allp.loc[allp.groupby(["circuit", "n"]).pc_sim_us.idxmax()][["circuit", "n", "requests"]].rename(columns={"requests": "max_from_requests"})
    return r.merge(lo, on=["circuit", "n"]).merge(hi, on=["circuit", "n"])


def band_table():
    """per (board, circuit, n) with both a Phase 2 and a selected Phase 3 point: local statistics, the decomposition of the selected offload point and the band"""
    allp = p3_all_sessions()
    rng = pc_sim_range(allp)
    loc = C.load_local()
    sel = allp[allp.selected]
    m = loc.merge(sel, on=["board", "circuit", "n"], suffixes=("_local", "_offload"))
    m = m.merge(rng, on=["circuit", "n"])
    m["fast_us"] = m.wire_us + m.residual_us + m.pc_sim_min_us
    m["slow_us"] = m.wire_us + m.residual_us + m.pc_sim_max_us
    m["fast_q1_us"] = m.e2e_q1_us + (m.pc_sim_min_us - m.pc_sim_us)
    m["fast_q3_us"] = m.e2e_q3_us + (m.pc_sim_min_us - m.pc_sim_us)
    m["slow_q1_us"] = m.e2e_q1_us + (m.pc_sim_max_us - m.pc_sim_us)
    m["slow_q3_us"] = m.e2e_q3_us + (m.pc_sim_max_us - m.pc_sim_us)
    m["weak_point"] = (m.reps < W.WEAK_MIN) | (m.requests < W.WEAK_MIN)
    m["pc_sim_extreme_weak"] = (m.min_from_requests < W.WEAK_MIN) | (m.max_from_requests < W.WEAK_MIN)
    return m.sort_values(["board", "circuit", "n"]).reset_index(drop=True), allp, rng


def bracket(g, bound):
    """-> (n_lo, n_hi, kind) for one bound ('fast' or 'slow') of a (board, circuit) group sorted by n"""
    off = g[f"{bound}_us"].to_numpy()
    loc = g.median_us.to_numpy()
    ns = g.n.to_numpy()
    faster = off < loc
    first = None
    for i in range(len(ns)):
        if faster[i:].all():            # offload faster here and at every larger measured n
            first = i
            break
    if first is None:
        return None, None, "none"
    if first == 0:
        return None, int(ns[0]), "below"
    return int(ns[first - 1]), int(ns[first]), "bracket"


def crossover_table(m=None):
    m = m if m is not None else band_table()[0]
    rows = []
    for (b, c), g in m.groupby(["board", "circuit"]):
        g = g.sort_values("n").reset_index(drop=True)
        r = dict(board=b, circuit=c, n_first=int(g.n.min()), n_last=int(g.n.max()), n_points=len(g))
        for bound in ("fast", "slow"):
            lo, hi, kind = bracket(g, bound)
            r[f"n_{bound}_lo"], r[f"n_{bound}_hi"], r[f"{bound}_kind"] = lo, hi, kind
            idx = [i for i, n in enumerate(g.n) if n in (lo, hi)]
            pts = g.iloc[idx] if idx else g.iloc[[len(g) - 1]]
            lab = []
            if kind == "none":
                lab.append("no crossover up to the largest measured n")
            elif kind == "below":
                lab.append("offload faster at the smallest measured n")
            ov = ((pts.q1_us <= pts[f"{bound}_q3_us"]) & (pts[f"{bound}_q1_us"] <= pts.q3_us)).any()   # local IQR vs shifted offload IQR at the bracket ends
            if ov:
                lab.append("within noise" if kind == "bracket" else "within noise at the largest measured n" if kind == "none" else "within noise at the smallest measured n")
            weak_end = bool(pts.weak_point.any()) or bool(pts.pc_sim_extreme_weak.any())
            beyond = g[g.n > (hi if hi is not None else g.n.max())] if kind != "none" else g.iloc[0:0]
            if weak_end:
                lab.append("weak")
            elif bool(beyond.weak_point.any()):
                lab.append("weak point beyond the bracket")
            r[f"{bound}_labels"] = "; ".join(lab)
        rows.append(r)
    return pd.DataFrame(rows)


def main():
    m, allp, rng = band_table()
    os.makedirs(C.PROC, exist_ok=True)
    m.to_csv(os.path.join(C.PROC, "offload_band.csv"), index=False)
    allp.to_csv(os.path.join(DER, "phase3_decomposition.csv"), index=False)
    rng.to_csv(os.path.join(DER, "phase3_pc_sim_range.csv"), index=False)
    X = crossover_table(m)
    X.to_csv(os.path.join(C.PROC, "offload_crossover.csv"), index=False)
    print(X.to_string())
    return m, X


if __name__ == "__main__":
    main()
