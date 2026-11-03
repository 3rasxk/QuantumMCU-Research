#!/usr/bin/env python3
"""Tests for the trade-off equations, the crossover bracket, the decision map and the predicted crossover (analysis/phase4/tradeoff.py).
Run: .venv/bin/python analysis/phase4/tradeoff_test.py   (no hardware; reads data/raw and data/processed/phase4 only)"""
import math
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import p4common as C  # noqa: E402
import gatecount as G  # noqa: E402
import offload_band as OB  # noqa: E402
import tradeoff as TO  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def synth(local, fast, slow, **kw):
    """a (board, circuit) group for OB.bracket / OB.crossover_table; IQRs default to +-5 % of the values"""
    n = len(local)
    d = pd.DataFrame(dict(board="b", circuit="c", n=np.arange(2, 2 + n), median_us=local, fast_us=fast, slow_us=slow))
    d["q1_us"], d["q3_us"] = d.median_us * 0.95, d.median_us * 1.05
    for bd in ("fast", "slow"):
        d[f"{bd}_q1_us"], d[f"{bd}_q3_us"] = d[f"{bd}_us"] * 0.95, d[f"{bd}_us"] * 1.05
    d["weak_point"] = False
    d["pc_sim_extreme_weak"] = False
    for k, v in kw.items():
        d[k] = v
    return d


def parse_cell_text(s):
    """Table III cell -> (n_lo, n_hi, kind, flags)"""
    dag = "$^{\\dagger}$" in s
    ddag = "$^{\\ddagger}$" in s
    core = s.replace("$^{\\dagger}$", "").replace("$^{\\ddagger}$", "").strip()
    if core == "none":
        return None, None, "none", dag, ddag
    m = re.match(r"\$\\le\$(\d+)", core)
    if m:
        return None, int(m.group(1)), "below", dag, ddag
    a, b = core.split("--")
    return int(a), int(b), "bracket", dag, ddag


