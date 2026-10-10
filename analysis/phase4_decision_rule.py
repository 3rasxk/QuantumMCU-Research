#!/usr/bin/env python3
# phase4_decision_rule.py
# Phase 4 (local vs offload decision rule): checks the two steps of the decision flowchart (analysis/phase4_flowchart.py)
# against the Phase 2 and Phase 3 data and derives the constants the flowchart left open ("to be re-derived from the
# REPS=100 dataset"). Read-only against data/raw (with_ref bucket, the only one); no hardware.
#
#   Step 1  n_max = floor(log2(B / 8)); B = largest contiguous free block in bytes (8 B per amplitude, qsim.hpp Cplx).
#           Checked against the last ok n of the circuits that stopped at a recorded memory wall.
#   Step 2  n*_new = n*_ref + log2(clock_new / clock_ref) + architecture adjustment, n* = the n where the offload round
#           trip per request becomes shorter than the local time per rep. n* is measured from the data here (log-linear
#           interpolation between the two n around the sign change of log2(local / offload)); the adjustment constants are
#           read off the data as log2(local speed ratio) - log2(clock ratio).
#
# Outputs: data/processed/phase4/{n_max_check,crossover,rule_eval,adjustments}.csv and PNGs under data/figures/phase4/
#          (PNG only): crossover_rule.png (data), decision_flowchart.png via phase4_flowchart.py.
# Use:     .venv/bin/python analysis/phase4_decision_rule.py [--raw DIR] [--out DIR] [--figures DIR]

import argparse
import csv
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_data as ad  # noqa: E402  (ok_series, constants; read-only loaders)
from shared import plot_style as ps  # noqa: E402

REPO_ROOT = ad.REPO_ROOT
BOARDS, CIRCUITS = ad.BOARDS, ad.CIRCUITS
CLOCK_MHZ = {"uno": 16, "esp8266": 80, "esp32": 240}          # env JSON f_cpu (build setting), not measured
SRAM_BYTES = ad.BOARD_RAM
MIN_MEDIAN_FOR_RATIO_US = 100.0        # a ratio is only taken at n where both medians are >= this (quantization < 4 %)
PAIRS = (("uno", "esp8266"), ("esp8266", "esp32"), ("uno", "esp32"))


# --------------------------------------------------------------------------- pure functions

def n_max(block_bytes):
    """Step 1: largest n whose state (8 B x 2^n) fits in a block of `block_bytes`."""
    if block_bytes < 8:
        return 0
    return int(math.floor(math.log2(block_bytes / 8)))


def crossover(local_med, offload_med):
    """First n where offload < local, by log-linear interpolation. Returns (n_star, flag):
    flag 'ok' (crossing between two measured n), 'at_or_below_first_n' (offload already faster at the first common n; n_star = that n),
    'none_in_range' (local faster at every common n; n_star None)."""
    ns = sorted(set(local_med) & set(offload_med))
    if not ns:
        return None, "no_common_n"
    d = {n: math.log2(local_med[n] / offload_med[n]) for n in ns}     # > 0: local slower
    if d[ns[0]] > 0:
        return float(ns[0]), "at_or_below_first_n"
    for a, b in zip(ns, ns[1:]):
        if d[b] > 0:
            return a + (0 - d[a]) * (b - a) / (d[b] - d[a]), "ok"
    return None, "none_in_range"


def log2_speed_ratio(slow_med, fast_med, min_median_us=MIN_MEDIAN_FOR_RATIO_US):
    """Median over common n of log2(slow / fast), using only n where both medians >= min_median_us."""
    ns = [n for n in sorted(set(slow_med) & set(fast_med)) if slow_med[n] >= min_median_us and fast_med[n] >= min_median_us]
    if not ns:
        return None
    return float(np.median([math.log2(slow_med[n] / fast_med[n]) for n in ns]))


# --------------------------------------------------------------------------- tables

def medians(raw_root, board, circuit, phase):
    return {n: float(np.median(v)) for n, v in ad.ok_series(raw_root, board, circuit, phase).items()}


