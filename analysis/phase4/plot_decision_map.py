#!/usr/bin/env python3
"""Decision map (added after the data were seen; existing data only): per circuit (4 small panels), x = n, y = board, one coloured cell per (board, n).

    .venv/bin/python analysis/phase4/plot_decision_map.py      -> figures/phase4/F6_decision_map.{pdf,png}

The cells come from tradeoff.cells(), which reads the same crossover table (offload_band.crossover_table) as Table III of the paper; the test
analysis/phase4/tradeoff_test.py checks the two against each other for every board x circuit x n.
Classes: local faster (both PC bounds), offload faster (both PC bounds), depends on PC speed (the fast and the slow bound disagree), within noise
(an end of a bracket labelled within noise), not runnable on board (n at or beyond the board's wall, or beyond its local time limit), not measured.
"""
import os
import sys

import matplotlib
import numpy as np

matplotlib.use("Agg")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_figures as MF  # noqa: E402
import p4common as C  # noqa: E402
import tradeoff as TO  # noqa: E402

plt = MF.plt
# Okabe-Ito based, colour-blind safe; the two "no" classes are neutral greys with different lightness
PAL = {TO.LOCAL: "#0072B2", TO.OFFLOAD: "#D55E00", TO.DEPENDS: "#F0E442", TO.NOISE: "#CC79A7", TO.NORUN: "#4D4D4D", TO.NOMEAS: "#E6E6E6"}
ORDER = [TO.LOCAL, TO.OFFLOAD, TO.DEPENDS, TO.NOISE, TO.NORUN, TO.NOMEAS]


def main():
    cells = TO.cells()
    cells.to_csv(os.path.join(C.PROC, "decision_cells.csv"), index=False)
    fig, axs = plt.subplots(2, 2, figsize=(MF.W2, 3.4), sharex=True, sharey=True)
    ns = TO.GRID_N
    for ax, c in zip(axs.flat, C.CIRCUITS):
        for yi, b in enumerate(C.BOARDS):
            g = cells[(cells.board == b) & (cells.circuit == c)].set_index("n")
            for xi, n in enumerate(ns):
                cl = g.loc[n, "cell"]
                ax.add_patch(plt.Rectangle((xi - 0.5, yi - 0.5), 1, 1, facecolor=PAL[cl], edgecolor="white", lw=0.8))
        ax.set_xlim(-0.5, len(ns) - 0.5)
        ax.set_ylim(len(C.BOARDS) - 0.5, -0.5)
        ax.set_xticks(range(len(ns)))
        ax.set_xticklabels(ns)
        ax.set_yticks(range(len(C.BOARDS)))
        ax.set_yticklabels([C.BOARD_LABEL[b] for b in C.BOARDS])
        ax.tick_params(length=2, labelsize=7.5)
        ax.set_title(c, fontsize=9, loc="left", pad=2)
    for ax in axs[1]:
        ax.set_xlabel("Qubits $n$", fontsize=8)
    from matplotlib.patches import Patch
    hs = [Patch(facecolor=PAL[k], edgecolor="0.5", lw=0.4, label=TO.CELL_LABEL[k]) for k in ORDER]
    fig.legend(handles=hs, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.0), columnspacing=1.0, handletextpad=0.5, fontsize=7.5)
    fig.tight_layout(rect=(0, 0.17, 1, 1))
    MF.save(fig, "F6_decision_map")
    print("wrote figures/phase4/F6_decision_map;", cells.cell.value_counts().to_dict())


if __name__ == "__main__":
    main()
