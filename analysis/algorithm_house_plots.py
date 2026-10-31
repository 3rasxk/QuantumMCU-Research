#!/usr/bin/env python3
# algorithm_house_plots.py
# One chart per circuit (three boards), in the house line-chart style of the graph-create skill (grouped log-y lines, no markers); group = board.
#   data/figures/phase2/algorithms/<circuit>.png  Phase 2 only: local median time per run
#   data/figures/phase3/algorithms/<circuit>.png  Phase 3 only: offload round trip per request and the PC simulation part of it
#   data/figures/phase4/algorithms/<circuit>.png  Phase 4: Phase 2 local together with Phase 3 offload (fastest / slowest observed PC simulation)
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

band = pd.read_csv(os.path.join(ROOT, "data", "processed", "phase4", "offload_band.csv"))
NAME = {"uno": "Uno", "esp8266": "ESP8266", "esp32": "ESP32"}
PHASES = {
    2: ("Phase 2 -- {c}, local", [("local", "median_us")], "Time per run (µs, log scale)"),
    3: ("Phase 3 -- {c}, offload", [("round trip", "e2e_us"), ("PC simulation", "pc_sim_us")], "Time per request (µs, log scale)"),
    4: ("Phase 4 -- {c}, local vs offload", [("local", "median_us"), ("offload, fast PC", "fast_us"), ("offload, slow PC", "slow_us")],
        "Time per run (µs, log scale)"),
}
for ph, (title, SER, ylab) in PHASES.items():
    for c in ("h_all", "bell_ghz", "qft", "grover"):
        rows = []
        for b in ("uno", "esp8266", "esp32"):
            g = band[(band.board == b) & (band.circuit == c)].sort_values("n")
            for lab, col in SER:
                rows += [{"n": int(r.n), "time_us": float(r[col]), "board": NAME[b], "series": lab} for _, r in g.iterrows() if r[col] > 0]
        df = pd.DataFrame(rows)
        fig, ax = plot_grouped_lines(df, "n", "time_us", "board", "series", title=title.format(c=c), xlabel="Number of qubits, $n$", ylabel=ylab,
                                     group_order=list(NAME.values()), series_order=[s for s, _ in SER])
        out = os.path.join(ROOT, "data", "figures", f"phase{ph}", "algorithms", f"{c}.png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        save_figure(fig, out)
        print(out)
