# Vendored copy of the graph-create house plotting style (scripts/plot_style.py), so the analysis does not depend on ~/.claude. Unmodified apart from this line.
#!/usr/bin/env python3
"""Grouped log-scale line chart in the "Phase 2 -- all boards, all circuits" house style.

Library use:
    import sys; sys.path.insert(0, "<skill>/scripts")
    from plot_style import plot_grouped_lines
    fig, ax = plot_grouped_lines(df, x="n", y="time_us", group="board", series="circuit",
                                 title="...", xlabel="Number of qubits, $n$",
                                 ylabel="Median execution time per rep (µs, log scale)")
    fig.savefig("out.png", dpi=300, bbox_inches="tight")

CLI:
    python plot_style.py data.csv --x n --y time_us --group board --series circuit \
        --title "..." --xlabel "..." --ylabel "..." --out out.png

Data is "long" format: one row per (group, series, x). Each series may cover a different
x-range; lines simply stop where the data stops (do not pad with NaN/zeros).
"""
from __future__ import annotations

import argparse
import colorsys
import math
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.colors as mcolors  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

# --------------------------------------------------------------------------- palette
# One hue family per group (blue / orange / green ...), four roles per family:
#   0 = the classic matplotlib "tab" colour, 1 = hue-shifted accent,
#   2 = bright/light variant, 3 = dark shade of the family.
FAMILIES = [
    ["#1f77b4", "#8e5bd0", "#56b4e9", "#0b2a6b"],  # blue   (purple, sky, navy)
    ["#ff7f0e", "#d62728", "#f2c230", "#7a3b12"],  # orange (red, gold, brown)
    ["#2ca02c", "#8bd450", "#00a99d", "#0b4d2a"],  # green  (lime, teal, forest)
]
EXTRA_BASES = ["#e377c2", "#7f7f7f", "#bcbd22", "#17becf", "#8c564b"]


def _derive_family(base: str) -> list[str]:
    """Build a 4-colour family (base, accent, light, dark) for groups beyond the 3 built-in ones."""
    r, g, b = mcolors.to_rgb(base)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    out = [base]
    for dh, nl, ns in [(0.12, l, s), (0.0, min(0.75, l + 0.2), s), (0.0, max(0.15, l - 0.25), s)]:
        rr, gg, bb = colorsys.hls_to_rgb((h + dh) % 1.0, nl, ns)
        out.append(mcolors.to_hex((rr, gg, bb)))
    return out


def family(i: int) -> list[str]:
    if i < len(FAMILIES):
        return FAMILIES[i]
    return _derive_family(EXTRA_BASES[(i - len(FAMILIES)) % len(EXTRA_BASES)])


# --------------------------------------------------------------------------- style
FIGSIZE = (9.4, 6.2)  # inches; saved at 300 dpi with bbox_inches="tight"
DPI = 300

RC = {
    "figure.figsize": FIGSIZE,
    "figure.dpi": 100,
    "savefig.dpi": DPI,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 10.5,
    "axes.titlepad": 8.5,
    "axes.labelsize": 10,
    "axes.linewidth": 0.8,
    "axes.grid": False,          # no grid at all
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "xtick.major.size": 6,
    "ytick.major.size": 6,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
    "xtick.minor.visible": False,
    "ytick.minor.visible": False,
    "lines.linewidth": 2.0,
    "lines.solid_capstyle": "butt",
    "legend.fontsize": 9,
    "legend.labelspacing": 0.28,
    "legend.frameon": True,
    "legend.framealpha": 1.0,
    "legend.edgecolor": "0.8",
    "legend.handlelength": 2.5,
    "legend.columnspacing": 1.1,
    "legend.borderpad": 0.3,
    "axes.unicode_minus": True,
}

_THAI_FONTS = ["Noto Sans Thai", "Sarabun", "TH Sarabun New", "Tahoma", "Loma", "Garuda", "Noto Serif Thai"]


def _has_thai(*strings) -> bool:
    return any(any("฀" <= ch <= "๿" for ch in str(s)) for s in strings if s)


def apply_style(*texts) -> None:
    """Apply the house rcParams. Pass any label strings so a Thai-capable font is chosen if needed."""
    plt.rcParams.update(RC)
    if _has_thai(*texts):
        from matplotlib import font_manager as fm

        have = {f.name for f in fm.fontManager.ttflist}
        for name in _THAI_FONTS:
            if name in have:
                plt.rcParams["font.family"] = [name, "DejaVu Sans"]
                plt.rcParams["axes.unicode_minus"] = False  # Thai fonts usually lack U+2212
                break


# --------------------------------------------------------------------------- helpers
def _decade_ticks(ymin: float, ymax: float, max_labels: int = 6):
    # 0.05-decade tolerance: a minimum of 0.97 should snap to 10^0, not open up an empty decade below it
    lo, hi = math.floor(math.log10(ymin) + 0.05), math.ceil(math.log10(ymax) - 0.05)
    hi = max(hi, lo + 1)
    span = hi - lo
    step = max(1, math.ceil(span / (max_labels - 1)))
    return lo, hi, step


