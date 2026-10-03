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
# ผลลัพธ์: data/figures/phase1/infidelity_vs_depth.{png,svg}

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import plot_style as ps  # noqa: E402

RAW_DIR = REPO_ROOT / "data" / "raw" / "phase1"
FIGURES_DIR = REPO_ROOT / "data" / "figures" / "phase1"
# newest results file: infidelity_tvd.<UTC timestamp>.csv (restart re-validation, written by
# phase1_compare.py --timestamped-out) sorts after the original infidelity_tvd.csv
CSV_PATH = sorted(RAW_DIR.glob("infidelity_tvd*.csv"))[-1] if list(RAW_DIR.glob("infidelity_tvd*.csv")) \
    else RAW_DIR / "infidelity_tvd.csv"
THRESHOLD = 1e-3


def load_rows():
    if not CSV_PATH.exists():
        raise SystemExit(f"error: {CSV_PATH} not found. รัน analysis/phase1_compare.py ก่อน")
    with open(CSV_PATH, newline="") as f:
        return list(csv.DictReader(f))


# --- publication style (Phase 1 only: no boards here, so the board palette is not borrowed) ---
# Okabe-Ito colour-blind-safe palette + a distinct marker per circuit, so the series stay
# separable in greyscale print too. Serif (STIX) text, 300 dpi raster + vector PDF/SVG.
PUB_COLOR = {
    "h_all": "#0072B2", "bell_ghz": "#D55E00", "qft": "#009E73",
    "grover": "#CC79A7",
}
PUB_LABEL = {
    "h_all": "H-all", "bell_ghz": "Bell/GHZ", "qft": "QFT",
    "grover": "Grover",
}


def _pub_rc():
    import matplotlib
    matplotlib.rcParams.update({
        "font.family": "serif", "font.serif": ["STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix", "font.size": 9, "axes.labelsize": 9.5,
        "axes.titlesize": 10, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "legend.fontsize": 8.5, "axes.linewidth": 0.8, "xtick.direction": "in",
        "ytick.direction": "in", "xtick.top": True, "ytick.right": True,
        "xtick.minor.visible": True, "svg.fonttype": "path", "pdf.fonttype": 42,
    })


def _draw_panel(ax, rows, column, ylabel, threshold=None):
    from matplotlib.ticker import LogLocator, NullFormatter
    omitted = 0
    for circuit in ps.CIRCUIT_ORDER:
        pts = sorted((int(r["depth"]), float(r[column])) for r in rows if r["circuit"] == circuit)
        shown = [(d, v) for d, v in pts if v > 0]
        omitted += len(pts) - len(shown)
        if not shown:
            continue
        single = len(shown) == 1
        ax.plot([p[0] for p in shown], [p[1] for p in shown],
                color=PUB_COLOR[circuit], marker=ps.CIRCUIT_MARKER[circuit], markersize=5.5,
                markeredgecolor="black", markeredgewidth=0.5,
                linewidth=0 if single else 1.2, alpha=0.95, label=PUB_LABEL[circuit], zorder=3)
    if threshold is not None:
        ax.axhline(threshold, color="#444444", linestyle=(0, (5, 3)), linewidth=0.9, zorder=2)
        ax.text(1.15, threshold * 1.25, r"pass threshold ($10^{-3}$)", fontsize=8,
                color="#444444", va="bottom", ha="left")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_locator(LogLocator(base=10))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.grid(True, which="major", color="#d0d0d0", linewidth=0.6)
    ax.grid(True, which="minor", color="#ececec", linewidth=0.3)
    ax.set_axisbelow(True)
    ax.set_xlabel("Circuit depth (gate layers)")
    ax.set_ylabel(ylabel)
    return omitted


def _save_pub(fig, stem):
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    for ext, kw in (("png", {"dpi": 300}), ("pdf", {}), ("svg", {})):
        path = FIGURES_DIR / f"{stem}.{ext}"
        fig.savefig(path, bbox_inches="tight", pad_inches=0.05, **kw)
        print(f"figure -> {path}")
    import matplotlib.pyplot as plt
    plt.close(fig)


def plot_all(rows):
    _pub_rc()
    import matplotlib.pyplot as plt
    specs = [
        ("infidelity", r"Infidelity, $1-F$", THRESHOLD, "infidelity_vs_depth"),
        ("tvd", "Total variation distance, TVD", None, "tvd_vs_depth"),
    ]
    # combined two-panel figure (a)(b), shared legend on top
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.1), layout="constrained")
    omitted = 0
    for ax, (col, ylab, thr, _), tag in zip(axes, specs, "ab"):
        omitted += _draw_panel(ax, rows, col, ylab, thr)
        ax.text(-0.02, 1.03, f"({tag})", transform=ax.transAxes, fontweight="bold",
                fontsize=10, va="bottom", ha="right")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside upper center", ncol=6, frameon=False,
               handletextpad=0.3, columnspacing=1.0)
    _save_pub(fig, "phase1_accuracy")
    # single-panel versions (same style) for slides / report inserts
    for col, ylab, thr, stem in specs:
        fig, ax = plt.subplots(figsize=(3.5, 2.9), layout="constrained")
        _draw_panel(ax, rows, col, ylab, thr)
        ax.legend(loc="upper left", fontsize=7, handletextpad=0.3, labelspacing=0.25,
                  frameon=False)
        _save_pub(fig, stem)
    if omitted:
        print(f"warning: {omitted} point(s) <= 0 omitted from log-scale plots")


