"""Draw docs/design/grover_circuit.png (grover, n = 2, one iteration, same gate order as firmware/common/circuits.hpp).

Run: python3 docs/design/make_grover_circuit.py
Sequence per qubit: H | oracle (CZ) | H X | CZ | X H  -> |11>. For n = 2 the one iteration lands on the marked state exactly.
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

plt.rcParams["mathtext.fontset"] = "cm"
plt.rcParams["font.family"] = "serif"

OUT = Path(__file__).with_name("grover_circuit.png")

fig, ax = plt.subplots(figsize=(13, 3.6))
ax.set_xlim(0, 13)
ax.set_ylim(0, 3.6)
ax.axis("off")

YS = [2.3, 1.1]          # q0 on top, q1 below
X0, X1 = 1.6, 10.4       # wire span
BOX = 0.62
ax.text(0.9, YS[0], r"$|0\rangle$", ha="center", va="center", fontsize=24)
ax.text(0.9, YS[1], r"$|0\rangle$", ha="center", va="center", fontsize=24)
for y in YS:
    ax.plot([X0, X1], [y, y], color="black", lw=1.3, zorder=1)


def box(x, y, label):
    ax.add_patch(Rectangle((x - BOX / 2, y - BOX / 2), BOX, BOX, fc="white", ec="black", lw=1.3, zorder=3))
    ax.text(x, y, label, ha="center", va="center", fontsize=20, zorder=4)


def cz(x):
    ax.plot([x, x], YS, color="black", lw=1.3, zorder=2)
    for y in YS:
        ax.plot(x, y, "o", color="black", ms=8, zorder=4)


cols = [("H", 2.4), ("cz", 3.7), ("H", 5.0), ("X", 6.0), ("cz", 7.2), ("X", 8.4), ("H", 9.4)]
for kind, x in cols:
    if kind == "cz":
        cz(x)
    else:
        for y in YS:
            box(x, y, kind)

# oracle / diffusion labels (dashed groups)
for x0, x1, lab in [(3.25, 4.15, "oracle"), (4.5, 9.9, "diffusion")]:
    ax.add_patch(Rectangle((x0, 0.45), x1 - x0, 2.5, fc="none", ec="gray", lw=1, ls="--", zorder=0))
    ax.text((x0 + x1) / 2, 3.15, lab, ha="center", va="bottom", fontsize=14, color="gray")

# output brace + state
ax.text(10.75, sum(YS) / 2, r"$\}$", ha="center", va="center", fontsize=80)
ax.text(11.9, sum(YS) / 2, r"$|11\rangle$", ha="center", va="center", fontsize=28)

fig.savefig(OUT, dpi=200, bbox_inches="tight", facecolor="white")
print(OUT)
