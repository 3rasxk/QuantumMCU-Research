#!/usr/bin/env python3
"""Crossover figure per circuit (added after the data were seen; existing data only, selected sessions, in-scope n).

    .venv/bin/python analysis/phase4/plot_crossover_by_circuit.py

Writes
  figures/phase4/F4_crossover_by_circuit.{pdf,png}     the paper figure: 4 panels (h_all, bell_ghz, qft, grover), three boards each
  data/figures/phase4/crossover/<board>_<circuit>.png  the 12 single-series versions (docs / appendix, not in the paper)
  data/processed/phase4/band_check.csv                 the shared-versus-per-board band check (see below)

Per board and circuit: local median with IQR (Phase 2, board micros()); offload band = wire + residual of that board + [PC simulation min, max]
over every Phase 3 session (Phase 3, 115 200 baud); memory wall (vertical dotted line, only where the wall has positive evidence); crossover
brackets as short bars above the x axis (solid = fast PC bound, dotted = slow PC bound; a left arrow = offload already faster at the smallest
measured n; no bar = none up to the largest measured n); hollow marker = weak point; dagger = bracket within noise, double dagger = a weak point in
or beyond the bracket.

Band check (decides shared band or one band per board): at every n with >= 2 boards, the spread of the fast and of the slow band edge between boards,
divided by the mean band height; if it exceeds BAND_TOL at any n the bands are drawn per board. The result is printed and stored.
"""
import os
import sys

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_figures as MF  # noqa: E402  (style, colours, markers, save)
import p4common as C  # noqa: E402
import offload_band as OB  # noqa: E402
import tradeoff as TO  # noqa: E402

plt = MF.plt
COL, MRK, W2 = MF.COL, MF.MRK, MF.W2
BAND_TOL = 0.10
OUT_DIR = os.path.join(C.ROOT, "data", "figures", "phase4", "crossover")


def band_decision(m):
    """-> (per_board: bool, DataFrame of the check, {circuit: max ratio})"""
    chk = TO.band_check(m)
    mx = chk.groupby("circuit").ratio.max().to_dict()
    return bool(any(v > BAND_TOL for v in mx.values())), chk, mx


def draw_series(ax, b, c, loc, m, X, walls, bar_slot, label_noise=True):
    """one board x circuit on ax; bar_slot = vertical slot (0, 1, 2) of its crossover bars above the x axis"""
    g = loc[(loc.board == b) & (loc.circuit == c)].sort_values("n")
    ax.fill_between(g.n, g.q1_us, g.q3_us, color=COL[b], alpha=0.30, lw=0)
    ax.plot(g.n, g.median_us, color=COL[b], lw=1.0)
    weak = g.reps < C.SMALL_REPS
    ax.plot(g.n[~weak], g.median_us[~weak], ls="", marker=MRK[c], color=COL[b], mfc=COL[b], ms=3.2)
    ax.plot(g.n[weak], g.median_us[weak], ls="", marker=MRK[c], color=COL[b], mfc="white", mew=0.9, ms=4.6)
    o = m[(m.board == b) & (m.circuit == c)].sort_values("n")
    ax.fill_between(o.n, o.fast_us, o.slow_us, color=COL[b], alpha=0.20, lw=0, hatch="////", edgecolor=COL[b])
    ax.plot(o.n, o.fast_us, color=COL[b], lw=0.5, alpha=0.7)
    ax.plot(o.n, o.slow_us, color=COL[b], lw=0.5, alpha=0.7)
    if (b, c) in walls:
        ax.axvline(walls[(b, c)], color=COL[b], ls=":", lw=1.0)
    xr = X[(X.board == b) & (X.circuit == c)].iloc[0]
    tr = matplotlib.transforms.blended_transform_factory(ax.transData, ax.transAxes)
    for k, (bound, ls_) in enumerate((("fast", "-"), ("slow", ":"))):
        y = 0.025 + 0.075 * bar_slot + 0.032 * k
        lo, hi, kind = xr[f"n_{bound}_lo"], xr[f"n_{bound}_hi"], xr[f"{bound}_kind"]
        lab = str(xr[f"{bound}_labels"])
        mark = ("†" if "within noise" in lab else "") + ("‡" if "weak" in lab else "")
        if kind == "bracket":
            ax.plot([lo, hi], [y, y], color=COL[b], lw=2.2, ls=ls_, transform=tr, solid_capstyle="butt", zorder=6)
            right = hi
        elif kind == "below":
            ax.annotate("", xy=(hi - 0.15, y), xytext=(hi + 0.55, y), xycoords=tr, textcoords=tr, arrowprops=dict(arrowstyle="->", color=COL[b], lw=1.2, ls=ls_))
            right = hi + 0.55
        else:
            right = None
        if right is not None and mark and label_noise:
            ax.text(right + 0.12, y, mark, transform=tr, fontsize=7.5, color=COL[b], va="center", ha="left")


