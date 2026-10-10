#!/usr/bin/env python3
# phase1_plot.py
# สร้างกราฟ Infidelity vs Circuit Depth (แกน y เป็น log-scale) จาก
# data/raw/phase1/infidelity_tvd.csv — ห้ามคำนวณค่าใหม่ในไฟล์นี้ อ่านค่าที่วัดจริงเท่านั้น
#
# Phase 1 รันบน PC (ไม่มีบอร์ด) จึงไม่ใช้สีบอร์ด — แยกวงจรด้วยหมึกเทา + marker +
# linestyle จาก pc/shared/plot_style.py เพื่อไม่ให้สีบอร์ดถูกยืมไปมีความหมายอื่น
# Phase 1 เป็น deterministic (รันครั้งเดียวต่อ circuit/n) จึงไม่มี median/IQR และ
# ระบุบนกราฟตรง ๆ ว่าไม่มี repetition แทนการเขียน n=100 ที่ไม่จริง
#
# ผลลัพธ์: data/figures/phase1/infidelity_vs_depth.png (PNG only)

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import plot_style as ps  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw" / "phase1"
FIGURES_DIR = REPO_ROOT / "data" / "figures" / "phase1"
# Restart re-validation: infidelity_tvd.<UTC timestamp>.csv (written by phase1_compare.py
# --timestamped-out), one file per run. Each file holds only the points that run covered, so all
# of them are merged, a later file (sorted by timestamp) replacing the same (circuit, n) of an
# earlier one. The original infidelity_tvd.csv is retired and used only when no timestamped file
# exists. (sorted(glob)[-1] picked the original, because "c" sorts after a digit.)
_STAMPED = sorted(RAW_DIR.glob("infidelity_tvd.[0-9]*.csv"))
CSV_PATHS = _STAMPED or [RAW_DIR / "infidelity_tvd.csv"]
THRESHOLD = 1e-3


def load_rows():
    merged = {}
    for path in CSV_PATHS:
        if not path.exists():
            raise SystemExit(f"error: {path} not found. รัน analysis/phase1_compare.py ก่อน")
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                merged[(r["circuit"], int(r["n"]))] = r
    return [merged[k] for k in sorted(merged)]


# --- Phase 1 charts tell the algorithms apart by COLOUR ONLY (solid lines, no markers). Phase 1 has no boards, so the
# board colours are not reused: blue / vermillion / green / purple, checked with dataviz validate_palette.js
# (--pairs all, light surface): lightness, chroma, normal-vision floor (min dE 18.7) and 3:1 contrast pass; CVD
# separation is in the 6-8 floor band (purple vs blue 6.7), so the legend order matches the curve order and the
# per-algorithm figures carry the algorithm name in the title. The rcParams come from ps.apply_style(). ---
PUB_COLOR = dict(ps.CIRCUIT_COLOR)       # one colour per circuit, shared with the Phase 2 and 3 charts
LINE_W = 1.8


def _curve(ax, xs, ys, circuit, **kw):
    """Solid coloured line, no marker. A lone point has no line to draw, so it gets one small dot to stay visible."""
    if len(xs) == 1:
        return ax.plot(xs, ys, color=PUB_COLOR[circuit], marker="o", markersize=3, linestyle="none", zorder=3, **kw)
    return ax.plot(xs, ys, color=PUB_COLOR[circuit], linestyle="-", linewidth=LINE_W, zorder=3, **kw)
PUB_LABEL = {
    "h_all": "H-all", "bell_ghz": "Bell/GHZ", "qft": "QFT",
    "grover": "Grover",
}


def _draw_panel(ax, rows, column, ylabel, threshold=None):
    from matplotlib.ticker import LogLocator, NullFormatter
    omitted = 0
    for circuit in ps.CIRCUIT_ORDER:
        pts = sorted((int(r["depth"]), float(r[column])) for r in rows if r["circuit"] == circuit)
        shown = [(d, v) for d, v in pts if v > 0]
        omitted += len(pts) - len(shown)
        if not shown:
            continue
        _curve(ax, [p[0] for p in shown], [p[1] for p in shown], circuit, label=PUB_LABEL[circuit])
    if threshold is not None:
        ax.axhline(threshold, color=ps.INK_SECONDARY, linestyle=(0, (5, 3)), linewidth=ps.REF_LINE_WIDTH, zorder=2)
        ax.text(1.15, threshold * 1.25, r"pass threshold ($10^{-3}$)", fontsize=8.5,
                color=ps.INK_SECONDARY, va="bottom", ha="left")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_locator(LogLocator(base=10))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Circuit depth (gate layers)")
    ax.set_ylabel(ylabel)
    return omitted


def _save_pub(fig, stem):
    ps.save_figure_png_only(fig, FIGURES_DIR, stem)       # PNG only under data/figures/


