#!/usr/bin/env python3
# phase4_all_in_one.py
# Phase 4 in one chart: the measured crossover n* (offload becomes faster than local) for every board and circuit,
# from data/processed/phase4/crossover.csv (run analysis/phase4_decision_rule.py first). Same 12 colours as
# phase2_all_in_one.py (one tone family per board). Drawn in the graph-create house style (analysis/vendor/plot_style.py): no grid, outward ticks, black
# spines, centred title, legend upper left with one column per board; still a bar chart. Output: data/figures/phase4/all_boards_all_circuits.png
#
# Use:  .venv/bin/python analysis/phase4_all_in_one.py

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _graph_data as gd  # noqa: E402
from shared import plot_style as ps  # noqa: E402  (board / circuit order and labels only)

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
import plot_style as house  # noqa: E402  (vendored graph-create style)


def main():
    house.apply_style()
    df = pd.read_csv(gd.REPO_ROOT / "data" / "processed" / "phase4" / "crossover.csv")
    rows = {(r.board, r.circuit): r for r in df.itertuples()}
    nb, nc = len(ps.BOARD_ORDER), len(ps.CIRCUIT_ORDER)
    fig, ax = plt.subplots(constrained_layout=True)
    handles = []
    for bi, b in enumerate(ps.BOARD_ORDER):
        for ci, c in enumerate(ps.CIRCUIT_ORDER):
            col = house.family(bi)[ci]               # board = colour family, circuit = shade (house palette)
            x = bi * (nc + 1) + ci
            r = rows.get((b, c))
            handles.append(Patch(color=col, label=f"{ps.BOARD_SHORT[b]} {c}"))
            if r is None:
                continue
            if r.flag == "none_in_range":     # no crossover up to the last common n: bar to that n, hatched, labelled
                top = int(str(r.common_n).split("..")[1])
                ax.bar(x, top, color=col, zorder=3)          # solid like the others; the label "> n" says that offload is not faster up to the last n before the wall
                ax.text(x, top + 0.2, f"> {top}", ha="center", va="bottom", fontsize=9)
                continue
            k = int(r.integer_n_star)     # n* rounded up: the first whole n at which offload is faster
            ax.bar(x, k, color=col, zorder=3)
            ax.text(x, k + 0.2, f"≤ {k}" if r.flag == "at_or_below_first_n" else f"{k}", ha="center", va="bottom",
                    fontsize=9)
    ax.set_xticks([bi * (nc + 1) + (nc - 1) / 2 for bi in range(nb)], [ps.BOARD_LABEL[b] for b in ps.BOARD_ORDER])
    ax.set_ylabel("First qubit count $n$ at which offload is faster than local")
    top = max(int(str(r.common_n).split("..")[1]) for r in df.itertuples() if str(r.common_n).count("..") == 1)      # the largest n measured before a memory wall
    ax.set_ylim(0, top + 1.3)
    ax.set_yticks(sorted(set(range(0, top + 1, 2 if top > 8 else 1)) | {top}))      # the last tick is the largest n before a wall
    leg = ax.legend(handles=handles, loc="upper left", ncol=nb)
    leg.set_zorder(2.4)
    gd.footnote(fig, "n* by log-linear interpolation of offload vs local medians (phase4_decision_rule.py), rounded up to a whole n; "
                     "> n = offload is not faster up to the last n measured before the memory wall; ≤ n = already faster at the first n measured.")
    out = gd.REPO_ROOT / "data" / "figures" / "phase4" / "all_boards_all_circuits.png"
    house.save_figure(fig, str(out))
    print(out)


if __name__ == "__main__":
    main()
