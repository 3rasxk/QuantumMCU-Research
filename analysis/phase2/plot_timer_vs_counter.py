#!/usr/bin/env python3
# plot_timer_vs_counter.py
#
# Phase 2 micros() vs ESP32-counter timing: one figure per board x circuit (up to 12), graph-create house style.
# Reads data/raw/phase2/<board>/<circuit>/with_ref/ref/ref_compare.csv read-only (the post-restart dataset: micros() and the
# counter timed the same rep). A point needs >= MIN_PAIRS paired reps. A line runs through the measured n only: a missing n is skipped, so the line joins its neighbours
# straight across; no value is made up for it. A board x circuit without counter data gets no figure and is listed.
# Each figure (all n, log y in us): the counter (reference, solid blue) and micros() (dashed orange), both measured median time per rep,
# y axis zoomed onto the two lines.
# Also timer_vs_counter/<board>/all_circuits.png (all 4 circuits in one chart, colour = circuit, solid counter / dashed darker-shade micros()) and
# timer_vs_counter/ratio_all_boards.png: micros() / counter per n, a panel per board, a line per circuit (shows the small-n gap).
# Writes data/figures/phase2/timer_vs_counter/<board>/<circuit>.png and data/derived/phase2_timer_vs_counter.csv.
# PNGs carry no timestamp metadata, so a re-run gives identical files.
#
# Use:  .venv/bin/python analysis/phase2/plot_timer_vs_counter.py [--phase 2|3]   (3 = Phase 3 data, same layout under data/figures/phase3/)

import math
import sys
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "pc"))
sys.path.insert(0, str(REPO_ROOT / "analysis"))
from shared import plot_style as ps  # noqa: E402
import _graph_data as gd  # noqa: E402

PHASE = 3 if "--phase" in sys.argv and sys.argv[sys.argv.index("--phase") + 1] == "3" else 2   # Phase 3: e2e round trip vs counter
RAW_DIR = REPO_ROOT / "data" / "raw" / f"phase{PHASE}"
FIG_DIR = REPO_ROOT / "data" / "figures" / f"phase{PHASE}" / "timer_vs_counter"
CSV_PATH = REPO_ROOT / "data" / "derived" / f"phase{PHASE}_timer_vs_counter.csv"
MIN_PAIRS = 10          # fewer paired reps: no median drawn (same rule as the other micros()/counter charts)
OUTLIER_PCT = 5.0
DASH = (0, (4, 3))
COUNTER_COLOR, MICROS_COLOR, GAP_COLOR = "#1f77b4", "#ff7f0e", "#7B3294"   # single group: each series takes the base of a different family


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
            if PHASE == 3 and gd.phase3_cutoff(b, c) is not None:      # Phase 3: up to the crossover with Phase 2 (+1 n)
                d = d[d.n <= gd.phase3_cutoff(b, c)]
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


def draw_series(ax, ns, ys, color, linestyle):
    """2 pt line through every measured n in order; an n with no measurement is skipped, so the line runs straight from its neighbour
    to the next measured point (no value is made up for the missing n). A single point cannot form a line, so it gets one small dot
    (the only marker in the figures). Returns the drawn (x, y) array for the legend overlap test."""
    if len(ns) == 1:
        ax.plot(ns, ys, color=color, marker="o", markersize=3, linestyle="none", zorder=3)
    else:
        ax.plot(ns, ys, color=color, linestyle=linestyle, linewidth=2.0, zorder=3)
    return [np.column_stack([ns, ys])]


def save_fig(fig, path):
    """Phase 2 keeps its own save (the unnumbered 2-9 ticks are minor ticks). Phase 3 follows the graph-create house style:
    no minor ticks, no title, no markers, so it goes through ps.save_png."""
    path = ps._check_output_path(path, ".png")
    if PHASE == 3:
        return ps.save_png(fig, path)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.05, dpi=ps.RASTER_DPI, metadata=ps._PNG_META)
    print(f"figure -> {path}")
    plt.close(fig)
    return path


def _sci_label(v, _pos=None):
    """10^k as mathtext (the house-style tick label)."""
    return rf"$10^{{{int(round(math.log10(v)))}}}$"


def log_axis(ax, ymin, ymax):
    """Log y in us, zoomed onto the data (limits 1.4x outside the lowest and highest value): a numbered tick (10^k) at every decade
    inside and unnumbered small ticks at 2-9 of each decade."""
    ylim = (ymin / 1.4, ymax * 1.4)
    lo, hi = math.floor(math.log10(ylim[0])), math.ceil(math.log10(ylim[1]))
    inside = lambda vs: [round(v, 6) for v in vs if ylim[0] <= v <= ylim[1]]  # noqa: E731
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(mticker.FixedLocator(inside([10.0 ** e for e in range(lo, hi + 1)])))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_sci_label))
    ax.yaxis.set_minor_locator(mticker.FixedLocator(inside([m * 10.0 ** e for e in range(lo, hi + 1) for m in range(2, 10)])))
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax.tick_params(axis="y", which="minor", length=3.5, width=0.8)
    ax.set_ylim(*ylim)
    return lo, hi


def place_legend(ax, handles, segs, ncol=1):
    """Upper left like the house style; another corner only when it would cover a line."""
    fig = ax.figure
    best, best_n = None, None
    for loc in ("upper left", "upper right", "lower right", "lower left"):
        leg = ax.legend(handles=handles, loc=loc, ncol=ncol)
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
    leg = ax.legend(handles=handles, loc=best, ncol=ncol)
    leg.set_zorder(2.4)
    return best


