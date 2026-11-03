#!/usr/bin/env python3
# crossover_house_plots.py (added after the data were seen; existing data only, selected sessions, in-scope n)
# One chart per board x circuit (12 files) in the house line-chart style of the graph-create skill (analysis/vendor/plot_style.py): log-y lines, no title,
# no markers except one dot per crossing. Exactly two lines:
#   Local   (blue)   median execution time per run, Phase 2 (board micros())
#   Offload (orange) median round-trip time per request of the selected Phase 3 session (wire + board and link + PC simulation of that session)
# The dot (named in the legend) marks where the two DRAWN lines cross (straight segments between measured n, in the log-y plot): an interpolated point of the picture, not a measured
# value; the reported crossover is the bracket of two measured n (Table III, docs/phase4_report.md section 5), which these charts do not show.
# No crossing of the drawn lines = no dot. IQR, weak points, PC-speed bounds (fast / slow band), memory walls and brackets are in figures/phase4/F4_crossover_by_circuit.pdf.
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
from plot_style import plot_grouped_lines, save_figure  # noqa: E402
import p4common as C  # noqa: E402
import offload_band as OB  # noqa: E402

OUT = os.path.join(ROOT, "data", "figures", "phase4", "crossover")


def crossings(nl, tl, no, to):
    """points where the polylines (n, log10 t) of the two lines cross, over the n where both are defined; [(n, t_us)]"""
    ll, lo = dict(zip(nl, np.log10(tl))), dict(zip(no, np.log10(to)))
    ns = sorted(set(ll) & set(lo))
    d = [ll[n] - lo[n] for n in ns]
    pts = []
    for i in range(len(ns)):
        if d[i] == 0:
            pts.append((float(ns[i]), 10 ** ll[ns[i]]))
        if i + 1 < len(ns) and ns[i + 1] == ns[i] + 1 and d[i] * d[i + 1] < 0:
            t = d[i] / (d[i] - d[i + 1])
            pts.append((ns[i] + t, 10 ** (ll[ns[i]] + t * (ll[ns[i + 1]] - ll[ns[i]]))))
    return pts


def main():
    m, _, _ = OB.band_table()
    loc = C.load_local()
    os.makedirs(OUT, exist_ok=True)
    for b in C.BOARDS:
        for c in C.CIRCUITS:
            g = loc[(loc.board == b) & (loc.circuit == c)].sort_values("n")
            o = m[(m.board == b) & (m.circuit == c)].sort_values("n")
            rows = [{"n": int(n), "time_us": float(t), "path": "Local", "series": "line"} for n, t in zip(g.n, g.median_us)]
            rows += [{"n": int(n), "time_us": float(t), "path": "Offload", "series": "line"} for n, t in zip(o.n, o.e2e_us)]
            df = pd.DataFrame(rows)
            df = df[df.time_us > 0]
            fig, ax = plot_grouped_lines(df, "n", "time_us", "path", "series", title="", xlabel="Number of qubits, $n$",
                                         ylabel="Time per run (µs, log scale)", group_order=["Local", "Offload"], series_order=["line"])
            for t in ax.get_legend().get_texts():
                t.set_text("Local (Phase 2)" if t.get_text().startswith("Local") else "Offload (Phase 3)")
            cross = crossings(g.n, g.median_us, o.n, o.e2e_us)
            for x, y in cross:
                ax.plot([x], [y], "o", color="black", markersize=9, markeredgecolor="white", markeredgewidth=1.2, zorder=5)
            if cross:                                                   # name the dot in the legend (same position and look as the house legend)
                from matplotlib.lines import Line2D
                leg = ax.get_legend()
                texts = [t.get_text() for t in leg.get_texts()]
                handles = [h for h in ax.get_legend_handles_labels()[0]]
                handles.append(Line2D([], [], marker="o", color="black", markersize=9, markeredgecolor="white", markeredgewidth=1.2, linestyle=""))
                leg = ax.legend(handles, texts + ["Crossover"], loc=leg._loc, ncol=len(handles))
                leg.set_zorder(2.4)
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
