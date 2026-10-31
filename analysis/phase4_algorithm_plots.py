#!/usr/bin/env python3
# phase4_algorithm_plots.py
# One local-vs-offload panel per circuit with the three boards together, in the style of the F4 panels of the paper: local median with IQR (solid, markers, Phase 2),
# offload band between the fastest and the slowest observed PC simulation (hatched) with the measured offload median (dashed), crossover bracket bars
# (solid = fast bound, dotted = slow bound), hollow markers = weak points (< 30 reps / requests).
# Reads data/processed/phase4/offload_band.csv and offload_crossover.csv (run analysis/phase4/make_figures.py or analysis/reproduce.py first); read-only.
# Output: figures/algorithms/<circuit>.png   Use:  .venv/bin/python analysis/phase4_algorithm_plots.py
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
P = os.path.join(ROOT, "data", "processed", "phase4")
COL = {"uno": "#0072B2", "esp8266": "#E69F00", "esp32": "#009E73"}
MRK = {"h_all": "o", "bell_ghz": "s", "qft": "^", "grover": "D"}
LAB = {"uno": "Arduino Uno R3", "esp8266": "ESP8266", "esp32": "ESP32"}
plt.rcParams.update({"font.family": "serif", "font.serif": ["STIXGeneral", "DejaVu Serif"], "mathtext.fontset": "cm", "font.size": 9,
                     "axes.linewidth": 0.8, "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white"})

band = pd.read_csv(os.path.join(P, "offload_band.csv"))
xo = pd.read_csv(os.path.join(P, "offload_crossover.csv"))
written = 0
for c in ("h_all", "bell_ghz", "qft", "grover"):
    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    anyweak = False
    for b in ("uno", "esp8266", "esp32"):
        g = band[(band.board == b) & (band.circuit == c)].sort_values("n")
        row = xo[(xo.board == b) & (xo.circuit == c)].iloc[0]
        col = COL[b]
        ax.fill_between(g.n, g.q1_us, g.q3_us, color=col, alpha=0.30, lw=0)
        ax.plot(g.n, g.median_us, color=col, lw=1.4, marker=MRK[c], mfc=col, ms=5)
        ax.fill_between(g.n, g.fast_us, g.slow_us, color=col, alpha=0.18, lw=0, hatch="////", edgecolor=col)
        ax.plot(g.n, g.e2e_us, color=col, lw=1.2, ls="--")
        wk = g[g.weak_point]
        if len(wk):
            anyweak = True
            ax.plot(wk.n, wk.median_us, ls="", marker=MRK[c], mfc="white", mec=col, mew=1.2, ms=7)
        for bound, ls_ in (("fast", "-"), ("slow", ":")):
            lo, hi, kind = row[f"n_{bound}_lo"], row[f"n_{bound}_hi"], row[f"{bound}_kind"]
            if kind == "bracket":
                y = float(g[g.n == int(hi)].median_us.iloc[0])
                ax.plot([lo, hi], [y, y], color=col, lw=3.4, ls=ls_, solid_capstyle="butt", zorder=5)
            elif kind == "below":
                y = float(g[g.n == int(hi)].median_us.iloc[0])
                ax.annotate("", xy=(hi, y), xytext=(hi - 0.9, y), arrowprops=dict(arrowstyle="->", color=col, lw=1.6, ls=ls_))
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(matplotlib.ticker.LogFormatterMathtext())
    ax.set_xlim(1.5, band[band.circuit == c].n.max() + 0.5)
    ax.set_xticks(range(2, int(band[band.circuit == c].n.max()) + 1))
    ax.set_xlabel("Qubits $n$")
    ax.set_ylabel(r"Time per run ($\mu$s)")
    ax.text(0.03, 0.95, c, transform=ax.transAxes, ha="left", va="top", fontsize=11)
    hs = [Line2D([], [], color=COL[b], lw=1.6, label=LAB[b]) for b in COL]
    hs += [Line2D([], [], color="gray", lw=1.2, label="local median, IQR shaded (Phase 2)"),
           Patch(facecolor="gray", alpha=0.25, hatch="////", edgecolor="gray", label="offload band: fastest to slowest PC simulation"),
           Line2D([], [], color="gray", lw=1.2, ls="--", label="offload, measured session (Phase 3)"),
           Line2D([], [], color="gray", lw=3.4, label="crossover bracket, fast bound"),
           Line2D([], [], color="gray", lw=3.4, ls=":", label="crossover bracket, slow bound")]
    if anyweak:
        hs.append(Line2D([], [], color="gray", marker=MRK[c], mfc="white", ls="", ms=7, label="weak: < 30 reps / requests"))
    ax.legend(handles=hs, loc="lower right", fontsize=6.5, frameon=True, framealpha=0.9, ncol=2)
    fig.text(0.01, 0.005, "Offload band reflects the speed of the host PC (Aer simulation time varies about 2x between sessions). "
                          "No bar: no crossover up to the largest measured n; arrow: offload already faster at the smallest n.", fontsize=5.6, color="0.3")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    out = os.path.join(ROOT, "figures", "algorithms")
    os.makedirs(out, exist_ok=True)
    fig.savefig(os.path.join(out, f"{c}.png"), dpi=300)
    plt.close(fig)
    written += 1
print(written, "figures -> figures/algorithms/<circuit>.png")