def _place_legend(ax, handles, labels, ncol, loc):
    """loc="auto": keep the house position (upper left) unless it covers a line, then try other corners."""
    fig = ax.figure
    cands = ["upper left", "upper right", "lower right", "lower left", "center right", "center left"] if loc == "auto" else [loc]
    best, best_n = None, None
    for c in cands:
        leg = ax.legend(handles, labels, loc=c, ncol=ncol)
        leg.set_zorder(2.4)  # above the lines, but below the axes spines so the spines stay solid black
        if loc != "auto":
            return leg
        fig.canvas.draw()
        bb = leg.get_window_extent().expanded(1.03, 1.06)
        n = 0
        for ln in handles:
            pts = ax.transData.transform(ln.get_xydata())
            for a, b in zip(pts[:-1], pts[1:]):
                seg = a + (b - a) * np.linspace(0, 1, 60)[:, None]
                n += int(sum(bb.contains(x, y) for x, y in seg))
        if n == 0:
            return leg
        if best_n is None or n < best_n:
            best, best_n = c, n
    return ax.legend(handles, labels, loc=best, ncol=ncol)


def plot_grouped_lines(
    df: pd.DataFrame,
    x: str,
    y: str,
    group: str,
    series: str,
    title: str | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    log_y: bool = True,
    group_order: list | None = None,
    series_order: list | None = None,
    legend_label: str = "{group} {series}",
    legend_ncol: int | None = None,
    legend_loc: str = "auto",
    x_scale: str | None = None,
    integer_x: bool = True,
):
    """Draw one line per (group, series). Returns (fig, ax).

    x_scale: None (linear, the reference look), "log2" or "log10" - use when x doubles / grows by
    decades (file sizes 1,2,4,...64) so the points are not squashed against the left edge.
    legend_loc: "auto" (default) = upper left like the reference, moving to another corner only if it would cover a line;
    or any matplotlib location string to force one.
    """
    apply_style(title, xlabel, ylabel, *df[group].astype(str).unique(), *df[series].astype(str).unique())
    groups = group_order or list(dict.fromkeys(df[group]))
    sers = series_order or list(dict.fromkeys(df[series]))

    fig, ax = plt.subplots(constrained_layout=True)

    handles, labels = [], []
    # Legend is read column-wise: all series of group 1, then group 2, ... so one column per group.
    for gi, g in enumerate(groups):
        fam = family(gi)
        for si, s in enumerate(sers):
            sub = df[(df[group] == g) & (df[series] == s)].sort_values(x)
            if sub.empty:
                continue
            if len(groups) == 1:
                # only one group: give each series its own family's base colour (blue, orange, green, ...)
                color = family(si)[0]
            else:
                color = fam[si] if si < len(fam) else _derive_family(fam[0])[si % 4]
            (ln,) = ax.plot(sub[x], sub[y], color=color, label=legend_label.format(group=g, series=s))
            handles.append(ln)
            labels.append(ln.get_label())

    if log_y:
        ax.set_yscale("log")
        lo, hi, step = _decade_ticks(df[y][df[y] > 0].min(), df[y].max())
        ticks = [10.0 ** e for e in range(lo, hi + 1, step)]
        ax.yaxis.set_major_locator(mticker.FixedLocator(ticks))
        ax.yaxis.set_major_formatter(mticker.LogFormatterSciNotation(base=10))
        ax.yaxis.set_minor_locator(mticker.NullLocator())  # no minor ticks
        # y-limits hug the surrounding decades (about 0.17 decade below, 0.12 above) rather than a 5% margin
        ax.set_ylim(10.0 ** (lo - 0.17), 10.0 ** (hi + 0.12))

    xs = sorted(df[x].unique())
    if x_scale in ("log2", "log10"):
        ax.set_xscale("log", base=2 if x_scale == "log2" else 10)
        ax.xaxis.set_minor_locator(mticker.NullLocator())
        if len(xs) <= 20:
            ax.set_xticks(xs)
            ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))
    elif integer_x:
        ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        if len(xs) <= 20:
            ax.set_xticks(xs)  # every x value gets a tick, as in the reference

    if title:
        ax.set_title(title)
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)

    ncol = legend_ncol or len(groups)
    leg = _place_legend(ax, handles, labels, ncol, legend_loc)
    leg.set_zorder(2.4)
    return fig, ax


def save_figure(fig, path: str, dpi: int = DPI) -> None:
    fig.savefig(path, dpi=dpi, bbox_inches="tight", pad_inches=0.05)


# --------------------------------------------------------------------------- CLI
def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv")
    p.add_argument("--x", required=True)
    p.add_argument("--y", required=True)
    p.add_argument("--group", required=True, help="column giving one hue family / legend column (e.g. board)")
    p.add_argument("--series", required=True, help="column giving the shade within a group (e.g. circuit)")
    p.add_argument("--title")
    p.add_argument("--xlabel")
    p.add_argument("--ylabel")
    p.add_argument("--linear-y", action="store_true", help="linear y axis instead of log")
    p.add_argument("--group-order", help="comma-separated, default = order of appearance")
    p.add_argument("--series-order", help="comma-separated, default = order of appearance")
    p.add_argument("--legend-ncol", type=int)
    p.add_argument("--legend-loc", default="auto", help='"auto" or a matplotlib location such as "lower right"')
    p.add_argument("--x-scale", choices=["log2", "log10"], help="log x axis (default linear)")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)

    df = pd.read_csv(a.csv)
    for col in (a.x, a.y, a.group, a.series):
        if col not in df.columns:
            sys.exit(f"column '{col}' not in CSV (have: {', '.join(df.columns)})")
    fig, _ = plot_grouped_lines(
        df, a.x, a.y, a.group, a.series, title=a.title, xlabel=a.xlabel, ylabel=a.ylabel,
        log_y=not a.linear_y,
        group_order=a.group_order.split(",") if a.group_order else None,
        series_order=a.series_order.split(",") if a.series_order else None,
        legend_ncol=a.legend_ncol, legend_loc=a.legend_loc, x_scale=a.x_scale,
    )
    save_figure(fig, a.out)
    print(f"saved {a.out}")


if __name__ == "__main__":
    main()
