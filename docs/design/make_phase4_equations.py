"""Draw docs/design/phase4_equations.png: the Phase 4 decision rule (analysis/phase4_decision_rule.py).

Run: python3 docs/design/make_phase4_equations.py
"""
from pathlib import Path

import matplotlib.pyplot as plt

plt.rcParams["mathtext.fontset"] = "cm"
plt.rcParams["font.family"] = "serif"

OUT = Path(__file__).with_name("phase4_equations.png")

rows = [
    ("Step 1  memory limit",
     r"$n_{\max}=\left\lfloor \log_2\!\dfrac{B}{8}\right\rfloor$",
     r"$B$ = largest free contiguous block (bytes), 8 bytes per amplitude"),
    ("Step 2  crossover",
     r"$T_{\mathrm{offload}}(n^{*})=T_{\mathrm{local}}(n^{*})$",
     r"$n^{*}$ = $n$ where the offload round trip drops below the local time per rep"),
    ("Predict another board",
     r"$n^{*}_{\mathrm{new}}=n^{*}_{\mathrm{ref}}+\log_2\!\dfrac{f_{\mathrm{new}}}{f_{\mathrm{ref}}}+\Delta_{\mathrm{arch}}$",
     r"$f$ = CPU clock;  $\Delta_{\mathrm{arch}}$ = architecture adjustment"),
    ("Adjustment from data",
     r"$\Delta_{\mathrm{arch}}=\log_2\!\dfrac{T_{\mathrm{local,ref}}}{T_{\mathrm{local,new}}}-\log_2\!\dfrac{f_{\mathrm{new}}}{f_{\mathrm{ref}}}$",
     r"first term = measured local speed ratio"),
    ("Decision",
     r"$\mathrm{run\ local\ if}\ \ n\leq n_{\max}\ \ \mathrm{and}\ \ n<n^{*};\ \ \mathrm{otherwise\ offload}$",
     ""),
]

fig, ax = plt.subplots(figsize=(11, 10))
ax.set_xlim(0, 11)
ax.set_ylim(0, 10)
ax.axis("off")
y = 9.4
for title, eq, note in rows:
    ax.text(0.3, y + 0.45, title, fontsize=13, color="gray", va="center")
    ax.text(0.6, y - 0.25, eq, fontsize=24, va="center")
    if note:
        ax.text(0.6, y - 1.0, note, fontsize=12, color="#444444", va="center")
    y -= 1.9
fig.savefig(OUT, dpi=200, bbox_inches="tight", facecolor="white")
print(OUT)
