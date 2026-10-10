#!/usr/bin/env python3
# phase2_fpu_ratio_own_n_plot.py
# กราฟ "FPU effect" ที่ n ของใครของมัน (own operating point) — คู่กับ
# phase2_fpu_ratio_plot.py ที่ตรึง n เดียวกันทุกบอร์ด (controlled comparison)
# ตรรกะร่วมกันอยู่ที่ analysis/_fpu_ratio_common.py คนละคำถาม ไม่ใช่กราฟซ้ำ:
#
#   fpu_ratio_comparison.png     — ตัดตัวแปรขนาดปัญหาออก เหลือแต่ผล FPU ล้วน ๆ
#   fpu_ratio_comparison_own_n   — แต่ละบอร์ดที่ n ที่ตัวเองใช้งานได้จริงสูงสุด (ตรงกับ
#   (ไฟล์นี้)                     วิธีรายงานผลเดิมของ dataset n=30: Uno ที่กำแพงของ Uno,
#                                  ESP8266 ที่กำแพงของ ESP8266, ESP32 ที่กำแพงของ ESP32
#                                  — คนละ n กัน ไม่ใช่ n เดียวที่ใช้ร่วมกัน)
#
# เลือก n ต่อบอร์ด: หา n สูงสุดที่บอร์ดนั้น (เท่านั้น) มีข้อมูลทั้ง h_all และ bell_ghz
# พร้อมกัน อิสระจากบอร์ดอื่น — ไม่ hardcode 7/12/13 ตามที่ dataset n=30 เคยได้ ค่านั้น
# มาจาก Memory Wall ของแต่ละบอร์ดในรอบนั้น ซึ่งไม่รับประกันว่าจะซ้ำเดิมในรอบ n=100 นี้
# n ที่ใช้จริงต่อบอร์ดแสดงไว้บนแกน x ตรง ๆ (ไม่ใช่แค่ใน caption) กันคนดูงงว่าทำไมแต่ละ
# กลุ่มลึกไม่เท่ากัน
#
# แหล่งข้อมูล: data/processed/phase2/summary.csv (คอลัมน์จาก phase2_summarize.py:
# board, circuit, n, n_trials, median_exec_time_us, iqr_low_us, iqr_high_us, iqr_width_us)
# ผลลัพธ์: data/figures/phase2/fpu_ratio_comparison_own_n.png

import sys
from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import plot_style as ps  # noqa: E402
from phase2_plot import load_summary  # noqa: E402
from _fpu_ratio_common import (  # noqa: E402
    boards_with_both_circuits, draw_ratio_bars, find_own_n, index_by_board_circuit_n,
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
    if not boards:
        raise SystemExit("error: no board has both h_all and bell_ghz data — "
                         "check data/processed/phase2/summary.csv coverage")

    n_by_board = {}
    for board in boards:
        n = find_own_n(idx, board)
        if n is not None:
            n_by_board[board] = n
    boards = [b for b in boards if b in n_by_board]  # เผื่อกรณีขอบ (ไม่ควรเกิดถ้าผ่าน boards_with_both_circuits แล้ว)
    if not boards:
        raise SystemExit("error: no board has an n with both h_all and bell_ghz data")

    ps.apply_style()
    fig, ax = plt.subplots(figsize=(7.5, 5.5), layout="constrained")
    ratios, reps = draw_ratio_bars(ax, boards, n_by_board, idx, ps)

    ax.set_xticks(range(len(boards)))
    ax.set_xticklabels([f"{ps.BOARD_LABEL[b]}\n(n = {n_by_board[b]})" for b in boards])
    ps.style_axes(ax, log_y=True, integer_x=False)
    ax.set_ylabel("Execution time at each board's own n (µs, log scale)")
    ax.set_title("Hadamard vs Bell State execution time — ratio inverts with FPU presence\n"
                 "(each board at its own highest measured n)")
    ax.legend(loc="upper right")

    n_desc = ", ".join(f"{ps.BOARD_SHORT[b]} n={n_by_board[b]}" for b in boards)
    ps.add_footnote(
        fig,
        f"Bars = median, error bars = IQR (25th–75th percentile); {ps.reps_phrase(reps)}. "
        f"Label = h_all / bell_ghz ratio. Each board shown at its own highest n with both "
        f"circuits measured ({n_desc}) — n differs per board, unlike fpu_ratio_comparison.png.",
    )
    ps.save_figure_png_only(fig, FIGURES_DIR, "fpu_ratio_comparison_own_n")

    for board in boards:
        fpu = "has FPU" if board == "esp32" else "no FPU"
        n = n_by_board[board]
        print(f"  {board:8s} ({fpu:7s})  n={n:2d}  h_all/bell_ghz ratio = {ratios[board]:.3g}")


if __name__ == "__main__":
    main()
