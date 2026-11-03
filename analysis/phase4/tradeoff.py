"""Equations and shared helpers of the local-versus-offload trade-off (added after the data were seen; no new data, read-only on data/raw).

One place for what the figures, the decision map, Table III and the tests share:

  (1) state size          M(n) = AMP_BYTES * 2^n  (complex float32, 8 B)           memory_bytes()
  (2) memory wall         n_max = floor(log2(B / AMP_BYTES))                         n_max()
  (6) wire time           T_wire = BITS_PER_BYTE * L_frame / baud                    t_wire_us()      (used by offload_band.py)
  (8) crossover bracket   offload_band.bracket (unchanged); cells(): which side is faster under each PC bound, per (board, circuit, n), from the crossover table
      predicted crossover bracket from a local model plus the offload equation      predicted_table()
(equation numbers as in docs/phase4_report.md section 13 and the paper)

The crossover bracket rule itself is offload_band.bracket (unchanged). Local statistics come from analysis/common/sessions.py through p4common /
offload_band; nothing here reads data/raw directly.
"""
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import p4common as C  # noqa: E402
import offload_band as OB  # noqa: E402
from common import sessions as SES  # noqa: E402
from common import weak as W  # noqa: E402

AMP_BYTES = 8            # complex float32: two 4-byte floats (firmware/common/qsim.hpp)
BITS_PER_BYTE = OB.BITS_PER_BYTE
GRID_N = list(range(2, 15))          # decision-map columns: n = 2 .. 14 (the largest wall n of the three boards)
SMALL_SIM_US = 20000.0   # offload points with a PC simulation below this give the board-and-link residual (same cut as the report)

LOCAL, OFFLOAD, DEPENDS, NOISE, NORUN, NOMEAS = "local", "offload", "depends", "noise", "norun", "nomeas"
CELL_LABEL = {LOCAL: "local faster (both PC bounds)", OFFLOAD: "offload faster (both PC bounds)", DEPENDS: "depends on PC speed (bounds disagree)",
              NOISE: "within noise", NORUN: "not runnable on board (beyond wall / time-limited)", NOMEAS: "not measured"}


# ------------------------------------------------------------------------------------------------ equations
def memory_bytes(n):
    """(E1) bytes of the state vector of n qubits"""
    return AMP_BYTES * 2 ** n


def n_max(B_bytes):
    """(E2) largest n whose state fits: AMP_BYTES * 2^n <= B -> floor(log2(B / AMP_BYTES)); B = bytes available for the state as model.py reads them
    (Uno: 2048 B minus the compiler-reported static use; ESP8266: free heap read after the allocation at n = 2; ESP32: largest free block)"""
    return int(math.floor(math.log2(B_bytes / AMP_BYTES)))


t_wire_us = OB.t_wire_us      # (E6) defined next to the pipeline that uses it (offload_band.py)


# ------------------------------------------------------------------------------------------------ band check
def band_check(m):
    """per circuit: how much do the offload bands of the three boards differ, relative to the band height?
    at every n with >= 2 boards: spread = max over the two bounds of (max over boards - min over boards); height = mean over boards of (slow - fast).
    -> DataFrame circuit, n, spread_us, height_us, ratio; plus per circuit the maximum ratio"""
    rows = []
    for (c, n), g in m.groupby(["circuit", "n"]):
        if len(g) < 2:
            continue
        spread = max(g.fast_us.max() - g.fast_us.min(), g.slow_us.max() - g.slow_us.min())
        height = float((g.slow_us - g.fast_us).mean())
        rows.append(dict(circuit=c, n=int(n), boards=len(g), spread_us=float(spread), height_us=height, ratio=float(spread / height) if height > 0 else float("inf")))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ decision-map cells
def side_flags(X_row, bound, ns):
    """{n: offload is faster under this bound} from the crossover-table row (the bracket rule: offload faster at n_hi and at every larger measured n)"""
    kind, hi = X_row[f"{bound}_kind"], X_row[f"n_{bound}_hi"]
    if kind == "none":
        return {n: False for n in ns}
    if kind == "below":
        return {n: True for n in ns}
    return {n: bool(n >= hi) for n in ns}


def _noise_ns(X_row):
    out = set()
    for bound in ("fast", "slow"):
        if "within noise" in str(X_row[f"{bound}_labels"]) and X_row[f"{bound}_kind"] == "bracket":
            out |= {int(X_row[f"n_{bound}_lo"]), int(X_row[f"n_{bound}_hi"])}
    return out


def cells(m=None, X=None, allp=None):
    """DataFrame board, circuit, n, cell (LOCAL / OFFLOAD / DEPENDS / NOISE / NORUN / NOMEAS) for n in GRID_N, plus the per-bound flags.
    Both-measured cells follow the crossover table (m, X); NOISE overrides at the two ends of a bracket labelled within noise;
    offload-only n (local missing) and every n at or beyond the board's wall are NORUN; the rest is NOMEAS."""
    if m is None or allp is None:
        m, allp, _ = OB.band_table()
    X = X if X is not None else OB.crossover_table(m)
    sel = allp[allp.selected]
    rows = []
    for b in C.BOARDS:
        wall = SES.wall_n(b)
        for c in C.CIRCUITS:
            xr = X[(X.board == b) & (X.circuit == c)].iloc[0]
            g = m[(m.board == b) & (m.circuit == c)]
            both = set(int(n) for n in g.n)
            off = set(int(n) for n in sel[(sel.board == b) & (sel.circuit == c)].n)
            fast, slow = side_flags(xr, "fast", sorted(both)), side_flags(xr, "slow", sorted(both))
            noise = _noise_ns(xr)
            for n in GRID_N:
                if n in both:
                    if n in noise:
                        cell = NOISE
                    elif fast[n] and slow[n]:
                        cell = OFFLOAD
                    elif not fast[n] and not slow[n]:
                        cell = LOCAL
                    else:
                        cell = DEPENDS
                    rows.append(dict(board=b, circuit=c, n=n, cell=cell, fast_off=fast[n], slow_off=slow[n]))
                else:
                    cell = NORUN if (n >= wall or n in off) else NOMEAS
                    rows.append(dict(board=b, circuit=c, n=n, cell=cell, fast_off=None, slow_off=None))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ predicted crossover
