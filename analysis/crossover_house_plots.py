#!/usr/bin/env python3
# crossover_house_plots.py (added after the data were seen; existing data only, selected sessions, in-scope n)
# One chart per board x circuit (12 files) in the house line-chart style of the graph-create skill (analysis/vendor/plot_style.py): grouped log-y lines,
# no markers, no bands; group = path (Local / Offload), series = the lines of the path.
#   Local   : median execution time per run (Phase 2, board micros())
#   Offload : fast PC bound, slow PC bound (wire + the board's residual + the fastest / slowest observed PC simulation) and the measured session (Phase 3)
# Departures from the plain style, added because the chart is about the crossover (all drawn with the Python API of the style, nothing else changed):
#   * the crossover bracket of each PC bound as a light vertical span between the two measured n (fast: gold, slow: red; one span when both are equal),
#     stated again in the title; "none" = no crossover up to the largest measured n; an arrow-less "<=n" = offload already faster at the smallest measured n
#   * the memory wall (positive evidence only) as a dotted vertical line.
# IQR, weak points (hollow markers) and the within-noise labels are not drawn (the style has no markers or bands): see figures/phase4/F4_crossover_by_circuit.pdf.
# Output: data/figures/phase4/crossover/<board>_<circuit>.png     Use:  .venv/bin/python analysis/crossover_house_plots.py
import os
import sys

import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "vendor"))          # vendored graph-create style (analysis/vendor/plot_style.py)
sys.path.insert(0, os.path.join(HERE, "phase4"))
from plot_style import FAMILIES, plot_grouped_lines, save_figure  # noqa: E402
import p4common as C  # noqa: E402
import offload_band as OB  # noqa: E402

OUT = os.path.join(ROOT, "data", "figures", "phase4", "crossover")
SERIES = ["Fast PC bound", "Slow PC bound", "Measured session", "Phase 2 median"]     # order = shade order of the family (orange base, red, gold; navy for the local line)
NAME = {"uno": "Uno R3", "esp8266": "ESP8266", "esp32": "ESP32"}


def bracket_text(lo, hi, kind):
    return "none" if kind == "none" else f"<={int(hi)}" if kind == "below" else f"{int(lo)}-{int(hi)}"


def main():
    m, _, _ = OB.band_table()
    X = OB.crossover_table(m)
    loc = C.load_local()
    walls = {}
    for r in C.load_walls().itertuples():
        walls.setdefault((r.board, r.circuit), int(r.n))
    os.makedirs(OUT, exist_ok=True)
    for b in C.BOARDS:
        for c in C.CIRCUITS:
            g = loc[(loc.board == b) & (loc.circuit == c)].sort_values("n")
            o = m[(m.board == b) & (m.circuit == c)].sort_values("n")
            rows = [{"n": int(n), "time_us": float(t), "path": "Local", "series": "Phase 2 median"} for n, t in zip(g.n, g.median_us)]
            for col, lab in (("fast_us", "Fast PC bound"), ("slow_us", "Slow PC bound"), ("e2e_us", "Measured session")):
                rows += [{"n": int(n), "time_us": float(t), "path": "Offload", "series": lab} for n, t in zip(o.n, o[col])]
            df = pd.DataFrame(rows)
            df = df[df.time_us > 0]
            xr = X[(X.board == b) & (X.circuit == c)].iloc[0]
            br = {bd: (xr[f"n_{bd}_lo"], xr[f"n_{bd}_hi"], xr[f"{bd}_kind"]) for bd in ("fast", "slow")}
            title = f"Phase 4 -- {NAME[b]}, {c}: local vs offload\ncrossover bracket: fast PC {bracket_text(*br['fast'])}, slow PC {bracket_text(*br['slow'])}"
            fig, ax = plot_grouped_lines(df, "n", "time_us", "path", "series", title=title, xlabel="Number of qubits, $n$",
                                         ylabel="Time per run (µs, log scale)", group_order=["Local", "Offload"], series_order=SERIES,
                                         legend_label="{group} {series}")
            for t in ax.get_legend().get_texts():                      # "Local Phase 2 median" -> "Local (Phase 2, median)"; "Offload Fast PC bound" -> "Offload, fast PC bound (Phase 3)"
                s = t.get_text()
                t.set_text("Local (Phase 2, median)" if s.startswith("Local") else "Offload, " + s.split(" ", 1)[1][0].lower() + s.split(" ", 1)[1][1:] + " (Phase 3)")
            same = br["fast"] == br["slow"] or (br["fast"][2] == br["slow"][2] == "bracket" and tuple(br["fast"][:2]) == tuple(br["slow"][:2]))
            for bd, col in (("fast", FAMILIES[1][2]), ("slow", FAMILIES[1][1])):
                if bd == "slow" and same:
                    continue
                lo, hi, kind = br[bd]
                if kind == "bracket":
                    ax.axvspan(lo, hi, color=col, alpha=0.22, lw=0, zorder=0.5)
                elif kind == "below":
                    ax.axvspan(hi - 0.5, hi, color=col, alpha=0.22, lw=0, zorder=0.5)
            if (b, c) in walls:
                ax.axvline(walls[(b, c)], color="0.35", ls=":", lw=1.2, zorder=0.6)
                ax.text(walls[(b, c)], 0.5, f"memory wall, n={walls[(b, c)]} ", rotation=90, va="center", ha="right", fontsize=8, color="0.25",
                        transform=ax.get_xaxis_transform(), bbox=dict(fc="white", ec="none", pad=1.0))      # mid-height: the legend sits in a corner
            # y axis fitted to the data (a label at every decade, as in the other house charts)
            lo_e = int(np.floor(np.log10(df.time_us.min())))
            hi_l = np.log10(df.time_us.max())
            ax.set_ylim(10.0 ** lo_e, 10.0 ** (hi_l + 0.2 * (hi_l - lo_e)))
            ax.yaxis.set_major_locator(mticker.LogLocator(base=10, numticks=30))
            ax.yaxis.set_major_formatter(mticker.LogFormatterSciNotation(base=10))
            out = os.path.join(OUT, f"{b}_{c}.png")
            save_figure(fig, out)
            print(out)


if __name__ == "__main__":
    main()
