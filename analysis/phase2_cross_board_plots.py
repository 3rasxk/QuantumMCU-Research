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
        col, mk, ls = ps.BOARD_COLOR[b], ps.BOARD_MARKER[b], gd.BOARD_LINESTYLE[b]
        for n in ns:
            ax.plot(np.full(len(vals[n]), n), vals[n], linestyle="none", marker=".", markersize=2.6, color=col,
                    alpha=0.16, zorder=1, rasterized=True)
        ax.plot(ns, [st[n][0] for n in ns], linestyle=ls, color=col, linewidth=1.4, zorder=2)
        for n in ns:
            med, q1, q3 = st[n]
            if q1 is not None:
                ax.errorbar([n], [med], yerr=[[med - q1], [q3 - med]], color=col, linewidth=1.6, capsize=2.5, zorder=3)
            capped = out.get(n, {}).get("cat") == OK_CAPPED
            ax.plot([n], [med], linestyle="none", marker=mk, markersize=6.5, zorder=4, markeredgecolor=col if capped
                    else "white", markerfacecolor="white" if capped else col, markeredgewidth=1.3 if capped else 0.6)
        reps_all += [len(vals[n]) for n in ns]
        meds = [st[n][0] for n in ns]
        lo, hi = min(meds + [lo or meds[0]]), max(meds + [hi or meds[0]])
        y = 0.95 - 0.05 * row                                   # one strip row per board
        for n, o in sorted(out.items()):
            if o["cat"] == WALL:
                ax.plot([n], [y], transform=tr, linestyle="none", marker="X", markersize=8, markerfacecolor=col,
                        markeredgecolor="white", markeredgewidth=0.5, clip_on=False, zorder=5)
            elif o["cat"] == TIME_LIMITED:
                ax.plot([n], [y], transform=tr, linestyle="none", marker="*", markersize=10, markerfacecolor="white",
                        markeredgecolor=col, markeredgewidth=1.2, clip_on=False, zorder=5)
    ax.set_yscale("log")
    ps.style_axes(ax, log_y=True)
    ax.set_ylim(lo / 3, hi * 10 ** 1.1)
    ax.set_xlabel("Number of qubits, n (qubits)")
    ax.set_ylabel("Median execution time per rep (µs, log scale)")
    h = [Line2D([], [], linestyle=gd.BOARD_LINESTYLE[b], marker=ps.BOARD_MARKER[b], color=ps.BOARD_COLOR[b],
                label=ps.BOARD_LABEL[b]) for b in sets]
    h += [Line2D([], [], linestyle="none", marker="o", markerfacecolor="white", markeredgecolor=ps.INK_PRIMARY,
                 markeredgewidth=1.3, label=f"< 100 reps ({CAP_TEXT} per-point cap)"),
          Line2D([], [], linestyle="none", marker="X", color=ps.INK_PRIMARY,
                 label="memory wall (recorded evidence), top strip"),
          Line2D([], [], linestyle="none", marker="*", markerfacecolor="white", markeredgecolor=ps.INK_PRIMARY,
                 label=f"time-limited, not run (1 rep > {CAP_TEXT}), top strip")]
    ax.legend(handles=h, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=1, fontsize=8.5)
    note = "; ".join(f"{ps.BOARD_SHORT[b]}: {S.commit_note()}" for b, S in sets.items())
    fig.suptitle(f"{ps.CIRCUIT_LABEL.get(circuit, circuit)} -- all boards (target REPS={tm.REPS}; {note})",
                 fontsize=10.5)
    ax.text(0.0, 1.05, "Phase 2, micros() timing, one unit per board", transform=ax.transAxes, fontsize=8.5,
            color=ps.INK_SECONDARY)
    gd.footnote(fig, gd.reps_text(reps_all) + "; marker = median, bar = IQR (25th-75th pct), dots = every rep.")
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
