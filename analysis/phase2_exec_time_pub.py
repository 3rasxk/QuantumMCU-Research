#!/usr/bin/env python3
# phase2_exec_time_pub.py
# Publication-style figure: per-rep execution time vs number of qubits for one
# (board, circuit) from data/raw/phase2/<board>/<circuit>/<bucket>/raw.csv.
# Median with IQR error bars (skipped where n_reps == 1), timing_model estimate as a
# dashed line, and the measured per-qubit growth factor. Read-only against data/raw/.
#
# Output: data/figures/phase2/<board>/<circuit>/exec_time_vs_qubits.png
#
# Usage: python3 analysis/phase2_exec_time_pub.py --board esp32 --circuit grover

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import paths as sp  # noqa: E402
from shared import plot_style as ps  # noqa: E402
from shared import timing_model as tm  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", required=True)
    ap.add_argument("--circuit", required=True)
    ap.add_argument("--ref", action="store_true")
    args = ap.parse_args()

    raw_path = sp.raw_csv_path(args.board, args.circuit, phase=2, ref=args.ref)
    if not raw_path.exists():
        raise SystemExit(f"error: {raw_path} not found")
    by_n = defaultdict(list)
    with open(raw_path, newline="") as f:
        for r in csv.DictReader(f):
            by_n[int(r["n"])].append(float(r["exec_time_us"]))
    ns = sorted(by_n)
    med = np.array([np.median(by_n[n]) for n in ns])
    q1 = np.array([np.percentile(by_n[n], 25) for n in ns])
    q3 = np.array([np.percentile(by_n[n], 75) for n in ns])
    reps = [len(by_n[n]) for n in ns]

    import matplotlib
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    ps.apply_style()
    color = ps.BOARD_COLOR[args.board]
    fig, ax = plt.subplots(figsize=(4.6, 3.4), layout="constrained")

    model = np.array([tm.expected_exec_time_us(args.board, args.circuit, n) for n in ns])
    ax.plot(ns, model, color=ps.INK_SECONDARY, linestyle=(0, (5, 3)), linewidth=ps.REF_LINE_WIDTH,
            label="Timing model (estimate)", zorder=2)
    ps.iqr_band(ax, ns, [float(q1[i]) if reps[i] > 1 else None for i in range(len(ns))],
                [float(q3[i]) if reps[i] > 1 else None for i in range(len(ns))], color)
    ax.plot(ns, med, color=color, linestyle="-", linewidth=1.8,
            label=f"Measured ({ps.BOARD_SHORT[args.board]}), median line, IQR band", zorder=4)

    if len(ns) >= 3:
        slope = np.polyfit(ns, np.log10(med), 1)[0]
        ax.text(0.04, 0.95, f"growth $\\approx {10 ** slope:.1f}\\times$ per qubit",
                transform=ax.transAxes, va="top", fontsize=8.5)

    ax.set_yscale("log")
    ps.style_axes(ax)
    ax.set_xlabel("Number of qubits, $n$")
    ax.set_ylabel(r"Execution time per repetition ($\mu$s)")
    label = ps.CIRCUIT_LABEL.get(args.circuit, args.circuit).split(" (")[0]
    ax.set_title(f"{ps.BOARD_SHORT[args.board]} — {label} (REPS={max(reps)}, {ps.git_tag()})", fontsize=9.5)
    ax.legend(loc="lower right")
    rep_txt = f"{reps[0]}" if len(set(reps)) == 1 else "/".join(str(r) for r in reps)
    ax.text(1.0, -0.2, f"repetitions per point: {rep_txt}", transform=ax.transAxes,
            ha="right", va="top", fontsize=7.5, color=ps.INK_SECONDARY)

    out = REPO_ROOT / "data" / "figures" / "phase2" / args.board / args.circuit
    ps.save_figure_png_only(fig, out, "exec_time_vs_qubits")   # PNG only under data/figures/


if __name__ == "__main__":
    main()
