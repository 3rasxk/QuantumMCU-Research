#!/usr/bin/env python3
# crossover_bar_house_plot.py (added after the data were seen; existing data only)
# Bar chart, graph-create house style: the number of qubits n at which the Local (Phase 2) and Offload (Phase 3) lines cross, for every board and circuit.
# The values are the dots of the 12 charts in data/figures/phase4/crossover/<board>/<circuit>.png (same data: ESP32 counter medians of the Phase 2 / Phase 3
# algorithms charts, same crossing rule: straight segments between measured n, so the value is an interpolated n of the drawn lines, not a measured n).
# No bar = the drawn lines do not cross (labelled "none"). Two crossings (ESP32 grover): the last one is used.
# It is NOT the crossover of Table III (micros() and round trip, as a bracket) nor of all_boards_all_circuits.png (older interpolation rule).
# Output: data/figures/phase4/crossover_qubits_bar.png      Use:  .venv/bin/python analysis/crossover_bar_house_plot.py
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "vendor"))
sys.path.insert(0, os.path.join(HERE, "phase4"))
sys.path.insert(0, HERE)
import plot_style as house  # noqa: E402
import p4common as C  # noqa: E402
from crossover_house_plots import crossings  # noqa: E402

OUT = os.path.join(ROOT, "data", "figures", "phase4", "crossover_qubits_bar.png")
LABEL = {"uno": "Arduino Uno R3", "esp8266": "NodeMCU ESP8266", "esp32": "ESP32 DevKit V1"}
SHORT = {"uno": "Uno", "esp8266": "ESP8266", "esp32": "ESP32"}


def main():
    house.apply_style()
    cv = pd.read_csv(os.path.join(ROOT, "data", "derived", "counter_validity.csv"))
    cv = cv[cv.selected.astype(bool) & (cv.usable.astype(bool) | (cv.n == 2)) & (cv.counter_median_us > 0)]      # as analysis/algorithm_house_plots.py
    nb, nc = len(C.BOARDS), len(C.CIRCUITS)
    fig, ax = plt.subplots(constrained_layout=True)
    handles, top = [], 0
    for bi, b in enumerate(C.BOARDS):
        for ci, c in enumerate(C.CIRCUITS):
            col = house.family(bi)[ci]
            x = bi * (nc + 1) + ci
            handles.append(Patch(color=col, label=f"{SHORT[b]} {c}"))
            g = cv[(cv.phase == 2) & (cv.board == b) & (cv.circuit == c)].sort_values("n")
            o = cv[(cv.phase == 3) & (cv.board == b) & (cv.circuit == c)].sort_values("n")
            pts = crossings(g.n, g.counter_median_us, o.n, o.counter_median_us)
            if not pts:
                ax.text(x, 0.2, "none", ha="center", va="bottom", fontsize=9)
                continue
            n_star = pts[-1][0]
            ax.bar(x, n_star, color=col, zorder=3)
            ax.text(x, n_star + 0.2, f"{n_star:.1f}", ha="center", va="bottom", fontsize=9)
            top = max(top, n_star)
    ax.set_xticks([bi * (nc + 1) + (nc - 1) / 2 for bi in range(nb)], [LABEL[b] for b in C.BOARDS])
    ax.set_ylabel("Number of qubits $n$ where the Local and Offload lines cross")
    ax.set_ylim(0, top + 2.5)
    leg = ax.legend(handles=handles, loc="upper left", ncol=nb)
    leg.set_zorder(2.4)
    fig.supxlabel("n of the crossing of the drawn lines (ESP32 counter medians, straight segments between measured n, so an interpolated value);\n"
                  "none = the lines do not cross; ESP32 grover crosses twice, the last crossing is shown.", fontsize=7.5, color="0.3")
    house.save_figure(fig, OUT)
    print(OUT)


if __name__ == "__main__":
    main()
