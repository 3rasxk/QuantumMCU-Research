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
CSV_PATH = RAW_DIR / "infidelity_tvd.csv"
THRESHOLD = 1e-3


def load_rows():
    if not CSV_PATH.exists():
        raise SystemExit(f"error: {CSV_PATH} not found. รัน analysis/phase1_compare.py ก่อน")
    with open(CSV_PATH, newline="") as f:
        return list(csv.DictReader(f))


def main():
    ps.apply_style()
    rows = load_rows()

    fig, ax = plt.subplots(figsize=(7.5, 4.8), layout="constrained")

    omitted = 0
    for circuit in ps.CIRCUIT_ORDER:
        pts = sorted((int(r["depth"]), float(r["infidelity"])) for r in rows if r["circuit"] == circuit)
        if not pts:
            continue
        # infidelity = 1 − F อาจออกมา <= 0 จากการปัดเศษ float64 ซึ่งแสดงบนแกน log ไม่ได้
        # ตัดออกจากเส้นแต่บอกจำนวนบนกราฟ ไม่ปล่อยให้หายไปเงียบ ๆ
        shown = [(d, v) for d, v in pts if v > 0]
        omitted += len(pts) - len(shown)
        ax.plot(
            [p[0] for p in shown], [p[1] for p in shown],
            color=ps.CIRCUIT_INK[circuit], linestyle=ps.CIRCUIT_LINESTYLE[circuit],
            marker=ps.CIRCUIT_MARKER[circuit], markersize=6, markeredgecolor="white",
            markeredgewidth=0.8, linewidth=1.8, label=ps.CIRCUIT_LABEL[circuit], zorder=3,
        )

    ax.axhline(THRESHOLD, color=ps.REFERENCE_LINE, linestyle=(0, (6, 3)), linewidth=1.2, zorder=2,
               label=f"Pass threshold (infidelity = {THRESHOLD:.0e})")

    ps.style_axes(ax, log_y=True)
    ax.set_xlabel("Circuit depth (gate layers)")
    ax.set_ylabel("Infidelity, 1 − F (dimensionless, log scale)")
    ax.set_title("Phase 1 — C++ simulator vs Qiskit Aer: infidelity by circuit depth")
    fig.legend(loc="outside lower center", ncol=3)

    note = "Deterministic simulation: one run per (circuit, n), no repetitions."
    if omitted:
        note += f" {omitted} point(s) with infidelity ≤ 0 (float rounding) not shown on log axis."
        print(f"warning: {omitted} point(s) with infidelity <= 0 omitted from log-scale plot")
    ps.add_footnote(fig, note)

    ps.save_figure(fig, FIGURES_DIR, "infidelity_vs_depth")


if __name__ == "__main__":
    main()
