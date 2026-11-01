#!/usr/bin/env python3
# algorithm_house_plots.py
# One chart per circuit (three boards), in the house line-chart style of the graph-create skill (grouped log-y lines, no markers); group = board.
# EVERY time here is the ESP32 reference counter's median pulse width of the point (data/derived/counter_validity.csv, selected sessions); the
# board's own micros() is never drawn. Only points whose counter pair passed the validity rules (usable) are drawn; where a point is unusable the
# line is drawn straight between the neighbouring usable points (no marker, so the gap is not visible: see the list printed at the end).
#   data/figures/phase2/algorithms/<circuit>.png  Phase 2 only: local time per run
#   data/figures/phase3/algorithms/<circuit>.png  Phase 3 only: offload round trip per request
#   data/figures/phase4/algorithms/<circuit>.png  Phase 4: Phase 2 local with Phase 3 offload, at the n where both are usable
# Weak points, IQR and crossover brackets are not drawn (the style has no markers or bands); see figures/phase4/F4_offload_crossover.pdf for those.
# Reads data/processed/phase4/offload_band.csv (read-only). Output: data/figures/phase2/<circuit>_local_vs_offload.png
#   Use:  .venv/bin/python analysis/phase4_algorithm_house_plots.py
import glob
import os
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
cands = glob.glob(os.path.expanduser("~/.claude/skills/synced/*/graph-create/scripts"))
if not cands:
    sys.exit("graph-create skill not found under ~/.claude/skills/synced/*/graph-create")
sys.path.insert(0, cands[0])
from plot_style import plot_grouped_lines, save_figure  # noqa: E402

cv = pd.read_csv(os.path.join(ROOT, "data", "derived", "counter_validity.csv"))
cv = cv[cv.selected.astype(bool) & cv.usable.astype(bool) & (cv.counter_median_us > 0)]
NAME = {"uno": "Uno", "esp8266": "ESP8266", "esp32": "ESP32"}
CIRC = ("h_all", "bell_ghz", "qft", "grover")
PHASES = {2: ("Phase 2 -- {c}, local (counter)", [("local", 2)], "Time per run (µs, log scale; counter)"),
          3: ("Phase 3 -- {c}, offload (counter)", [("round trip", 3)], "Time per request (µs, log scale; counter)"),
          4: ("Phase 4 -- {c}, local vs offload (counter)", [("local", 2), ("offload", 3)], "Time per run (µs, log scale; counter)")}
for ph, (title, SER, ylab) in PHASES.items():
    for c in CIRC:
        rows = []
        for b in NAME:
            have = {}
            for lab, src in SER:
                g = cv[(cv.phase == src) & (cv.board == b) & (cv.circuit == c)]
                have[lab] = dict(zip(g.n.astype(int), g.counter_median_us))
            ns = set.intersection(*[set(v) for v in have.values()]) if ph == 4 else None
            for lab, _ in SER:
                rows += [{"n": n, "time_us": float(t), "board": NAME[b], "series": lab} for n, t in sorted(have[lab].items()) if ns is None or n in ns]
        df = pd.DataFrame(rows)
        fig, ax = plot_grouped_lines(df, "n", "time_us", "board", "series", title=title.format(c=c), xlabel="Number of qubits, $n$", ylabel=ylab,
                                     group_order=list(NAME.values()), series_order=[s for s, _ in SER])
        out = os.path.join(ROOT, "data", "figures", f"phase{ph}", "algorithms", f"{c}.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        save_figure(fig, out)
        print(out)
