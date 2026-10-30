#!/usr/bin/env python3
# paper_figures.py
# The two main figures of the paper outline (docs/report/paper_outline.md), made only from data on disk:
#   fig1_memory_wall   state-vector bytes at the last ok n and at the wall n, against the heap the board
#                      really had (free_heap_before + the state it already holds, from Phase 2 raw.csv)
#   fig2_time_vs_n     median per-rep execution time vs n, every circuit and board, with the fitted model B
#                      of analysis/phase2_gate_cost_fit.py drawn over it; grover is NOT in the fit
#                      (out-of-sample); lower row = model error in % per point
#
# Inputs : data/raw/phase2/<board>/<circuit>/with_ref/{raw,memory_wall}.csv,
#          data/processed/gate_cost_fit.csv, gate_cost_validation.csv (run phase2_gate_cost_fit.py first)
# Outputs: data/figures/paper/fig1_memory_wall.{png,svg}, fig2_time_vs_n.{png,svg}

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
sys.path.insert(0, str(REPO_ROOT / "pc" / "shared"))
from shared import plot_style as ps  # noqa: E402
import timing_model as tm  # noqa: E402

RAW = REPO_ROOT / "data" / "raw" / "phase2"
PROCESSED = REPO_ROOT / "data" / "processed"
OUT = REPO_ROOT / "data" / "figures" / "paper"
WALL_STATUSES = {"malloc_failed", "build_overflow"}
CIRCUITS = ps.CIRCUIT_ORDER
MIN_REPS_FOR_IQR = 10          # points below this have too few reps for a meaningful IQR


def _wall_info(board, circuit="h_all"):
    """(heap_bytes_available, last_ok_n, wall_n) for one board from h_all (the wall is the same for
    h_all / bell_ghz / qft; grover is time-limited before its wall on the ESP boards)."""
    raw = pd.read_csv(RAW / board / circuit / "with_ref" / "raw.csv")
    wall = pd.read_csv(RAW / board / circuit / "with_ref" / "memory_wall.csv")
    ok_n = sorted(wall.loc[wall.status == "ok", "n"])
    wall_n = int(wall.loc[wall.status.isin(WALL_STATUSES), "n"].min())
    # free_heap_before is read after the state is allocated, so the heap the board had before
    # allocating = free_heap_before + 8 * 2^n (constant across n, checked below)
    per_n = raw.groupby("n").free_heap_before.median()
    avail = (per_n + 8 * (2 ** per_n.index.to_series())).round()
    spread = float(avail.max() - avail.min())
    return float(avail.median()), int(ok_n[-1]), wall_n, spread


def fig1():
    ps.apply_style()
    boards = ps.BOARD_ORDER
    fig, ax = plt.subplots(figsize=(7.2, 4.6), layout="constrained")
    width = 0.2
    x = np.arange(len(boards))
    rows = []
    for i, b in enumerate(boards):
        avail, ok_n, wall_n, spread = _wall_info(b)
        rows.append((b, avail, ok_n, wall_n, spread, tm.TOTAL_RAM_BYTES[b]))
    series = [("total RAM (datasheet)", [r[5] for r in rows], "#d9d9d9", None),
              ("heap available before the state", [r[1] for r in rows], "#9ecae1", None),
              ("state at last ok n", [8 * 2 ** r[2] for r in rows], "#009E73", None),
              ("state at wall n (failed)", [8 * 2 ** r[3] for r in rows], "#D55E00", "//")]
    for j, (label, vals, color, hatch) in enumerate(series):
        bars = ax.bar(x + (j - 1.5) * width, vals, width, label=label, color=color, hatch=hatch,
                      edgecolor="white" if hatch is None else "black", linewidth=0.5, zorder=3)
        for xi, v, r in zip(x + (j - 1.5) * width, vals, rows):
            txt = f"n={r[2]}" if j == 2 else f"n={r[3]}" if j == 3 else (f"{v/1024:.0f} KB" if v >= 10000 else f"{v:.0f} B")
            ax.text(xi, v * 1.12, txt, ha="center", va="bottom", fontsize=7.5, color=ps.INK_PRIMARY)
    ax.set_yscale("log")
    ax.set_ylim(300, 1.2e6)
    ax.set_xticks(x, [ps.BOARD_LABEL[b] for b in boards])
    ax.set_ylabel("bytes (log scale)")
    ax.legend(loc="upper left", ncol=2, fontsize=8)
    ax.set_title("State-vector memory wall: 8 bytes x 2^n against the heap the board really had", fontsize=9.5)
    note = ("Uno and ESP8266: the first n whose state exceeds the available heap fails "
            "(1812 B and 52240 B). ESP32: the failing state (128 KB) is smaller than the 250 KB free heap,\n"
            "so the limit is the largest contiguous block, not the free total (largest block of about 110 KB "
            "was seen in an earlier retired run, NOT re-measured in this dataset).")
    ps.add_footnote(fig, note)
    ps.save_figure(fig, OUT, "fig1_memory_wall")
    plt.close(fig)
    return rows


