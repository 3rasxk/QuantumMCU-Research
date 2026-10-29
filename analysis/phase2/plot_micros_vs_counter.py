#!/usr/bin/env python3
# plot_micros_vs_counter.py
#
# Phase 2 micros() vs ESP32-counter timing: one figure per board x circuit (up to 12), graph-create house style.
# Reads data/raw/phase2/<board>/<circuit>/with_ref/ref/ref_compare.csv read-only (the post-restart dataset: micros() and the
# counter timed the same rep). A point needs >= MIN_PAIRS paired reps. A line ends where the data ends and breaks at a missing n;
# nothing is filled or interpolated. A board x circuit without counter data gets no figure and is listed.
# Each figure: |micros() - counter| in us (measured medians) on a log scope from 0.0125 us (one counter tick) up to 10 us, wider only
# when a gap is larger; hollow dot where micros() is above the counter.
# Writes data/figures/phase2/micros_vs_counter/<board>_<circuit>.png and data/derived/phase2_micros_vs_counter.csv.
# PNGs carry no timestamp metadata, so a re-run gives identical files.
#
# Use:  .venv/bin/python analysis/phase2/plot_micros_vs_counter.py

import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import plot_style as ps  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw" / "phase2"
FIG_DIR = REPO_ROOT / "data" / "figures" / "phase2" / "micros_vs_counter"
CSV_PATH = REPO_ROOT / "data" / "derived" / "phase2_micros_vs_counter.csv"
SCOPE_LO_US, SCOPE_HI_US = 0.0125, 10.0   # y scope: from one counter tick (12.5 ns) up to 10 us; a larger gap widens the top
MIN_PAIRS = 10          # fewer paired reps: no median drawn (same rule as the other micros()/counter charts)
OUTLIER_PCT = 5.0
DASH = (0, (4, 3))
COUNTER_COLOR, MICROS_COLOR = "#1f77b4", "#ff7f0e"   # single group: each series takes the base of a different family


def load_points():
    """One row per (board, circuit, n): medians and the paired-rep count, plus the IQRs used by the outlier report."""
    rows, skipped = [], []
    for b in ps.BOARD_ORDER:
        for c in ps.CIRCUIT_ORDER:
            path = RAW_DIR / b / c / "with_ref" / "ref" / "ref_compare.csv"
            if not path.exists():
                skipped.append((b, c, "no ref_compare.csv"))
                continue
            d = pd.read_csv(path).dropna(subset=["micros_us", "counter_us"])
            for n, g in d.groupby("n"):
                if len(g) < MIN_PAIRS:
                    skipped.append((b, c, f"n={int(n)}: only {len(g)} paired rep(s)"))
                    continue
                cm, mm = float(g.counter_us.median()), float(g.micros_us.median())
                iqr = lambda s: float(s.quantile(0.75) - s.quantile(0.25))  # noqa: E731
                rows.append(dict(board=b, circuit=c, n=int(n), median_counter_us=cm, median_micros_us=mm,
                                 diff_us=mm - cm, diff_pct=(mm - cm) / cm * 100.0, reps_used=len(g),
                                 iqr_diff_us=iqr(g.diff_us), iqr_diff_pct=iqr(g.diff_pct)))
    return pd.DataFrame(rows), skipped


def runs(ns):
    """Split sorted n values into runs of consecutive integers: a missing n breaks the line instead of bridging it."""
    out, cur = [], []
    for n in ns:
        if cur and n != cur[-1] + 1:
            out.append(cur)
            cur = []
        cur.append(n)
    if cur:
        out.append(cur)
    return out


def draw_series(ax, ns, ys, color, linestyle):
    """2 pt line per run of consecutive n. A single isolated point cannot form a line, so it gets one small dot (the only
    marker in the figures). Returns the drawn (x, y) arrays for the legend overlap test."""
    segs = []
    lookup = dict(zip(ns, ys))
    for run in runs(list(ns)):
        xs, vs = run, [lookup[n] for n in run]
        if len(run) == 1:
            ax.plot(xs, vs, color=color, marker="o", markersize=3, linestyle="none", zorder=3)
        else:
            ax.plot(xs, vs, color=color, linestyle=linestyle, linewidth=2.0, zorder=3)
        segs.append(np.column_stack([xs, vs]))
    return segs


def _sci_label(v, _pos=None):
    """10^k as mathtext (the house-style tick label)."""
    return rf"$10^{{{int(round(math.log10(v)))}}}$"


def gap_axis(ax, ymax):
    """Log y from 0.0125 us (one counter tick) to at least 10 us, in us: numbered 10^k at every decade, "0.0125" at the bottom
    edge, unnumbered small ticks at 2-9. The top widens to the next decade only when a gap is larger than 10 us."""
    hi = max(math.ceil(math.log10(max(ymax, SCOPE_HI_US)) - 0.05), 1)
    ylim = (SCOPE_LO_US, 10.0 ** (hi + 0.12))
    inside = lambda vs: [round(v, 6) for v in vs if ylim[0] <= v <= ylim[1]]  # noqa: E731
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(mticker.FixedLocator(inside([SCOPE_LO_US] + [10.0 ** e for e in range(-1, hi + 1)])))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _p: f"{v:g}" if v < 0.1 else _sci_label(v)))
    ax.yaxis.set_minor_locator(mticker.FixedLocator(inside([m * 10.0 ** e for e in range(-2, hi + 1) for m in range(2, 10)])))
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax.tick_params(axis="y", which="minor", length=3.5, width=0.8)
    ax.set_ylim(*ylim)
    return hi


