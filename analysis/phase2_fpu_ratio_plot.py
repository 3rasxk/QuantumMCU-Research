#!/usr/bin/env python3
# phase2_fpu_ratio_plot.py
# กราฟ "FPU effect" ที่ n เดียวกันทุกบอร์ด (controlled comparison) — เดิมรายงานเป็น
# ตารางตัวเลขเท่านั้น (chapter4_results_th.md เวอร์ชัน n=30 §4.2.9) ไม่เคยมีรูป:
# เทียบเวลา local execution ของ h_all กับ bell_ghz ที่ n เดียวกัน ข้ามทั้ง 3 บอร์ด —
# h_all มีเกท H หนาแน่นกว่า (คำนวณเลขจุดทศนิยมเยอะกว่า) ส่วน bell_ghz ส่วนใหญ่เป็น CNOT
# (สลับ index ล้วน แทบไม่มีเลขจุดทศนิยม) บอร์ดที่มี FPU ฮาร์ดแวร์ (ESP32) จึงได้เปรียบ
# h_all มากกว่า bell_ghz อย่างไม่สมส่วน จนอัตราส่วน h_all/bell_ghz "กลับด้าน" เทียบกับ
# บอร์ดที่ไม่มี FPU (Uno, ESP8266)
#
# กราฟนี้ตรึง n ให้เท่ากันทุกบอร์ด เพื่อตัดตัวแปร "ขนาดปัญหา" ออก เหลือแต่ผล FPU ล้วน ๆ —
# คู่กับ phase2_fpu_ratio_own_n_plot.py ที่เทียบที่ n ของใครของมัน (operating point จริง)
# คนละคำถาม ไม่ใช่กราฟซ้ำ ตรรกะร่วมกันอยู่ที่ analysis/_fpu_ratio_common.py
#
# เลือก n ที่เทียบ: หา n สูงสุดที่ทั้ง h_all และ bell_ghz มีข้อมูลอยู่ "ทุกบอร์ด" (ไม่
# hardcode n=7 ตามที่ dataset n=30 เคยใช้ — ค่านั้นมาจาก Memory Wall ของ Uno ในรอบนั้น
# ซึ่งไม่รับประกันว่าจะเป็นค่าเดียวกันในรอบ n=100 นี้) ถ้าไม่มี n ร่วมเลย สคริปต์นี้จะ
# ออกด้วย error ชัดเจนแทนการเดา
#
# แหล่งข้อมูล: data/processed/phase2/summary.csv (คอลัมน์จาก phase2_summarize.py:
# board, circuit, n, n_trials, median_exec_time_us, iqr_low_us, iqr_high_us, iqr_width_us)
# ผลลัพธ์: data/figures/phase2/fpu_ratio_comparison.{png,svg}

import sys
from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import plot_style as ps  # noqa: E402
from phase2_plot import load_summary  # noqa: E402
from _fpu_ratio_common import (  # noqa: E402
    boards_with_both_circuits, draw_ratio_bars, find_common_n, index_by_board_circuit_n,
)

FIGURES_DIR = REPO_ROOT / "data" / "figures" / "phase2"


def main():
    summary_rows = load_summary()
    if not summary_rows:
        raise SystemExit("error: data/processed/phase2/summary.csv ว่างเปล่า หรือไม่มี — "
                         "รัน analysis/phase2_summarize.py ก่อน")
    idx = index_by_board_circuit_n(summary_rows)

    boards, missing = boards_with_both_circuits(idx, ps.BOARD_ORDER)
    if missing:
        print(f"warning: skipping board(s) missing h_all or bell_ghz data entirely: {missing}")
    if len(boards) < 2:
        raise SystemExit("error: need at least 2 boards with both h_all and bell_ghz data "
                         "to compare the FPU effect")

    n = find_common_n(idx, boards)
    if n is None:
        raise SystemExit(
            "error: no single n has h_all AND bell_ghz data for every board "
            f"({', '.join(boards)}) — check data/processed/phase2/summary.csv coverage"
        )
    n_by_board = {board: n for board in boards}

    ps.apply_style()
    fig, ax = plt.subplots(figsize=(7.5, 5.5), layout="constrained")
    ratios, reps = draw_ratio_bars(ax, boards, n_by_board, idx, ps)

    ax.set_xticks(range(len(boards)))
    ax.set_xticklabels([ps.BOARD_LABEL[b] for b in boards])
    ps.style_axes(ax, log_y=True, integer_x=False)
    ax.set_ylabel(f"Execution time at n = {n} (µs, log scale)")
    ax.set_title("Hadamard vs Bell State execution time — ratio inverts with FPU presence")
    ax.legend(loc="upper right")

    ps.add_footnote(
        fig,
        f"Bars = median, error bars = IQR (25th–75th percentile); {ps.reps_phrase(reps)}. "
        f"Label = h_all / bell_ghz ratio. n = {n} chosen as the highest qubit count with both "
        "circuits measured on every board shown (controlled comparison — same n for all boards).",
    )
    ps.save_figure(fig, FIGURES_DIR, "fpu_ratio_comparison")

    for board in boards:
        fpu = "has FPU" if board == "esp32" else "no FPU"
        print(f"  {board:8s} ({fpu:7s})  h_all/bell_ghz ratio at n={n} = {ratios[board]:.3g}")


if __name__ == "__main__":
    main()
