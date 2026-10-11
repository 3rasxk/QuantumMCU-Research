#!/usr/bin/env python3
# phase2_cross_board_plots.py
#
# Cross-board comparison, one PNG per circuit: median per-rep micros() time vs n for every board that has data,
# on one log-y chart (IQR bars, faint reps, board = marker + linestyle + colour). Reads
# data/raw/phase2/<board>/<circuit>/<bucket>/ (raw.csv, memory_wall.csv, env/*.json) read-only.
# Output: data/figures/phase2/compare_<circuit>.png (PNG only).
#
# Use:  .venv/bin/python analysis/phase2_cross_board_plots.py [--circuit grover] [--ref]

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _graph_data as gd  # noqa: E402
from _graph_data import OK, OK_CAPPED, WALL, TIME_LIMITED  # noqa: E402
from shared import plot_style as ps  # noqa: E402
from shared import timing_model as tm  # noqa: E402

CAP_TEXT = f"{tm.POINT_TIME_CAP_S / 3600:g} h"
LINE_W = 1.8          # colour-only series: solid lines, no markers


def plot_circuit(circuit, ref=False):
    sets = {b: gd.PointSet(b, circuit, 2, ref) for b in ps.BOARD_ORDER}
    sets = {b: S for b, S in sets.items() if S.raw}
    if not sets:
        print(f"[{circuit}] no data on any board -- skipping")
        return None
    fig, ax = plt.subplots(figsize=(8.2, 5.8), layout="constrained")
    tr = ax.get_xaxis_transform()
    lo = hi = None
    reps_all = []
    for row, (b, S) in enumerate(sets.items()):
        out = gd.outcomes_phase2(S)
        vals = gd.values_by_n(S.raw, "exec_time_us")
        ns = [n for n in sorted(vals) if not out or out.get(n, {}).get("cat") in (OK, OK_CAPPED)]
        if not ns:
            continue
        st = {n: gd.stats(vals[n]) for n in ns}
        col = ps.BOARD_COLOR[b]
        if ps.SHOW_REPS:
            for n in ns:
                ax.plot(np.full(len(vals[n]), n), vals[n], linestyle="none", marker=".", markersize=2.6, color=col,
                        alpha=0.16, zorder=1, rasterized=True)
        ps.iqr_band(ax, ns, [st[n][1] for n in ns], [st[n][2] for n in ns], col)
        ax.plot(ns, [st[n][0] for n in ns], linestyle="-", color=col, linewidth=LINE_W, zorder=2)
        for n in ns:                   # colour-only series; only a time-capped point (< 100 reps) gets an open marker
            if out.get(n, {}).get("cat") == OK_CAPPED:
                ax.plot([n], [st[n][0]], linestyle="none", markersize=7, zorder=4, **ps.dot_kwargs("capped", col))
        reps_all += [len(vals[n]) for n in ns]
        meds = [st[n][0] for n in ns]
        lo, hi = min(meds + [lo or meds[0]]), max(meds + [hi or meds[0]])
        y = 0.95 - 0.05 * row                                   # one strip row per board
        for n, o in sorted(out.items()):
            if o["cat"] == WALL:
                ax.plot([n], [y], transform=tr, linestyle="none", markersize=8, clip_on=False, zorder=5,
                        **ps.dot_kwargs("wall", col))
            elif o["cat"] == TIME_LIMITED:
                ax.plot([n], [y], transform=tr, linestyle="none", markersize=8, clip_on=False, zorder=5,
                        **ps.dot_kwargs("time_limited", col))
    ax.set_yscale("log")
    ps.style_axes(ax, log_y=True)
    ax.set_ylim(lo / 3, hi * 10 ** 1.1)
    ax.set_xlabel("Number of qubits, $n$")
    ax.set_ylabel("Median execution time per rep (µs, log scale)")
    h = [Line2D([], [], linestyle="-", color=ps.BOARD_COLOR[b], linewidth=LINE_W,
                label=ps.BOARD_LABEL[b]) for b in sets]
    h += [Line2D([], [], linestyle="none", markersize=7, label=f"< 100 reps ({CAP_TEXT} cap)", **ps.dot_kwargs("capped")),
          Line2D([], [], linestyle="none", markersize=8, label="memory wall", **ps.dot_kwargs("wall", ps.INK_MUTED)),
          Line2D([], [], linestyle="none", markersize=8, label="time-limited, not run", **ps.dot_kwargs("time_limited"))]
    ax.legend(handles=h, loc="best", fontsize=8.5)
    note = "; ".join(f"{ps.BOARD_SHORT[b]}: {S.commit_note()}" for b, S in sets.items())
    ps.suptitle(fig, f"{ps.CIRCUIT_LABEL.get(circuit, circuit)} -- all boards (target REPS={tm.REPS}; {note})",
                fontsize=10)
    ax.text(0.0, 1.05, "Phase 2, micros() timing, one unit per board", transform=ax.transAxes, fontsize=8.5,
            color=ps.INK_SECONDARY)
    gd.footnote(fig, gd.reps_text(reps_all) + "; line = median, band = IQR (25th-75th pct); no band where a point has one rep.")
    return ps.save_figure_png_only(fig, gd.REPO_ROOT / "data" / "figures" / "phase2", f"compare_{circuit}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--circuit", default=None)
    ap.add_argument("--ref", action="store_true", help="read the with_ref bucket (default no_ref)")
    a = ap.parse_args()
    ps.apply_style()
    circuits = [a.circuit] if a.circuit else list(ps.CIRCUIT_ORDER)
    n = 0
    for c in circuits:
        if plot_circuit(c, a.ref):
            n += 1
    print(f"\n{n} figure(s) written under {gd.REPO_ROOT / 'data' / 'figures' / 'phase2'} (PNG only)")


if __name__ == "__main__":
    main()
