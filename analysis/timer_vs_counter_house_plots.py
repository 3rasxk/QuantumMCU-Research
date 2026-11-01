#!/usr/bin/env python3
# timer_vs_counter_house_plots.py
# micros() / counter ratio of the point medians vs n, one chart per circuit with the three boards, in the house line-chart style of the graph-create skill
# (same layout as analysis/algorithm_house_plots.py: no title, legend = board names, linear y). Only points whose counter pair passed the validity rules
# (usable) in the selected sessions are drawn (data/derived/counter_validity.csv, read-only); the line is drawn straight over unusable points.
#   data/figures/phase2/timer_vs_counter/<circuit>.png   data/figures/phase3/timer_vs_counter/<circuit>.png
#   Use:  .venv/bin/python analysis/timer_vs_counter_house_plots.py
import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
cands = glob.glob(os.path.expanduser("~/.claude/skills/synced/*/graph-create/scripts"))
if not cands:
    sys.exit("graph-create skill not found under ~/.claude/skills/synced/*/graph-create")
sys.path.insert(0, cands[0])
from plot_style import plot_grouped_lines, save_figure  # noqa: E402

cv = pd.read_csv(os.path.join(ROOT, "data", "derived", "counter_validity.csv"))
cv = cv[cv.selected.astype(bool) & cv.usable.astype(bool) & (cv.counter_median_us > 0) & (cv.micros_median_us > 0)]
cv = cv.assign(ratio=cv.micros_median_us / cv.counter_median_us)
NAME = {"uno": "Uno", "esp8266": "ESP8266", "esp32": "ESP32"}
for ph in (2, 3):
    for c in ("h_all", "bell_ghz", "qft", "grover"):
        g = cv[(cv.phase == ph) & (cv.circuit == c)]
        rows = [{"n": int(r.n), "ratio": float(r.ratio), "board": NAME[r.board], "series": "ratio"} for r in g.sort_values(["board", "n"]).itertuples()]
        df = pd.DataFrame(rows)
        fig, ax = plot_grouped_lines(df, "n", "ratio", "board", "series", title="", xlabel="Number of qubits, $n$",
                                     ylabel=r"micros() / counter (per-point medians)", log_y=False,
                                     group_order=list(NAME.values()), series_order=["ratio"])
        for t in ax.get_legend().get_texts():
            t.set_text(t.get_text().replace(" ratio", ""))
        lo, hi = min(df.ratio.min(), 1.0) - 0.01, max(df.ratio.max(), 1.0) + 0.01   # always shows ratio 1 and at least +-1 %: a 0.1 % spread must not look large
        ax.set_ylim(lo, hi + 0.25 * (hi - lo))                                       # headroom for the legend
        out = os.path.join(ROOT, "data", "figures", f"phase{ph}", "timer_vs_counter", f"{c}.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        save_figure(fig, out)
        print(out)
