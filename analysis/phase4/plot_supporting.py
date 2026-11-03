#!/usr/bin/env python3
"""Supporting trade-off figures (added after the data were seen; existing data only, selected sessions, in-scope n).

    .venv/bin/python analysis/phase4/plot_supporting.py
      figures/phase4/F7_ratio.{pdf,png}       T_local / T_offload vs n, one line per board, per circuit; band = ratio under the slow and the fast PC bound
      figures/phase4/F8_breakdown.{pdf,png}   share of the offload round trip (wire, board-and-link residual, PC simulation), medians, one board

F7: the ratio of the Phase 2 local median to the measured offload median of the selected Phase 3 session (line), with the range obtained from the
fast and the slow offload bound (band); above 1 local is slower than offload. Weak points are hollow.
F8: share-of-total stacked bars (not absolute log-y bars) because the three parts span five decades and the question is which part dominates; the board is
the ESP32 (widest n range, all four circuits). The parts are medians of one point and do not add exactly, so the total is their sum. A negative residual
(one weak ESP32 grover point) is drawn as zero and marked with an asterisk.
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
import offload_band as OB  # noqa: E402

plt = MF.plt
COL, MRK = MF.COL, MF.MRK
BREAKDOWN_BOARD = "esp32"
PART_COL = {"wire": "#56B4E9", "residual": "#E69F00", "pc_sim": "#CC79A7"}


def f7_ratio(m):
    fig, axs = plt.subplots(2, 2, figsize=(MF.W2, 4.6), sharex=True)
    for ax, c in zip(axs.flat, C.CIRCUITS):
        for b in C.BOARDS:
            g = m[(m.board == b) & (m.circuit == c)].sort_values("n")
            ax.fill_between(g.n, g.median_us / g.slow_us, g.median_us / g.fast_us, color=COL[b], alpha=0.25, lw=0)
            ax.plot(g.n, g.median_us / g.e2e_us, color=COL[b], lw=1.0)
            wk = g.weak_point
            ax.plot(g.n[~wk], (g.median_us / g.e2e_us)[~wk], ls="", marker=MRK[c], color=COL[b], mfc=COL[b], ms=3.2)
            ax.plot(g.n[wk], (g.median_us / g.e2e_us)[wk], ls="", marker=MRK[c], color=COL[b], mfc="white", mew=0.9, ms=4.6)
        ax.axhline(1.0, color="k", lw=0.8)
        MF.log_ticks(ax)
        ax.set_xlim(1.5, 14.5)
        ax.set_xticks(range(2, 15, 2))
        ax.text(0.03, 0.96, c, transform=ax.transAxes, ha="left", va="top", fontsize=8)
    for ax in axs[1]:
        ax.set_xlabel("Qubits $n$")
    for ax in axs[:, 0]:
        ax.set_ylabel(r"$T_{\rm local}/T_{\rm offload}$")
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    hs = MF.board_handles() + [Line2D([], [], color="k", lw=0.8, label="ratio 1 (crossover)"),
                               Patch(facecolor="gray", alpha=0.3, label="range: slow to fast PC bound"),
                               Line2D([], [], color="gray", marker="o", mfc="white", ls="", ms=5, label=f"weak: $<{C.SMALL_REPS}$ independent reps / requests")]
    fig.legend(handles=hs, loc="upper center", ncol=6, frameon=False, bbox_to_anchor=(0.5, 1.0), columnspacing=0.9, handletextpad=0.4)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    MF.save(fig, "F7_ratio")


def f8_breakdown(m):
    fig, axs = plt.subplots(2, 2, figsize=(MF.W2, 4.4), sharex=True, sharey=True)
    for ax, c in zip(axs.flat, C.CIRCUITS):
        g = m[(m.board == BREAKDOWN_BOARD) & (m.circuit == c)].sort_values("n")
        parts = {"wire": g.wire_us.to_numpy(), "residual": np.clip(g.residual_us.to_numpy(), 0, None), "pc_sim": g.pc_sim_us.to_numpy()}
        tot = sum(parts.values())
        bottom = np.zeros(len(g))
        for k in ("wire", "residual", "pc_sim"):
            ax.bar(g.n, parts[k] / tot, bottom=bottom, color=PART_COL[k], width=0.8, lw=0)
            bottom += parts[k] / tot
        for n, r in zip(g.n, g.residual_us):
            if r < 0:
                ax.text(n, 1.02, "*", ha="center", va="bottom", fontsize=8)
        ax.set_xlim(1.4, 14.6)
        ax.set_ylim(0, 1.08)
        ax.set_xticks(range(2, 15, 2))
        ax.text(0.03, 0.96, c, transform=ax.transAxes, ha="left", va="top", fontsize=8, bbox=dict(fc="white", ec="none", alpha=0.7, pad=1))
    for ax in axs[1]:
        ax.set_xlabel("Qubits $n$")
    for ax in axs[:, 0]:
        ax.set_ylabel("Share of the round trip")
    from matplotlib.patches import Patch
    hs = [Patch(color=PART_COL["wire"], label="wire (serial)"), Patch(color=PART_COL["residual"], label="board and link residual"),
          Patch(color=PART_COL["pc_sim"], label="PC simulation")]
    fig.legend(handles=hs, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.0))
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    MF.save(fig, "F8_breakdown")


def main():
    m, _, _ = OB.band_table()
    f7_ratio(m)
    f8_breakdown(m)
    print("wrote figures/phase4/F7_ratio, F8_breakdown")


if __name__ == "__main__":
    main()