def n_max_rows(raw_root):
    out = []
    for b in BOARDS:
        for c in CIRCUITS:
            d = Path(raw_root) / "phase2" / b / c / "with_ref"
            term = ad.readdf(d / "memory_wall.csv", ["n", "status"])
            raw = ad.readdf(d / "raw.csv")
            if not len(term):
                continue
            term = term.drop_duplicates("n", keep="last")
            walls = term[term["status"].map(lambda s: ad.rs.is_wall_status(str(s)))]
            ok = term[term["status"] == "ok"]
            if not len(walls):
                continue                               # the series stopped at the time cap, not at memory
            observed = int(ok["n"].max())
            if b == "uno":
                static = float(np.median([float(r.compile_ram_used_bytes) - 8 * 2 ** int(r.n) for r in ok.itertuples()
                                          if pd.notna(r.compile_ram_used_bytes)]))
                measured, basis = SRAM_BYTES[b] - static, f"SRAM - static data ({static:.0f} B, compile RAM used - state)"
            elif b == "esp32":
                n0 = int(raw["n"].min())
                measured, basis = float(raw[raw["n"] == n0]["largest_block"].median()) + 8 * 2 ** n0, "largest free block (firmware-reported)"
            else:
                n0 = int(raw["n"].min())
                measured = float(raw[raw["n"] == n0]["free_heap_before"].median()) + 8 * 2 ** n0
                basis = "total free heap (largest block is not logged by the ESP8266 firmware)"
            fallback = SRAM_BYTES[b] / 2
            out.append(dict(board=b, circuit=c, observed_last_ok_n=observed, observed_wall_n=int(walls["n"].min()),
                            B_measured_bytes=round(measured), B_basis=basis, n_max_measured_B=n_max(measured),
                            agree_measured_B=n_max(measured) == observed, B_fallback_sram_half=fallback,
                            n_max_fallback=n_max(fallback), agree_fallback=n_max(fallback) == observed))
    return out


def crossover_rows(raw_root):
    out = []
    for c in CIRCUITS:
        for b in BOARDS:
            loc, off = medians(raw_root, b, c, 2), medians(raw_root, b, c, 3)
            ns, flag = crossover(loc, off)
            common = sorted(set(loc) & set(off))
            out.append(dict(circuit=c, board=b, n_star=ns if ns is None else round(ns, 3), flag=flag,
                            common_n=f"{common[0]}..{common[-1]}" if common else "",
                            integer_n_star=next((n for n in common if off[n] < loc[n]), "none in range")))
    return out


def rule_rows(raw_root, cross):
    star = {(r["circuit"], r["board"]): r for r in cross}
    ev, adj = [], []
    for c in CIRCUITS:
        loc = {b: medians(raw_root, b, c, 2) for b in BOARDS}
        for ref, new in PAIRS:
            r = log2_speed_ratio(loc[ref], loc[new])
            clk = math.log2(CLOCK_MHZ[new] / CLOCK_MHZ[ref])
            sr, sn = star[(c, ref)], star[(c, new)]
            usable = sr["flag"] == "ok" and sn["flag"] == "ok"
            row = dict(circuit=c, ref=ref, new=new, log2_clock_ratio=clk, log2_local_speed_ratio=r,
                       architecture_adjustment=(r - clk) if r is not None else None,
                       n_star_ref=sr["n_star"], n_star_new_measured=sn["n_star"], flag_ref=sr["flag"], flag_new=sn["flag"])
            if usable and r is not None:
                row.update(n_star_pred_clock_only=sr["n_star"] + clk, error_clock_only=sr["n_star"] + clk - sn["n_star"],
                           n_star_pred_speed_ratio=sr["n_star"] + r, error_speed_ratio=sr["n_star"] + r - sn["n_star"])
            ev.append(row)
            adj.append(dict(circuit=c, ref=ref, new=new, log2_clock_ratio=round(clk, 3),
                            log2_local_speed_ratio=None if r is None else round(r, 3),
                            architecture_adjustment=None if r is None else round(r - clk, 3),
                            local_speed_ratio=None if r is None else round(2 ** r, 2)))
    return ev, adj


def offload_floor_rows(raw_root):
    """Offload round trip at small n per board (the 'floor' the local time has to reach), medians over circuits."""
    out = []
    for b in BOARDS:
        v = []
        for c in CIRCUITS:
            off = medians(raw_root, b, c, 3)
            v += [off[n] for n in off if n <= 4]
        out.append(dict(board=b, offload_round_trip_us_n_le_4_median=float(np.median(v)) if v else None, points=len(v)))
    return out


# --------------------------------------------------------------------------- output