def plot_per_algorithm(rows):
    """One figure per algorithm: (a) infidelity and (b) TVD versus qubit count n, with the
    circuit depth annotated on the top axis, saved to data/figures/phase1/<circuit>/."""
    _pub_rc()
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
                ax.plot([x for x, _ in shown], [y for _, y in shown],
                        color=PUB_COLOR[circuit], marker=ps.CIRCUIT_MARKER[circuit], markersize=6,
                        markeredgecolor="black", markeredgewidth=0.5,
                        linewidth=0 if len(shown) == 1 else 1.3, zorder=3)
                if thr is not None:
                    ax.axhline(thr, color="#444444", linestyle=(0, (5, 3)), linewidth=0.9)
                    ax.text(0.02, thr * 1.25, r"pass threshold ($10^{-3}$)", fontsize=8,
                            color="#444444", va="bottom", ha="left", transform=ax.get_yaxis_transform())
                ax.set_yscale("log")
                ys = [y for _, y in shown]
                pad = 100 if len(pts) == 1 else 4
                ax.set_ylim(min(ys) / pad, max(ys) * pad if thr is None else max(thr * 10, max(ys) * pad))
                if len(pts) == 1:
                    ax.set_xlim(pts[0][0] - 1, pts[0][0] + 1)
                    ax.set_xticks([pts[0][0]])
                else:
                    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
                ax.grid(True, which="major", color="#d0d0d0", linewidth=0.6)
                ax.grid(True, which="minor", axis="y", color="#ececec", linewidth=0.3)
                ax.set_axisbelow(True)
                ax.set_xlabel("Number of qubits, $n$")
                ax.set_ylabel(ylab)
                ax.text(-0.02, 1.03, f"({tag})", transform=ax.transAxes, fontweight="bold",
                        fontsize=10, va="bottom", ha="right")
                if len(pts) > 1:
                    sec = ax.secondary_xaxis("top", functions=(lambda v: v, lambda v: v))
                    sec.set_xticks([p[0] for p in pts])
                    sec.set_xticklabels([str(p[1]) for p in pts], fontsize=6.5)
                    sec.set_xlabel("circuit depth", fontsize=8)
            extra = f" (depth {pts[0][1]})" if len(pts) == 1 else ""
            fig.suptitle(f"{PUB_LABEL[circuit].replace(' (n=7)', '')}{extra} — C++ simulator vs Qiskit Aer", fontsize=10)
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