def style_axes(ax, c):
    MF.log_ticks(ax)
    ax.set_xlim(1.5, 14.5)
    ax.set_xticks(range(2, 15, 2))
    ax.text(0.03, 0.96, c, transform=ax.transAxes, ha="left", va="top", fontsize=8)


def handles(per_board_band):
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    return MF.board_handles() + [
        Line2D([], [], color="gray", lw=1, label="local median, IQR shaded (Phase 2)"),
        Patch(facecolor="gray", alpha=0.25, hatch="////", edgecolor="gray",
              label="offload band, " + ("one per board: " if per_board_band else "") + "fast to slow PC (Phase 3)"),
        Line2D([], [], color="gray", ls=":", label="memory wall"),
        Line2D([], [], color="gray", lw=2.2, label="crossover bracket, fast PC"),
        Line2D([], [], color="gray", lw=2.2, ls=":", label="crossover bracket, slow PC"),
        Line2D([], [], color="gray", marker="o", mfc="white", ls="", ms=5, label=f"weak: $<{C.SMALL_REPS}$ independent reps / requests")]


def main():
    m, allp, _ = OB.band_table()
    X = OB.crossover_table(m)
    loc = C.load_local()
    walls = {}
    for _, r in C.load_walls().iterrows():
        walls.setdefault((r.board, r.circuit), int(r.n))
    per_board, chk, mx = band_decision(m)
    chk.to_csv(os.path.join(C.PROC, "band_check.csv"), index=False)
    print("band check (max spread / mean band height over n):", {c: round(v, 2) for c, v in mx.items()}, "-> per-board bands" if per_board else "-> one shared band")
    assert per_board, "the shared-band drawing is not implemented: the check says the bands do not differ"      # all four circuits exceed BAND_TOL

    fig, axs = plt.subplots(2, 2, figsize=(W2, 5.0), sharex=True)
    for ax, c in zip(axs.flat, C.CIRCUITS):
        for i, b in enumerate(C.BOARDS):
            draw_series(ax, b, c, loc, m, X, walls, i)
        style_axes(ax, c)
    for ax in axs[1]:
        ax.set_xlabel("Qubits $n$")
    for ax in axs[:, 0]:
        ax.set_ylabel(r"Time per run ($\mu$s)")
    fig.legend(handles=handles(True), loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.0), columnspacing=0.9, handletextpad=0.4)
    fig.tight_layout(rect=(0, 0, 1, 0.89))
    MF.save(fig, "F4_crossover_by_circuit")

    os.makedirs(OUT_DIR, exist_ok=True)
    for b in C.BOARDS:
        for c in C.CIRCUITS:
            fig, ax = plt.subplots(figsize=(MF.W1 * 1.5, 2.9))
            draw_series(ax, b, c, loc, m, X, walls, 0)
            style_axes(ax, f"{C.BOARD_LABEL[b]}, {c}")
            ax.set_xlabel("Qubits $n$")
            ax.set_ylabel(r"Time per run ($\mu$s)")
            fig.tight_layout()
            fig.savefig(os.path.join(OUT_DIR, f"{b}_{c}.png"), dpi=200, metadata=MF.META_PNG)
            plt.close(fig)
    print("wrote figures/phase4/F4_crossover_by_circuit and 12 files in", os.path.relpath(OUT_DIR, C.ROOT))


if __name__ == "__main__":
    main()