def fig2():
    ps.apply_style()
    fit = pd.read_csv(PROCESSED / "gate_cost_fit.csv")
    val = pd.read_csv(PROCESSED / "gate_cost_validation.csv")
    val = val[val.model == "B"]
    fig, axes = plt.subplots(2, 3, figsize=(11, 6.4), layout="constrained",
                             gridspec_kw={"height_ratios": [3, 1]}, sharex="col")
    for col, b in enumerate(ps.BOARD_ORDER):
        ax, axr = axes[0, col], axes[1, col]
        p = fit[(fit.model == "B") & (fit.board == b)].set_index("parameter").value_us
        k = (p.k_H_us, p.k_CNOT_us, p.k_CPHASE_us, p.a_per_gate_us)
        for c in CIRCUITS:
            raw = pd.read_csv(RAW / b / c / "with_ref" / "raw.csv")
            g = raw.groupby("n").exec_time_us
            med, q1, q3, cnt = g.median(), g.quantile(0.25), g.quantile(0.75), g.size()
            ns = med.index.to_numpy()
            few = cnt.to_numpy() < MIN_REPS_FOR_IQR
            filled = c != "grover"        # grover = out-of-sample: hollow markers
            ok = ~few                      # points with too few reps get no IQR band
            ps.iqr_band(ax, ns, [float(a) if o else None for a, o in zip(q1.to_numpy(), ok)],
                        [float(a) if o else None for a, o in zip(q3.to_numpy(), ok)], ps.CIRCUIT_INK[c])
            ax.plot(ns[~few], med.to_numpy()[~few], linestyle="none", marker=ps.CIRCUIT_MARKER[c], markersize=ps.MARKER_SIZE,
                    markerfacecolor=ps.CIRCUIT_INK[c] if filled else "white", markeredgecolor=ps.CIRCUIT_INK[c],
                    markeredgewidth=0.9, zorder=4, label=f"{c} (measured)")
            if few.any():
                ax.plot(ns[few], med.to_numpy()[few], linestyle="none", marker=ps.CIRCUIT_MARKER[c], markersize=ps.MARKER_SIZE + 2,
                        markerfacecolor="none", markeredgecolor="#D55E00", markeredgewidth=1.2, zorder=5,
                        label="fewer than 10 reps (2 h cap)" if c == "grover" else None)
            nn = np.arange(max(2, ns.min()), ns.max() + 1)
            model = [sum(np.array(tm.gate_counts(c, int(n)), dtype=float) * (1 << int(n)) * np.array(k[:3]))
                     + sum(tm.gate_counts(c, int(n))) * k[3] for n in nn]
            ax.plot(nn, model, color=ps.CIRCUIT_INK[c], linestyle=ps.CIRCUIT_LINESTYLE[c], linewidth=ps.REF_LINE_WIDTH,
                    alpha=0.8, zorder=2)
            v = val[(val.board == b) & (val.circuit == c) & val.above_min_median]
            axr.plot(v.n, v.error_pct, marker=ps.CIRCUIT_MARKER[c], markersize=ps.MARKER_SIZE - 0.5, linewidth=ps.LINE_WIDTH,
                     color=ps.CIRCUIT_INK[c], markerfacecolor=ps.CIRCUIT_INK[c] if filled else "white")
        ax.set_yscale("log")
        ax.set_title(ps.BOARD_LABEL[b])
        if col == 0:
            ax.set_ylabel("median execution time per rep (µs, log)")
            axr.set_ylabel("model − measured (%)")
        axr.axhline(0, color=ps.REFERENCE_LINE, linewidth=0.8)
        axr.set_ylim(-80, 40)
        axr.set_xlabel("number of qubits, n")
        ps.style_axes(ax)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    h2, l2 = axes[0, 2].get_legend_handles_labels()
    seen = dict(zip(labels, handles)); seen.update(dict(zip(l2, h2)))
    fig.legend(seen.values(), seen.keys(), loc="outside lower center", ncol=5, fontsize=8)
    ps.suptitle(fig, "Execution time vs n and the fitted per-gate model (lines); grover hollow = out-of-sample", tag=True, fontsize=10)
    ps.save_figure(fig, OUT, "fig2_time_vs_n")
    plt.close(fig)


def main():
    rows = fig1()
    for b, avail, ok_n, wall_n, spread, total in rows:
        print(f"{b:8s} heap before state {avail:9.0f} B (spread across n {spread:.0f} B)  last ok n={ok_n}  wall n={wall_n}  "
              f"state at wall {8 * 2 ** wall_n} B  fits free heap: {8 * 2 ** wall_n <= avail}")
    fig2()
    print(f"figures -> {OUT}")


if __name__ == "__main__":
    main()