def place_legend(ax, handles, segs):
    """Upper left like the house style; another corner only when it would cover a line."""
    fig = ax.figure
    best, best_n = None, None
    for loc in ("upper left", "upper right", "lower right", "lower left"):
        leg = ax.legend(handles=handles, loc=loc, ncol=1)
        leg.set_zorder(2.4)                    # below the spines (2.5)
        fig.canvas.draw()
        bb = leg.get_window_extent().expanded(1.03, 1.06)
        hit = 0
        for seg in segs:
            pts = ax.transData.transform(seg)
            for a, b in zip(pts[:-1], pts[1:]):
                hit += int(sum(bb.contains(*(a + (b - a) * t)) for t in np.linspace(0, 1, 60)))
            if len(pts) == 1:
                hit += int(bb.contains(*pts[0]))
        if hit == 0:
            return loc
        if best_n is None or hit < best_n:
            best, best_n = loc, hit
    leg = ax.legend(handles=handles, loc=best, ncol=1)
    leg.set_zorder(2.4)
    return best


def plot_one(s, board, circuit):
    """|micros() - counter| in us (measured medians) on a log scope from 0.0125 us to at least 10 us. micros() is below the counter
    at almost every point; a point where it is above is marked with a hollow dot, so the sign is not lost on a log axis."""
    s = s.sort_values("n")
    fig, ax = plt.subplots(figsize=(9.4, 6.2), layout="constrained")
    ns, gap = s.n.tolist(), s.diff_us.abs().tolist()
    segs = draw_series(ax, ns, gap, MICROS_COLOR, "-")
    handles = [Line2D([], [], color=MICROS_COLOR, linewidth=2.0, label="|micros() $-$ counter|")]
    above = s[s.diff_us > 0]
    if not above.empty:
        ax.plot(above.n, above.diff_us.abs(), linestyle="none", marker="o", markersize=7, markerfacecolor="white",
                markeredgecolor=MICROS_COLOR, markeredgewidth=1.6, zorder=4)
        handles.append(Line2D([], [], linestyle="none", marker="o", markersize=7, markerfacecolor="white",
                              markeredgecolor=MICROS_COLOR, markeredgewidth=1.6, label="micros() above counter"))
    top = gap_axis(ax, max(gap))
    ax.set_xticks(sorted(s.n.unique()))
    ax.set_title(f"Phase 2 -- micros() vs counter, {ps.BOARD_SHORT[board]}, {circuit}")
    ax.set_xlabel("Number of qubits, $n$")
    ax.set_ylabel("Gap between micros() and counter (µs, log scale)")
    loc = place_legend(ax, handles, segs)
    # ps.save_png switches minor ticks off; the unnumbered 2-9 ticks are minor ticks, so save with the same settings
    path = ps._check_output_path(FIG_DIR / f"{board}_{circuit}.png", ".png")
    fig.savefig(path, bbox_inches="tight", pad_inches=0.05, dpi=ps.RASTER_DPI, metadata=ps._PNG_META)
    print(f"figure -> {path}")
    plt.close(fig)
    return loc, top


def main():
    ps.apply_style()
    df, skipped = load_points()
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    cols = ["board", "circuit", "n", "median_counter_us", "median_micros_us", "diff_us", "diff_pct", "reps_used"]
    out = df[cols].copy()
    out["board"] = pd.Categorical(out.board, ps.BOARD_ORDER)
    out["circuit"] = pd.Categorical(out.circuit, ps.CIRCUIT_ORDER)
    out = out.sort_values(["board", "circuit", "n"]).round({"median_counter_us": 6, "median_micros_us": 6,
                                                            "diff_us": 6, "diff_pct": 6})
    out.to_csv(CSV_PATH, index=False)
    print(f"csv -> {CSV_PATH} ({len(out)} rows)")
    made = 0
    for b in ps.BOARD_ORDER:
        for c in ps.CIRCUIT_ORDER:
            s = df[(df.board == b) & (df.circuit == c)] if len(df) else df
            if s.empty:
                print(f"no counter data: {b} {c} -- no figure")
                continue
            loc, top = plot_one(s, b, c)
            made += 1
            print(f"{b}_{c}: legend={loc} y scope 0.0125 .. 1e{top} us")
    print(f"{made} figure(s) written")
    for sk in skipped:
        print("skipped:", *sk)
    big = df[df.diff_pct.abs() > OUTLIER_PCT].sort_values(["board", "circuit", "n"])
    print(f"\n|diff_pct| > {OUTLIER_PCT}% (kept in all figures):")
    print(big[["board", "circuit", "n", "diff_pct", "diff_us", "reps_used", "iqr_diff_us", "iqr_diff_pct"]]
          .to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main()
