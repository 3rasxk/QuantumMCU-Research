#!/usr/bin/env python3
# phase1_house_plots.py
# Phase 1 (PC build, C++ simulator vs Qiskit Aer; no board, one deterministic run per point) in the house line-chart style of the graph-create skill.
# Reads data/processed/phase4/phase1_infidelity.csv (made by analysis/phase4/audit.py from data/raw/phase1; read-only). One dashed line marks the 1e-3 pass
# threshold on the infidelity charts. Output (same file names as before, written over them):
#   data/figures/phase1/infidelity_vs_depth.png   infidelity vs circuit depth (log x), all circuits
#   data/figures/phase1/tvd_vs_depth.png          total variation distance vs circuit depth
#   data/figures/phase1/phase1_accuracy.png       infidelity vs number of qubits, all circuits
#   data/figures/phase1/<circuit>/infidelity_tvd.png   infidelity and TVD vs number of qubits for one circuit
#   Use:  .venv/bin/python analysis/phase1_house_plots.py
import glob
import os
import sys

import matplotlib.ticker as mt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
cands = glob.glob(os.path.expanduser("~/.claude/skills/synced/*/graph-create/scripts"))
if not cands:
    sys.exit("graph-create skill not found under ~/.claude/skills/synced/*/graph-create")
sys.path.insert(0, cands[0])
from plot_style import plot_grouped_lines, save_figure  # noqa: E402

d = pd.read_csv(os.path.join(ROOT, "data", "processed", "phase4", "phase1_infidelity.csv"))
LAB = {"h_all": "H-all", "bell_ghz": "Bell/GHZ", "qft": "QFT", "grover": "Grover"}
ORDER = [LAB[c] for c in ("h_all", "bell_ghz", "qft", "grover")]
THRESH = 1e-3
out_dir = os.path.join(ROOT, "data", "figures", "phase1")


def fit_y(ax, lo, hi):
    """y limits on whole decades below, headroom above for the legend, a label at every decade, minor ticks 2..9"""
    lo_e = int(np.floor(np.log10(lo)))
    ax.set_ylim(10.0 ** lo_e, 10.0 ** (np.log10(hi) + 0.17 * (np.log10(hi) - lo_e)))
    ax.yaxis.set_major_locator(mt.LogLocator(base=10, numticks=30))
    ax.yaxis.set_major_formatter(mt.LogFormatterMathtext(base=10))
    ax.yaxis.set_minor_locator(mt.LogLocator(base=10, subs=np.arange(2, 10), numticks=60))
    ax.yaxis.set_minor_formatter(mt.NullFormatter())
    ax.tick_params(axis="y", which="minor", length=3, direction="out")


def add_threshold(ax):
    ax.axhline(THRESH, color="0.35", lw=1.2, ls="--", zorder=1)
    hs, ls = ax.get_legend_handles_labels()
    hs.append(Line2D([], [], color="0.35", lw=1.2, ls="--"))
    ls.append(r"pass threshold ($10^{-3}$)")
    ax.legend(hs, ls, loc="upper left", ncol=3, fontsize=9, framealpha=0.9)


def one_series(df, x, y, xlabel, ylabel, name, x_scale=None, threshold=False):
    df = df.assign(series="v", group=df.circuit.map(LAB))
    fig, ax = plot_grouped_lines(df, x, y, "group", "series", title="", xlabel=xlabel, ylabel=ylabel,
                                 group_order=ORDER, series_order=["v"], x_scale=x_scale, integer_x=(x_scale is None),
                                 legend_label="{group}")
    fit_y(ax, df[y].min(), max(df[y].max(), THRESH if threshold else 0))
    if threshold:
        add_threshold(ax)
    save_figure(fig, os.path.join(out_dir, name))
    print(os.path.join(out_dir, name))


d = d.sort_values(["circuit", "n"])
one_series(d, "depth", "infidelity", "Circuit depth (gate layers, log scale)", "Infidelity, $1-F$ (log scale)", "infidelity_vs_depth.png",
           x_scale="log10", threshold=True)
one_series(d, "depth", "tvd", "Circuit depth (gate layers, log scale)", "Total variation distance, TVD (log scale)", "tvd_vs_depth.png", x_scale="log10")
one_series(d, "n", "infidelity", "Number of qubits, $n$", "Infidelity, $1-F$ (log scale)", "phase1_accuracy.png", threshold=True)

for c, g in d.groupby("circuit"):
    rows = []
    for r in g.itertuples():
        rows.append({"n": int(r.n), "v": float(r.infidelity), "group": LAB[c], "series": "infidelity"})
        rows.append({"n": int(r.n), "v": float(r.tvd), "group": LAB[c], "series": "TVD"})
    df = pd.DataFrame(rows)
    fig, ax = plot_grouped_lines(df, "n", "v", "group", "series", title="", xlabel="Number of qubits, $n$",
                                 ylabel="Distance from Qiskit Aer (log scale)", group_order=[LAB[c]], series_order=["infidelity", "TVD"],
                                 legend_label="{series}")
    fit_y(ax, df.v.min(), max(df.v.max(), THRESH))
    add_threshold(ax)
    p = os.path.join(out_dir, c, "infidelity_tvd.png")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    save_figure(fig, p)
    print(p)
