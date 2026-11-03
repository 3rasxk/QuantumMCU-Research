#!/usr/bin/env python3
# phase4_all_in_one.py
# Phase 4 in one bar chart, graph-create house style (analysis/vendor/plot_style.py): for every board and circuit the number of qubits n at which the Local
# (Phase 2) and the Offload (Phase 3) lines cross, rounded UP to the first whole n at which offload is faster. The crossing is the dot of the charts in
# data/figures/phase4/crossover/<board>/<circuit>.png (same data: ESP32 counter medians of the Phase 2 / Phase 3 algorithms charts, same rule: straight segments
# between measured n, see analysis/crossover_house_plots.py). No bar = the drawn lines do not cross ("no crossing").
# It is NOT the crossover of Table III (micros() and round trip, as a bracket). Output: data/figures/phase4/all_boards_all_circuits.png
#
# Use:  .venv/bin/python analysis/phase4_all_in_one.py
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))
sys.path.insert(0, str(HERE / "phase4"))
sys.path.insert(0, str(HERE))
import plot_style as house  # noqa: E402
import p4common as C  # noqa: E402
from crossover_house_plots import crossings  # noqa: E402

LABEL = {"uno": "Arduino Uno R3", "esp8266": "NodeMCU ESP8266", "esp32": "ESP32 DevKit V1"}
SHORT = {"uno": "Uno", "esp8266": "ESP8266", "esp32": "ESP32"}


def main():
    house.apply_style()
    cv = pd.read_csv(HERE.parent / "data" / "derived" / "counter_validity.csv")
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
                ax.text(x, 0.2, "no crossing", ha="center", va="bottom", fontsize=8.5, rotation=90)
                continue
            k = math.ceil(pts[-1][0] - 1e-9)           # first whole n at which offload is faster than local
            ax.bar(x, k, color=col, zorder=3)
            ax.text(x, k + 0.2, f"{k}", ha="center", va="bottom", fontsize=9)
            top = max(top, k)
    ax.set_xticks([bi * (nc + 1) + (nc - 1) / 2 for bi in range(nb)], [LABEL[b] for b in C.BOARDS])
    ax.set_ylabel("Crossover point (number of qubits $n$, rounded up)")
    ax.set_ylim(0, top + 2.5)
    ax.set_yticks(range(0, top + 1))                    # equal spacing: a tick at every whole n
    leg = ax.legend(handles=handles, loc="upper left", ncol=nb)
    leg.set_zorder(2.4)
    out = HERE.parent / "data" / "figures" / "phase4" / "all_boards_all_circuits.png"
    house.save_figure(fig, str(out))
    print(out)


if __name__ == "__main__":
    main()
