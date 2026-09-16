#!/usr/bin/env python3
# phase2_fpu_ratio_plot.py
# กราฟ "FPU effect" — เดิมรายงานเป็นตารางตัวเลขเท่านั้น (chapter4_results_th.md เวอร์ชัน
# n=30 §4.2.9) ไม่เคยมีรูป: เทียบเวลา local execution ของ h_all กับ bell_ghz ที่ n เดียวกัน
# ข้ามทั้ง 3 บอร์ด — h_all มีเกท H หนาแน่นกว่า (คำนวณเลขจุดทศนิยมเยอะกว่า) ส่วน bell_ghz
# ส่วนใหญ่เป็น CNOT (สลับ index ล้วน แทบไม่มีเลขจุดทศนิยม) บอร์ดที่มี FPU ฮาร์ดแวร์
# (ESP32) จึงได้เปรียบ h_all มากกว่า bell_ghz อย่างไม่สมส่วน จนอัตราส่วน h_all/bell_ghz
# "กลับด้าน" เทียบกับบอร์ดที่ไม่มี FPU (Uno, ESP8266)
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

FIGURES_DIR = REPO_ROOT / "data" / "figures" / "phase2"
CIRCUITS = ("h_all", "bell_ghz")  # อัตราส่วนที่สนใจคือ h_all / bell_ghz เท่านั้น


def index_by_board_circuit_n(summary_rows):
    """{(board, circuit, n): row} — row มี median_exec_time_us, iqr_low_us, iqr_high_us, n_trials"""
    idx = {}
    for r in summary_rows:
        idx[(r["board"], r["circuit"], int(r["n"]))] = r
    return idx


def find_common_n(idx, boards):
    """n สูงสุดที่ h_all และ bell_ghz มีข้อมูลอยู่พร้อมกันในทุกบอร์ดที่ระบุ
    คำนวณจากข้อมูลจริง ไม่ hardcode — ดู docstring ระดับไฟล์"""
    per_board_common = []
    for board in boards:
        ns_h = {n for (b, c, n) in idx if b == board and c == "h_all"}
        ns_b = {n for (b, c, n) in idx if b == board and c == "bell_ghz"}
        per_board_common.append(ns_h & ns_b)
    if not per_board_common:
        return None
    common = set.intersection(*per_board_common)
    return max(common) if common else None


def main():
    summary_rows = load_summary()
    if not summary_rows:
        raise SystemExit("error: data/processed/phase2/summary.csv ว่างเปล่า หรือไม่มี — "
                         "รัน analysis/phase2_summarize.py ก่อน")
    idx = index_by_board_circuit_n(summary_rows)

    boards = [b for b in ps.BOARD_ORDER
              if any(bd == b and c in CIRCUITS for (bd, c, n) in idx)]
    missing_circuit = [b for b in boards
                        if not all(any(bd == b and c == circ for (bd, c, n) in idx) for circ in CIRCUITS)]
    if missing_circuit:
        boards = [b for b in boards if b not in missing_circuit]
        print(f"warning: skipping board(s) missing h_all or bell_ghz data entirely: {missing_circuit}")
    if len(boards) < 2:
        raise SystemExit("error: need at least 2 boards with both h_all and bell_ghz data "
                         "to compare the FPU effect")

    n = find_common_n(idx, boards)
    if n is None:
        raise SystemExit(
            "error: no single n has h_all AND bell_ghz data for every board "
            f"({', '.join(boards)}) — check data/processed/phase2/summary.csv coverage"
        )

    ps.apply_style()
    fig, ax = plt.subplots(figsize=(7.5, 5.5), layout="constrained")
    width = 0.36
    reps = []
    ratios = {}

    for i, board in enumerate(boards):
        for j, circuit in enumerate(CIRCUITS):
            row = idx[(board, circuit, n)]
            median = float(row["median_exec_time_us"])
            lo = median - float(row["iqr_low_us"])
            hi = float(row["iqr_high_us"]) - median
            reps.append(int(row["n_trials"]))
            x = i + (j - 0.5) * width
            ax.bar(
                x, median, width, yerr=[[lo], [hi]], capsize=4,
                facecolor=ps.CIRCUIT_INK[circuit], hatch=ps.CIRCUIT_HATCH[circuit],
                edgecolor="white", linewidth=0.8, error_kw={"ecolor": ps.INK_SECONDARY, "elinewidth": 1.2},
                zorder=3, label=ps.CIRCUIT_LABEL[circuit] if i == 0 else None,
            )
        h_all_median = float(idx[(board, "h_all", n)]["median_exec_time_us"])
        bell_median = float(idx[(board, "bell_ghz", n)]["median_exec_time_us"])
        ratio = h_all_median / bell_median
        ratios[board] = ratio
        top = max(h_all_median, bell_median)
        ax.annotate(f"{ratio:.2g}×", xy=(i, top), xytext=(0, 6), textcoords="offset points",
                    ha="center", va="bottom", fontsize=10, fontweight="bold", color=ps.INK_PRIMARY)

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
        "circuits measured on every board shown.",
    )
    ps.save_figure(fig, FIGURES_DIR, "fpu_ratio_comparison")

    for board in boards:
        fpu = "has FPU" if board == "esp32" else "no FPU"
        print(f"  {board:8s} ({fpu:7s})  h_all/bell_ghz ratio at n={n} = {ratios[board]:.3g}")


if __name__ == "__main__":
    main()