def plot_one(s, board, circuit):
    """All n, log y in us. Two lines, both measured median times per rep: the counter (reference, solid blue) and micros() (dashed
    orange). The y axis is zoomed onto them: its limits sit 1.4x outside the lowest and highest plotted value."""
    s = s.sort_values("n")
    fig, ax = plt.subplots(figsize=(9.4, 6.2), layout="constrained")
    ns = s.n.tolist()
    segs = draw_series(ax, ns, s.median_counter_us.tolist(), COUNTER_COLOR, "-")
    segs += draw_series(ax, ns, s.median_micros_us.tolist(), MICROS_COLOR, DASH)
    handles = [Line2D([], [], color=COUNTER_COLOR, linewidth=2.0, linestyle="-", label="external pulse counter"),
               Line2D([], [], color=MICROS_COLOR, linewidth=2.0, linestyle=DASH, label="on-board timer")]
    allv = s.median_counter_us.tolist() + s.median_micros_us.tolist()
    log_axis(ax, min(allv), max(allv))
    if PHASE == 2:
        gd.record_ylim(f"timer/{board}/{circuit}", ax)
    else:
        gd.match_phase2_ylim(ax, f"timer/{board}/{circuit}")
    ylim = ax.get_ylim()
    ax.set_xticks(sorted(s.n.unique()))
    ax.set_ylabel("Median execution time per rep (µs, log scale)")
    loc = place_legend(ax, handles, segs)
    ax.set_xlabel("Number of qubits, $n$")
    # ps.save_png switches minor ticks off; the unnumbered 2-9 ticks are minor ticks, so save with the same settings
    save_fig(fig, FIG_DIR / board / f"{circuit}.png")
    return loc, (ns[0], ns[-1], ylim)


def plot_ratio(df):
    """One summary figure: micros() / counter per n, one panel per board, one line per circuit. The counter is the reference at 1,
    so a line below 1 means micros() read shorter. Linear y: this is where the two series differ (small n of the short circuits)."""
    fig, axes = plt.subplots(1, len(ps.BOARD_ORDER), figsize=(15.0, 5.2), sharey=True, layout="constrained")
    for ax, b in zip(axes, ps.BOARD_ORDER):
        ax.axhline(1.0, color=ps.REFERENCE_LINE, linewidth=1.0, zorder=1)
        for c in ps.CIRCUIT_ORDER:
            s = df[(df.board == b) & (df.circuit == c)].sort_values("n")
            if not s.empty:
                ax.plot(s.n, s.median_micros_us / s.median_counter_us, color=ps.CIRCUIT_COLOR[c], linewidth=2.0, label=c, zorder=3)
        if PHASE != 3:                                  # Phase 3: no panel title, the board name is the legend title
            ax.set_title(ps.BOARD_SHORT[b])
        ax.set_xlabel("Number of qubits, $n$")
        ax.set_xticks(sorted(df[df.board == b].n.unique()))
    axes[0].set_ylabel("on-board timer / external pulse counter (median per rep)")
    if PHASE != 3:
        axes[0].set_ylim(0.6, 1.02)
    if PHASE == 3:
        for ax, b in zip(axes, ps.BOARD_ORDER):
            ax.legend(loc="lower right", title=ps.BOARD_SHORT[b])
    else:
        axes[-1].legend(loc="lower right")
    save_fig(fig, FIG_DIR / "ratio_all_boards.png")


def darker(color, f=0.55):
    """Darker shade of the same hue: micros() takes the shade of its own circuit's colour."""
    return tuple(ch * f for ch in mcolors.to_rgb(color))


def plot_board(df, board):
    """One figure per board, all circuits together (log y in us). Each circuit has its own pair: counter (reference) solid in the
    circuit colour, micros() dashed in a darker shade of that colour. The dashed line is drawn on top so it shows over the solid one."""
    s = df[df.board == board]
    fig, ax = plt.subplots(figsize=(9.4, 6.2), layout="constrained")
    segs, handles = [], []
    for c in ps.CIRCUIT_ORDER:
        g = s[s.circuit == c].sort_values("n")
        if g.empty:
            continue
        col, dark = ps.CIRCUIT_COLOR[c], darker(ps.CIRCUIT_COLOR[c])
        segs += draw_series(ax, g.n.tolist(), g.median_counter_us.tolist(), col, "-")
        segs += draw_series(ax, g.n.tolist(), g.median_micros_us.tolist(), dark, DASH)
        handles += [Line2D([], [], color=col, linewidth=2.0, label=f"{c} external pulse counter"),
                    Line2D([], [], color=dark, linewidth=2.0, linestyle=DASH, label=f"{c} on-board timer")]
    allv = s.median_counter_us.tolist() + s.median_micros_us.tolist()
    log_axis(ax, min(allv), max(allv))
    if PHASE == 2:
        gd.record_ylim(f"timer_board/{board}", ax)
    else:
        gd.match_phase2_ylim(ax, f"timer_board/{board}")
    ax.set_xticks(sorted(s.n.unique()))
    ax.set_xlabel("Number of qubits, $n$")
    ax.set_ylabel("Median execution time per rep (µs, log scale)")
    place_legend(ax, handles, segs, ncol=2)
    save_fig(fig, FIG_DIR / board / "all_circuits.png")


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
            print(f"{b}_{c}: n {top[0]}..{top[1]}  y {top[2][0]:.4g} .. {top[2][1]:.6g} us")
    plot_ratio(df)
    for b in ps.BOARD_ORDER:
        plot_board(df, b)
    print(f"{made} figure(s) written")
    for sk in skipped:
        print("skipped:", *sk)
    big = df[df.diff_pct.abs() > OUTLIER_PCT].sort_values(["board", "circuit", "n"])
    print(f"\n|diff_pct| > {OUTLIER_PCT}% (kept in all figures):")
    print(big[["board", "circuit", "n", "diff_pct", "diff_us", "reps_used", "iqr_diff_us", "iqr_diff_pct"]]
          .to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main()