def main():
    # ---------------- equations
    m, allp, _ = OB.band_table()
    check("E6 wire time: formula 10 x (4 + 6) bytes / 115200 baud equals the pipeline value in every offload point",
          np.allclose(m.wire_us, TO.t_wire_us(4 + 6, 115200)) and abs(TO.t_wire_us(10, 115200) - 868.0555555) < 1e-3 and set(m.wire_us.round(6)) == {round(TO.t_wire_us(10, 115200), 6)})
    check("E1 state size: 8 B x 2^n", TO.memory_bytes(10) == 8192 and TO.memory_bytes(13) == 65536)
    mm = pd.read_csv(os.path.join(C.PROC, "memory_model.csv"))
    ok = all(TO.n_max(r.B_bytes) == r.n_max_pred for r in mm.itertuples())
    check("E2 n_max = floor(log2(B / 8)) reproduces n_max_pred of every row of the memory table", ok)
    w = mm[mm.wall_n.notna() & mm.match.astype(str).eq("True")]
    check("E2 reproduces (first failing n) - 1 for every row marked as agreeing", all(TO.n_max(r.B_bytes) == int(r.wall_n) - 1 for r in w.itertuples()) and len(w) > 0)
    # E3 / E4: the stored predictions are the formulas with the stored constants and the gate counts
    P = pd.read_csv(os.path.join(C.PROC, "time_predictions.csv"))
    F = pd.read_csv(os.path.join(C.PROC, "time_fit.csv"))
    ok3 = ok4 = True
    for r in P.itertuples():
        nh, nc, ncp = G.counts(r.circuit, int(r.n))
        c1 = float(F[(F.board == r.board) & (F.model == "M1")].c.iloc[0])
        f2 = F[(F.board == r.board) & (F.model == "M2")].iloc[0]
        t1 = c1 * (nh + nc + ncp) * 2 ** int(r.n)
        t2 = (f2.c_H * nh + f2.c_CNOT * nc + f2.c_CPHASE * ncp) * 2 ** int(r.n) + f2.a_call * (nh + nc + ncp)
        ok3 &= bool(np.isclose(t1, r.pred_M1, rtol=1e-9))
        ok4 &= bool(np.isclose(t2, r.pred_M2, rtol=1e-9))
    check("E3 M1: T = c_b x (gate calls) x 2^n equals every stored M1 prediction", ok3)
    check("E4 M2: T = (c_H N_H + c_CNOT N_CNOT + c_CP N_CP) 2^n + a G equals every stored M2 prediction", ok4)
    # gate counts: closed forms quoted in the paper (E4)
    check("E5 h_all / bell_ghz / qft totals: n, n, n + n(n-1)/2", all(G.total_gates("h_all", n) == n and G.total_gates("bell_ghz", n) == n and G.total_gates("qft", n) == n + n * (n - 1) // 2 for n in range(2, 15)))
    check("E5 multi-controlled phase: G(k) = 8 x 3^(k-2) - 3 for k >= 2", all(sum(G.mc_phase(k)) == 8 * 3 ** (k - 2) - 3 for k in range(2, 14)))
    check("E5 grover total: n + k(n) (16 x 3^(n-3) + 8n - 6) for n >= 3",
          all(G.total_gates("grover", n) == n + G.grover_iterations(n) * (16 * 3 ** (n - 3) + 8 * n - 6) for n in range(3, 15)))
    check("E10 grover marked-state probability sin^2((2k+1) theta), theta = asin(2^(-n/2)), k = floor(pi/4 sqrt(2^n)) is 1 - O(2^-n) (k from the firmware)",
          all(math.sin((2 * G.grover_iterations(n) + 1) * math.asin(2 ** (-n / 2))) ** 2 > 0.9 for n in range(4, 15)))

    # ---------------- bracket rule on synthetic cases
    clean = synth([1, 2, 4, 8, 16, 32], [10, 10, 10, 10, 10, 10], [20, 20, 20, 20, 20, 20])
    check("bracket: clean crossing, fast 10 us offload -> between n=5 and n=6 (local 16 > 10)", OB.bracket(clean, "fast") == (5, 6, "bracket"))
    check("bracket: clean crossing, slow 20 us offload -> between n=6 and n=7", OB.bracket(synth([1, 2, 4, 8, 16, 32, 64], [10] * 7, [20] * 7), "slow") == (6, 7, "bracket"))
    none = synth([1, 2, 3, 4], [10] * 4, [20] * 4)
    check("bracket: no crossing up to the largest measured n", OB.bracket(none, "fast") == (None, None, "none"))
    below = synth([50, 60, 70], [10] * 3, [20] * 3)
    check("bracket: offload faster at the smallest n -> below", OB.bracket(below, "fast") == (None, 2, "below"))
    dis = synth([1, 2, 4, 8, 16, 32], [3] * 6, [20] * 6)
    check("bracket: bounds disagree (fast earlier than slow)", OB.bracket(dis, "fast")[1] < OB.bracket(dis, "slow")[1])
    flip = synth([1, 20, 4, 8, 16, 32], [10] * 6, [20] * 6)       # offload faster at n=3 only: not persistent, the bracket stays after the last flip back
    check("bracket: an isolated early flip does not move the bracket (offload must stay faster at every larger n)", OB.bracket(flip, "fast") == (5, 6, "bracket"))
    xn = OB.crossover_table(synth([1, 2, 4, 9.8, 16, 32], [10] * 6, [20] * 6))
    check("crossover_table: IQRs overlap at a bracket end -> 'within noise'", "within noise" in str(xn.fast_labels.iloc[0]))
    xc = OB.crossover_table(synth([1, 2, 4, 8, 40, 80], [10] * 6, [20] * 6))
    check("crossover_table: well separated IQRs -> no 'within noise'", "within noise" not in str(xc.fast_labels.iloc[0]))

    # ---------------- decision map vs Table III
    X = OB.crossover_table(m)
    cells = TO.cells(m, X, allp)
    rows = [l.rstrip(" \\\n").split(" & ") for l in open(os.path.join(C.ROOT, "paper", "tables", "crossover.tex")) if " & " in l and not l.startswith("Board")]
    lab = {C.BOARD_LABEL[b]: b for b in C.BOARDS}
    ok_all, bad = True, []
    for r in rows:
        b, c = lab[r[0]], r[1].replace("\\_", "_")
        g = cells[(cells.board == b) & (cells.circuit == c)].set_index("n")
        for col, bound in ((3, "fast"), (4, "slow")):
            lo, hi, kind, dag, ddag = parse_cell_text(r[col])
            flags = {n: bool(g.loc[n, f"{bound}_off"]) for n in g.index if not pd.isna(g.loc[n, "fast_off"])}
            ns = sorted(flags)
            got = (None, None, "none")
            for i, n in enumerate(ns):
                if all(flags[k] for k in ns[i:]):
                    got = (None, n, "below") if i == 0 else (ns[i - 1], n, "bracket")
                    break
            if got[2] != kind or got[1] != hi or got[0] != lo:
                ok_all = False
                bad.append((b, c, bound, r[col], got))
            ends = {x for x in (lo, hi) if x is not None}
            noise_cells = {n for n in g.index if g.loc[n, "cell"] == TO.NOISE}
            if dag and kind == "bracket" and not ends <= noise_cells:
                ok_all = False
                bad.append((b, c, bound, "dagger but cells not noise", ends, noise_cells))
    check("decision map: for every board x circuit the per-bound sides in the cells reproduce the bracket printed in Table III", ok_all, str(bad[:3]))
    cnt = 0
    for (b, c), g in cells.groupby(["board", "circuit"]):
        for r in g.itertuples():
            if r.cell in (TO.LOCAL, TO.OFFLOAD, TO.DEPENDS):
                cnt += 1
                want = TO.OFFLOAD if (r.fast_off and r.slow_off) else TO.LOCAL if (not r.fast_off and not r.slow_off) else TO.DEPENDS
                if r.cell != want:
                    ok_all = False
    check("decision map: every coloured cell agrees with the two bounds", ok_all and cnt > 0)
    check("decision map: every (board, circuit, n) of the grid has exactly one cell", len(cells) == len(C.BOARDS) * len(C.CIRCUITS) * len(TO.GRID_N) and not cells.duplicated(["board", "circuit", "n"]).any())
    check("decision map: n at or beyond a board's wall is never coloured as measured",
          all(r.cell in (TO.NORUN, TO.NOMEAS) for r in cells.itertuples() if r.n >= TO.SES.wall_n(r.board)))

    # ---------------- predicted crossover on a synthetic exact model
    ns = list(range(2, 12))
    exact = [3.0 * 2 ** n for n in ns]                                   # local time of an exactly known model
    pcmin, pcmax = [100.0] * 10, [400.0] * 10
    d = synth(exact, [100.0 + 5 + 7] * 10, [400.0 + 5 + 7] * 10)
    truth = {bd: OB.bracket(d, bd) for bd in ("fast", "slow")}
    pred = TO.predicted_bracket(ns, exact, 5.0, 7.0, pcmin, pcmax)
    check("predicted crossover: an exact model returns the true bracket for both bounds", pred == truth, f"{pred} vs {truth}")
    check("compare: identical -> match", TO.compare_idx(truth["fast"], pred["fast"], ns) == "match")
    off1 = TO.predicted_bracket(ns, [x * 2.2 for x in exact], 5.0, 7.0, pcmin, pcmax)
    check("compare: a model 2.2x too slow moves the bracket one step earlier -> off by one", TO.compare_idx(truth["fast"], off1["fast"], ns) == "off by one", str(off1["fast"]))
    off3 = TO.predicted_bracket(ns, [x * 20 for x in exact], 5.0, 7.0, pcmin, pcmax)
    check("compare: a model 20x too slow -> off by more", TO.compare_idx(truth["fast"], off3["fast"], ns) == "off by more", str(off3["fast"]))
    nn = TO.predicted_bracket(ns, [1.0] * 10, 5.0, 7.0, pcmin, pcmax)
    check("compare: no crossover predicted but one measured -> counted by position", TO.compare_idx(truth["fast"], nn["fast"], ns) in ("off by one", "off by more"))
    pt = TO.predicted_table(m, X)
    check("predicted table: ESP8266 grover has no fit points -> 'no model'", set(pt[(pt.board == "esp8266") & (pt.circuit == "grover")].model_status) == {"no model"})
    check("predicted table: one row per board x circuit x bound", len(pt) == 24)

    print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