def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def plot_rule(ev, figures_dir):
    import matplotlib.pyplot as plt
    ps.apply_style()
    df = pd.DataFrame(ev)
    df = df[df["error_speed_ratio"].notna()] if "error_speed_ratio" in df else df.iloc[0:0]
    if df.empty:
        print("no usable crossover pairs -- skipping crossover_rule.png")
        return None
    import textwrap
    from matplotlib.lines import Line2D
    fig, ax = plt.subplots(figsize=(6.4, 6.0), layout="constrained")
    mk = {c: ps.CIRCUIT_MARKER[c] for c in CIRCUITS}
    shifts = []
    for c in CIRCUITS:
        d = df[df.circuit == c]
        if d.empty:
            continue
        shift = d.n_star_new_measured - d.n_star_ref
        shifts += list(shift)
        ax.plot(d.log2_local_speed_ratio, shift, linestyle="none", marker=mk[c], markersize=8, markerfacecolor=ps.CIRCUIT_INK[c],
                markeredgecolor="white", zorder=3)
        ax.plot(d.log2_clock_ratio, shift, linestyle="none", marker=mk[c], markersize=8, markerfacecolor="white",
                markeredgecolor=ps.INK_PRIMARY, markeredgewidth=1.3, zorder=3)
    top = max(shifts + list(df.log2_local_speed_ratio) + list(df.log2_clock_ratio)) + 0.6
    ax.plot([0, top], [0, top], linestyle="--", color=ps.INK_SECONDARY, linewidth=1.1, zorder=1)
    ax.set_xlim(0, top)
    ax.set_ylim(0, top)
    ax.set_aspect("equal")
    ax.set_xlabel("log2 of the ratio (filled: local speed ratio; open: clock ratio)")
    ax.set_ylabel("Measured shift of the crossover n* (qubits)")
    h = [Line2D([], [], linestyle="none", marker=mk[c], markersize=8, markerfacecolor=ps.CIRCUIT_INK[c], markeredgecolor="white", label=c)
         for c in CIRCUITS]
    h += [Line2D([], [], linestyle="none", marker="o", markerfacecolor="black", markeredgecolor="white", label="x = log2 local speed ratio"),
          Line2D([], [], linestyle="none", marker="o", markerfacecolor="white", markeredgecolor="black", markeredgewidth=1.3,
                 label="x = log2 clock ratio"),
          Line2D([], [], linestyle="--", color=ps.INK_SECONDARY, label="shift = x")]
    ax.legend(handles=h, fontsize=8, loc="upper left")
    ps.style_axes(ax)
    fig.suptitle("Phase 4: crossover shift between boards", fontsize=10.5)
    ps.add_footnote(fig, "\n".join(textwrap.wrap("Pairs where both boards have a measured crossover (7). n* by log-linear interpolation of offload vs "
                                                "local medians; one unit per board; 115,200 baud; the PC simulates with Qiskit Aer.", 90)))
    return ps.save_figure_png_only(fig, figures_dir, "crossover_rule")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, default=REPO_ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "data" / "processed" / "phase4")
    ap.add_argument("--figures", type=Path, default=REPO_ROOT / "data" / "figures" / "phase4")
    a = ap.parse_args(argv)
    ad.assert_not_raw(a.out, a.raw)
    ad.assert_not_raw(a.figures, a.raw)
    nm = n_max_rows(a.raw)
    cross = crossover_rows(a.raw)
    ev, adj = rule_rows(a.raw, cross)
    floor = offload_floor_rows(a.raw)
    write_csv(a.out / "n_max_check.csv", nm)
    write_csv(a.out / "crossover.csv", cross)
    write_csv(a.out / "rule_eval.csv", ev)
    write_csv(a.out / "adjustments.csv", adj)
    write_csv(a.out / "offload_floor.csv", floor)
    plot_rule(ev, a.figures)
    d = pd.DataFrame(ev)
    use = d[d["error_speed_ratio"].notna()] if "error_speed_ratio" in d else d.iloc[0:0]
    if len(use):
        print(f"step 1: measured-B rule agrees on {sum(r['agree_measured_B'] for r in nm)}/{len(nm)}, "
              f"SRAM/2 fallback on {sum(r['agree_fallback'] for r in nm)}/{len(nm)} series")
        print(f"step 2: {len(use)} uncensored (circuit, board pair) crossovers; RMS error clock-only "
              f"{float(np.sqrt((use.error_clock_only ** 2).mean())):.2f} n, speed-ratio rule {float(np.sqrt((use.error_speed_ratio ** 2).mean())):.2f} n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