def residual_constants(m):
    """T_res,b: the board-and-link residual as ONE constant per board = median residual of the selected offload points whose PC simulation is below SMALL_SIM_US"""
    s = m[m.pc_sim_us < SMALL_SIM_US]
    return {b: float(s[s.board == b].residual_us.median()) for b in C.BOARDS}


def predicted_bracket(ns, local_pred_us, wire_us, resid_us, pc_min_us, pc_max_us):
    """(E8) the bracket rule (offload_band.bracket) applied to a model: T_local from a model, T_off = wire + residual + simulation (min or max)"""
    df = pd.DataFrame(dict(n=list(ns), median_us=list(local_pred_us),
                           fast_us=np.asarray(pc_min_us, float) + wire_us + resid_us, slow_us=np.asarray(pc_max_us, float) + wire_us + resid_us))
    return {bound: OB.bracket(df, bound) for bound in ("fast", "slow")}


def compare_idx(meas, pred, ns):
    """compare two brackets by the index of their n_hi in the measured grid ns (len(ns) when offload is never faster): 0 -> match, 1 -> off by one, else off by more"""
    def idx(br):
        lo, hi, kind = br
        return len(ns) if kind == "none" else list(ns).index(int(hi))
    d = abs(idx(meas) - idx(pred))
    return "match" if d == 0 else "off by one" if d == 1 else "off by more"


def fmt_bracket(br):
    lo, hi, kind = br
    return "none" if kind == "none" else f"<={int(hi)}" if kind == "below" else f"{int(lo)}-{int(hi)}"


def predicted_table(m=None, X=None):
    """per board x circuit x bound: measured bracket and the brackets predicted by M1 and M2 (time_predictions.csv, in-sample and held-out n alike),
    model status (no model / not identifiable / ok), the share of the bracket's n that were held out of the fit, and weak flags"""
    if m is None:
        m, _, _ = OB.band_table()
    X = X if X is not None else OB.crossover_table(m)
    P = pd.read_csv(os.path.join(C.PROC, "time_predictions.csv"))
    res = residual_constants(m)
    rows = []
    for (b, c), g in m.groupby(["board", "circuit"]):
        g = g.sort_values("n").reset_index(drop=True)
        ns = list(g.n.astype(int))
        pp = P[(P.board == b) & (P.circuit == c)].set_index("n")
        xr = X[(X.board == b) & (X.circuit == c)].iloc[0]
        wire = float(g.wire_us.median())
        nfit = int((pp.role == "fit").sum())
        ident = bool(pp.M2_board_identifiable.iloc[0]) if len(pp) else False
        status = "no model" if nfit == 0 else ("ok" if ident else "not identifiable")
        for bound in ("fast", "slow"):
            meas = (xr[f"n_{bound}_lo"], xr[f"n_{bound}_hi"], xr[f"{bound}_kind"])
            r = dict(board=b, circuit=c, bound=bound, measured=fmt_bracket(meas), model_status=status, n_fit_points=nfit)
            pcmin, pcmax = g.pc_sim_min_us.to_numpy(), g.pc_sim_max_us.to_numpy()
            pc = pcmin if bound == "fast" else pcmax
            for mod in ("M1", "M2"):
                lp = [float(pp.loc[n, "pred_" + mod]) for n in ns]
                br = predicted_bracket(ns, lp, wire, res[b], pcmin, pcmax)[bound]
                r[f"pred_{mod}"] = fmt_bracket(br)
                r[f"cmp_{mod}"] = compare_idx(meas, br, ns)
            ends = [int(x) for x in (meas[0], meas[1]) if x is not None and not (isinstance(x, float) and math.isnan(x))]
            r["bracket_ends_held_out"] = int(sum(pp.loc[n, "role"] == "test" for n in ends if n in pp.index))
            r["bracket_ends"] = len(ends)
            r["measured_labels"] = str(xr[f"{bound}_labels"])
            r["weak"] = "weak" in r["measured_labels"]
            rows.append(r)
    return pd.DataFrame(rows)


def main():
    m, allp, rng = OB.band_table()
    X = OB.crossover_table(m)
    os.makedirs(C.PROC, exist_ok=True)
    band_check(m).to_csv(os.path.join(C.PROC, "band_check.csv"), index=False)
    cells(m, X, allp).to_csv(os.path.join(C.PROC, "decision_cells.csv"), index=False)
    pt = predicted_table(m, X)
    pt.to_csv(os.path.join(C.PROC, "crossover_predicted.csv"), index=False)
    return m, X, pt


if __name__ == "__main__":
    main()
