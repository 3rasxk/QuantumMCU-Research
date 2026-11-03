#!/usr/bin/env python3
"""Paper Fig. F1 (median time per run vs n, every board and circuit) in the house line-chart style of the graph-create skill.
Reads data/processed/phase4/time_predictions.csv (selected Phase 2 sessions, read-only); writes paper/figures/F1_timing_vs_n_house.png.
The style has no markers, so weak points (< 30 repetitions) and memory walls are stated in the paper caption, not drawn.

    .venv/bin/python analysis/paper/make_f1_house.py
"""
import glob
import os
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vendor"))   # vendored graph-create style (analysis/vendor/plot_style.py)
from plot_style import plot_grouped_lines, save_figure  # noqa: E402

d = pd.read_csv(os.path.join(ROOT, "data", "processed", "phase4", "time_predictions.csv"))
d = d[d.median_us > 0]
names = {"uno": "Uno", "esp8266": "ESP8266", "esp32": "ESP32"}
d["board"] = d.board.map(names)
d = d.rename(columns={"median_us": "time_us"})
d["bo"] = d.board.map({"Uno": 0, "ESP8266": 1, "ESP32": 2})
d["co"] = d.circuit.map({"h_all": 0, "bell_ghz": 1, "qft": 2, "grover": 3})
d = d.sort_values(["bo", "co", "n"])
fig, ax = plot_grouped_lines(d, "n", "time_us", "board", "circuit",
                             title="",
                             xlabel="Number of qubits, $n$", ylabel="Median execution time per run (µs, log scale)",
                             group_order=["Uno", "ESP8266", "ESP32"], series_order=["h_all", "bell_ghz", "qft", "grover"])
out = os.path.join(ROOT, "paper", "figures", "F1_timing_vs_n_house.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
save_figure(fig, out)
print(out)