def plot_all(rows):
    ps.apply_style()
    import matplotlib.pyplot as plt
    specs = [
        ("infidelity", r"Infidelity, $1-F$", THRESHOLD, "infidelity_vs_depth"),
        ("tvd", "Total variation distance, TVD", None, "tvd_vs_depth"),
    ]
    # combined two-panel figure (a)(b), shared legend on top
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 3.4), layout="constrained")
    omitted = 0
    for ax, (col, ylab, thr, _), tag in zip(axes, specs, "ab"):
        omitted += _draw_panel(ax, rows, col, ylab, thr)
        ps.add_panel_label(ax, f"({tag})")
    handles, labels = axes[0].get_legend_handles_labels()
    axes[0].legend(handles, labels, loc="upper left", ncol=2, handletextpad=0.4, columnspacing=1.0)
    ps.suptitle(fig, "Phase 1 — C++ simulator vs Qiskit Aer, all circuits", tag=True, fontsize=10)
    _save_pub(fig, "phase1_accuracy")
    # single-panel versions (same style) for slides / report inserts
    for col, ylab, thr, stem in specs:
        fig, ax = plt.subplots(figsize=(3.5, 2.9), layout="constrained")
        _draw_panel(ax, rows, col, ylab, thr)
        ax.legend(loc="upper left", fontsize=7, handletextpad=0.3, labelspacing=0.25)
        _save_pub(fig, stem)
    if omitted:
        print(f"warning: {omitted} point(s) <= 0 omitted from log-scale plots")


def plot_per_algorithm(rows):
    """One figure per algorithm: (a) infidelity and (b) TVD versus qubit count n, with the
    circuit depth annotated on the top axis, saved to data/figures/phase1/<circuit>/."""
    ps.apply_style()
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    global FIGURES_DIR
    base = FIGURES_DIR
    try:
        for circuit in ps.CIRCUIT_ORDER:
            pts = sorted((int(r["n"]), int(r["depth"]), float(r["infidelity"]), float(r["tvd"]))
                         for r in rows if r["circuit"] == circuit)
            if not pts:
                continue
            fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9), layout="constrained")
            for ax, idx, ylab, thr, tag in (
                    (axes[0], 2, r"Infidelity, $1-F$", THRESHOLD, "a"),
                    (axes[1], 3, "Total variation distance, TVD", None, "b")):
                shown = [(p[0], p[idx]) for p in pts if p[idx] > 0]
                _curve(ax, [x for x, _ in shown], [y for _, y in shown], circuit)
                if thr is not None:
                    ax.axhline(thr, color=ps.INK_SECONDARY, linestyle=(0, (5, 3)), linewidth=ps.REF_LINE_WIDTH)
                    ax.text(0.02, thr * 1.25, r"pass threshold ($10^{-3}$)", fontsize=8.5,
                            color=ps.INK_SECONDARY, va="bottom", ha="left", transform=ax.get_yaxis_transform())
                ax.set_yscale("log")
                ys = [y for _, y in shown]
                pad = 100 if len(pts) == 1 else 4
                ax.set_ylim(min(ys) / pad, max(ys) * pad if thr is None else max(thr * 10, max(ys) * pad))
                if len(pts) == 1:
                    ax.set_xlim(pts[0][0] - 1, pts[0][0] + 1)
                    ax.set_xticks([pts[0][0]])
                else:
                    ps.style_axes(ax)
                ax.set_xlabel("Number of qubits, $n$")
                ax.set_ylabel(ylab)
                ps.add_panel_label(ax, f"({tag})")
                if len(pts) > 1:
                    sec = ax.secondary_xaxis("top", functions=(lambda v: v, lambda v: v))
                    step = -(-len(pts) // 8)             # at most ~8 depth labels, so they cannot overlap
                    shown_pts = pts[::step]
                    sec.set_xticks([p[0] for p in shown_pts])
                    sec.set_xticklabels([f"{p[1]:.1e}".replace("e+0", "e") if p[1] >= 100000 else str(p[1]) for p in shown_pts], fontsize=8)
                    sec.set_xlabel("circuit depth", fontsize=9)
            extra = f" (depth {pts[0][1]})" if len(pts) == 1 else ""
            ps.suptitle(fig, f"{PUB_LABEL[circuit].replace(' (n=7)', '')}{extra} — C++ simulator vs Qiskit Aer",
                        tag=True, fontsize=10)
            FIGURES_DIR = base / circuit
            _save_pub(fig, "infidelity_tvd")
    finally:
        FIGURES_DIR = base


def main():
    rows = load_rows()
    plot_all(rows)
    plot_per_algorithm(rows)


if __name__ == "__main__":
    main()
