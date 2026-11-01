#!/usr/bin/env python3
# timer_vs_counter_house_plots.py
# Per board: time per run from the external reference counter (solid) and from the board's own timer, micros() (dashed), one colour per board
# (µs, log scale, point medians) vs n, one chart per circuit with the three boards, in the house line-chart style of the graph-create skill
# (same layout as analysis/algorithm_house_plots.py: no title, legend = board names, linear y). Only points whose counter pair passed the validity rules
# (usable) in the selected sessions are drawn (data/derived/counter_validity.csv, read-only); the line is drawn straight over unusable points.
#   data/figures/phase2/timer_vs_counter/<circuit>.png   data/figures/phase3/timer_vs_counter/<circuit>.png
#   Use:  .venv/bin/python analysis/timer_vs_counter_house_plots.py
import glob
import os
import sys

import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
cands = glob.glob(os.path.expanduser("~/.claude/skills/synced/*/graph-create/scripts"))
if not cands:
    sys.exit("graph-create skill not found under ~/.claude/skills/synced/*/graph-create")
sys.path.insert(0, cands[0])
from plot_style import FAMILIES, plot_grouped_lines, save_figure  # noqa: E402

cv = pd.read_csv(os.path.join(ROOT, "data", "derived", "counter_validity.csv"))
cv = cv[cv.selected.astype(bool) & cv.usable.astype(bool) & (cv.counter_median_us > 0) & (cv.micros_median_us > 0)]
NAME = {"uno": "Uno", "esp8266": "ESP8266", "esp32": "ESP32"}
for ph in (2, 3):
    for c in ("h_all", "bell_ghz", "qft", "grover"):
        g = cv[(cv.phase == ph) & (cv.circuit == c)]
        SER = ["reference counter", "on-board timer"]
        STYLE = {"reference counter": "-", "on-board timer": "--"}
        rows = []
        for r in g.sort_values(["board", "n"]).itertuples():
            for lab, v in zip(SER, (r.counter_median_us, r.micros_median_us)):
                rows.append({"n": int(r.n), "time_us": float(v), "board": NAME[r.board], "series": lab})
        df = pd.DataFrame(rows)
        fig, ax = plot_grouped_lines(df, "n", "time_us", "board", "series", title="", xlabel="Number of qubits, $n$",
                                     ylabel=r"Time per run (µs, log scale)",
                                     group_order=list(NAME.values()), series_order=SER)
        for ln in ax.lines:                                   # one colour per board; line style tells the clock
            lab = ln.get_label()
            for gi, bn in enumerate(NAME.values()):
                if lab.startswith(bn + " "):
                    kind = lab[len(bn) + 1:]
                    ln.set_linestyle(STYLE[kind])
                    if kind == "on-board timer":      # dark shade of the board's colour, thinner and on top, so it stays visible over the (almost equal) counter line
                        ln.set_color(FAMILIES[gi][3])
                        ln.set_linewidth(1.4)
                        ln.set_zorder(4)
                        ln.set_dashes((4, 3))
                    else:
                        ln.set_color(FAMILIES[gi][0])
        ax.legend(loc="upper left", ncol=3, fontsize=8.5, framealpha=0.9)
        lo, hi = df.time_us.min(), df.time_us.max()
        lo_e = int(np.floor(np.log10(lo)))
        ax.set_ylim(10.0 ** lo_e, 10.0 ** (np.log10(hi) + 0.13 * (np.log10(hi) - lo_e)))   # whole decade below, headroom for the legend
        ax.yaxis.set_major_locator(mticker.LogLocator(base=10, numticks=30))
        ax.yaxis.set_major_formatter(mticker.LogFormatterMathtext(base=10))
        ax.yaxis.set_minor_locator(mticker.LogLocator(base=10, subs=np.arange(2, 10), numticks=60))
        ax.yaxis.set_minor_formatter(mticker.NullFormatter())
        ax.tick_params(axis="y", which="minor", length=3, direction="out")
        # lower panel: the difference itself, on-board timer minus reference counter (signed, symmetric-log axis: linear within +-10 µs)
        fig.set_size_inches(9.4, 8.4)
        pos = ax.get_position()
        ax.set_position([pos.x0, pos.y0 + 0.36 * pos.height, pos.width, 0.64 * pos.height])
        ax.set_xlabel("")
        ax.tick_params(axis="x", labelbottom=False)
        ax2 = fig.add_axes([pos.x0, pos.y0, pos.width, 0.28 * pos.height], sharex=ax)
        for gi, bn in enumerate(NAME.values()):
            gg = g[g.board == {v: k for k, v in NAME.items()}[bn]].sort_values("n")
            if len(gg):
                ax2.plot(gg.n, gg.micros_median_us - gg.counter_median_us, color=FAMILIES[gi][0], lw=2.0)
        ax2.axhline(0, color="0.4", lw=0.8)
        ax2.set_yscale("symlog", linthresh=10)
        ax2.margins(y=0.10)
        ax2.set_xlabel("Number of qubits, $n$")
        ax2.set_ylabel("On-board timer $-$\nreference counter (µs)")
        ax2.tick_params(axis="both", direction="out", length=5)
        out = os.path.join(ROOT, "data", "figures", f"phase{ph}", "timer_vs_counter", f"{c}.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        save_figure(fig, out)
        print(out)
