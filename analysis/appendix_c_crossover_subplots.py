#!/usr/bin/env python3
# appendix_c_crossover_subplots.py — ภาคผนวก ค
# กราฟเส้น 1 subplot ต่อวงจร (จำนวน subplot ตามจริงจาก pc/shared/plot_style.CIRCUIT_ORDER
# ที่มีข้อมูล Phase 3 — ปัจจุบัน 4 วงจร: h_all, bell_ghz, qft, grover)
# แกน x = จำนวนคิวบิต (n), แกน y = เวลา (µs, log scale)
# แต่ละ subplot มี 6 เส้น = 3 บอร์ด (Uno/ESP8266/ESP32) × 2 เส้นทาง (local ทึบ,
# offload ประ) พร้อมแถบ IQR — ครบทั้ง Local Execution Time (Phase 2) และ Offload E2E
# Latency (Phase 3) อยู่ในกราฟเดียวกัน
#
# จัดกลุ่มตาม "algorithm" (วงจร) แทนที่จะจัดตามบอร์ดเหมือน crossover_{board}.png —
# เพื่อให้เทียบ "บอร์ดไหนเร็วกว่ากัน" ที่วงจรเดียวกันได้ในหน้าเดียว ตรงข้ามกับกราฟ
# รายบอร์ดที่เทียบ "วงจรไหนคุ้ม offload ก่อน" — สองมุมมองคนละคำถาม ไม่ใช่กราฟซ้ำ
#
# จุดตัด (crossover point) ทำเครื่องหมายด้วยวงกลมกลวงสีเดียวกับเส้นบอร์ดนั้น
# บวกเส้นประแนวตั้งบาง ๆ ลงแกน x — อ่านค่าจาก data/processed/phase3/crossover_summary.csv
# ตรง ๆ (ไม่คำนวณซ้ำ) เพื่อให้ตรงกับตารางสรุปทุกประการ
# ดึงข้อมูล/วาดเส้นด้วยฟังก์ชันเดียวกับ phase3_crossover_plot.py (ไม่เขียนซ้ำ)
#
# แหล่งข้อมูล: data/processed/phase2/summary.csv (local), data/processed/phase3/summary.csv
# (offload), data/processed/phase3/crossover_summary.csv (ตำแหน่งจุดตัดที่คำนวณไว้แล้ว)
#
# ผลลัพธ์: data/figures/phase3/crossover_all_boards.png

import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import plot_style as ps  # noqa: E402
from phase3_crossover_plot import (  # noqa: E402
    PHASE3_FIGURES_DIR, PHASE3_PROCESSED_DIR, best_baud_per_board, draw_series,
    load_local, load_offload, series_for,
)


def load_crossover():
    path = PHASE3_PROCESSED_DIR / "crossover_summary.csv"
    if not path.exists():
        raise SystemExit(f"error: {path} not found. รัน analysis/phase3_crossover_plot.py ก่อน")
    out = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            n = r["crossover_n"]
            out[(r["board"], r["circuit"])] = int(n) if n.isdigit() else None
    return out


def main():
    local = load_local()
    offload_rows = load_offload()
    crossover = load_crossover()
    best_baud = best_baud_per_board(offload_rows)
    circuits = [c for c in ps.CIRCUIT_ORDER if any(r["circuit"] == c for r in offload_rows)]
    if not circuits:
        raise SystemExit("error: ไม่มีข้อมูล Phase 3 ที่ตรงกับวงจรใน CIRCUIT_ORDER")
    ps.apply_style()

    fig, axes = plt.subplots(1, len(circuits), figsize=(4.4 * len(circuits), 4.4),
                             sharey=True, squeeze=False, layout="constrained")
    axes = axes[0]
    loc_trials, off_trials = [], []
    legend = {}
    any_crossover = False

    for ax, circuit in zip(axes, circuits):
        for board in ps.BOARD_ORDER:
            baud = best_baud.get(board)
            if baud is None:
                continue
            s = series_for(board, circuit, baud, local, offload_rows)
            if s is None:
                continue
            loc_trials += s["loc_trials"]
            off_trials += s["off_trials"]
            # 6 เส้นซ้อนกัน จึงลดความทึบแถบ IQR ลงครึ่งหนึ่งไม่ให้กลบกัน
            draw_series(ax, board, circuit, s, band_alpha=ps.IQR_ALPHA / 2)

            cn = crossover.get((board, circuit))
            if cn is not None and cn in s["ns"]:
                any_crossover = True
                color = ps.BOARD_COLOR[board]
                ax.scatter([cn], [s["off_med"][s["ns"].index(cn)]], s=90, facecolors="none",
                           edgecolors=color, linewidths=1.2, zorder=5)
                ax.axvline(x=cn, color=color, linestyle=":", linewidth=1.0, alpha=0.6, zorder=1)

        for h, lab in zip(*ax.get_legend_handles_labels()):
            legend.setdefault(lab, h)
        ps.style_axes(ax, log_y=True)
        ax.set_title(ps.CIRCUIT_LABEL[circuit])
        ax.set_xlabel("Number of qubits, n (qubits)")
    axes[0].set_ylabel("Time per run (µs, log scale)")

    # เรียง legend ตามบอร์ดคงที่ (local, offload) แล้วต่อด้วยสัญลักษณ์จุดตัด
    labels = [f"{ps.BOARD_SHORT[b]} — {kind}" for b in ps.BOARD_ORDER for kind in ("local", "offload")]
    labels = [lab for lab in labels if lab in legend]
    handles = [legend[lab] for lab in labels]
    if any_crossover:
        handles.append(Line2D([], [], linestyle="none", marker="o", markersize=9,
                              markerfacecolor="none", markeredgecolor=ps.INK_SECONDARY))
        labels.append("Crossover point (board colour)")
    fig.legend(handles, labels, loc="outside lower center", ncol=4)

    bauds = ", ".join(f"{ps.BOARD_SHORT[b]} {best_baud[b]}" for b in ps.BOARD_ORDER if b in best_baud)
    ps.suptitle(fig, "Local execution time vs offload end-to-end latency, by circuit — all boards "
                     f"(REPS={max(loc_trials + off_trials)}, {ps.git_tag()})", fontsize=10)
    ps.add_footnote(
        fig,
        f"Line = median, band = IQR (25th–75th percentile); {ps.reps_phrase(loc_trials, 'local')}; "
        f"{ps.reps_phrase(off_trials, 'offload')}. Offload baud: {bauds}.",
    )
    ps.save_figure_png_only(fig, PHASE3_FIGURES_DIR, "crossover_all_boards")


if __name__ == "__main__":
    main()
