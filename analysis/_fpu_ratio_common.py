#!/usr/bin/env python3
# _fpu_ratio_common.py — ตรรกะร่วมของกราฟ FPU ratio ทั้ง 2 แบบ:
#   phase2_fpu_ratio_plot.py         (n เดียวกันทุกบอร์ด — คุมตัวแปร n ออก เห็นผล FPU ล้วน ๆ)
#   phase2_fpu_ratio_own_n_plot.py   (n ของใครของมัน — ที่ operating point จริงของแต่ละบอร์ด)
#
# ไม่ใช่สคริปต์ที่รันตรง ๆ (ชื่อขึ้นต้น _ ตามธรรมเนียม private module) — ทั้งสองไฟล์ด้านบน
# import จากที่นี่แทนการก๊อปโค้ดวาดกราฟซ้ำ เหตุผลเดียวกับที่ pc/shared/circuit_ids.py
# ถูกรวมเป็นแหล่งเดียว: ตรรกะเดียวกัน 2 สำเนาคือความเสี่ยง ไม่ใช่ฟีเจอร์
#
# ไม่ import matplotlib/pyplot โดยตรงที่ module level ยกเว้นใน draw_ratio_bars (รับ ax
# ที่สร้างไว้แล้วจากผู้เรียก) เพื่อไม่ผูก backend/figure lifecycle ไว้ที่นี่

CIRCUITS = ("h_all", "bell_ghz")  # อัตราส่วนที่ทั้งสองกราฟสนใจคือ h_all / bell_ghz เท่านั้น


def index_by_board_circuit_n(summary_rows):
    """{(board, circuit, n): row} — row มี median_exec_time_us, iqr_low_us, iqr_high_us, n_trials
    (คอลัมน์จาก analysis/phase2_summarize.py)"""
    idx = {}
    for r in summary_rows:
        idx[(r["board"], r["circuit"], int(r["n"]))] = r
    return idx


def boards_with_both_circuits(idx, board_order):
    """บอร์ดที่มีข้อมูลทั้ง h_all และ bell_ghz อย่างน้อย 1 จุด (ไม่จำเป็นต้อง n เดียวกัน)
    เรียงตาม board_order (ปกติคือ pc/shared/plot_style.BOARD_ORDER)
    คืน (boards_ok, boards_missing) — ผู้เรียกเป็นคนตัดสินใจว่าจะพิมพ์ warning เอง"""
    boards_ok, boards_missing = [], []
    for board in board_order:
        has = {c for (b, c, n) in idx if b == board}
        if set(CIRCUITS) <= has:
            boards_ok.append(board)
        elif has & set(CIRCUITS):
            # มีวงจรหนึ่งแต่ไม่ครบทั้งคู่ — ไม่ใช่แค่ไม่มีข้อมูลบอร์ดนี้เลย ต้องบอกให้รู้
            boards_missing.append(board)
    return boards_ok, boards_missing


def find_common_n(idx, boards):
    """n สูงสุดที่ h_all และ bell_ghz มีข้อมูลอยู่พร้อมกันใน "ทุกบอร์ด" ที่ระบุ (n เดียว
    ใช้ร่วมกันทั้งหมด) — ใช้โดย phase2_fpu_ratio_plot.py"""
    per_board_common = []
    for board in boards:
        ns_h = {n for (b, c, n) in idx if b == board and c == "h_all"}
        ns_b = {n for (b, c, n) in idx if b == board and c == "bell_ghz"}
        per_board_common.append(ns_h & ns_b)
    if not per_board_common:
        return None
    common = set.intersection(*per_board_common)
    return max(common) if common else None


def find_own_n(idx, board):
    """n สูงสุดที่บอร์ดนี้ (เท่านั้น) มีข้อมูลทั้ง h_all และ bell_ghz พร้อมกัน — ของใครของมัน
    ไม่เกี่ยวกับบอร์ดอื่น — ใช้โดย phase2_fpu_ratio_own_n_plot.py"""
    ns_h = {n for (b, c, n) in idx if b == board and c == "h_all"}
    ns_b = {n for (b, c, n) in idx if b == board and c == "bell_ghz"}
    common = ns_h & ns_b
    return max(common) if common else None


def draw_ratio_bars(ax, boards, n_by_board, idx, ps):
    """วาดกราฟแท่งกลุ่ม 2 แท่งต่อบอร์ด (h_all, bell_ghz) ที่ n ของบอร์ดนั้น ๆ ตาม
    n_by_board (จะเป็น n เดียวกันทุกบอร์ด หรือคนละ n ก็ได้ — ฟังก์ชันนี้ไม่สนใจ)
    วาด error bar จาก IQR และ label อัตราส่วน h_all/bell_ghz เหนือแต่ละกลุ่ม

    ps = pc/shared/plot_style module (ส่งเข้ามาแทนการ import ที่นี่ เพื่อไม่ผูก sys.path
    setup ไว้ใน module ที่ไม่ใช่ entry point)

    คืน (ratios, reps): ratios = {board: h_all/bell_ghz}, reps = list ของ n_trials ทุกแท่ง
    (ใช้คำนวณ footnote จำนวน repetition ที่ผู้เรียก)"""
    width = 0.36
    reps = []
    ratios = {}

    for i, board in enumerate(boards):
        n = n_by_board[board]
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
                edgecolor="white", linewidth=0.8,
                error_kw={"ecolor": ps.INK_SECONDARY, "elinewidth": 1.2},
                zorder=3, label=ps.CIRCUIT_LABEL[circuit] if i == 0 else None,
            )
        h_all_median = float(idx[(board, "h_all", n)]["median_exec_time_us"])
        bell_median = float(idx[(board, "bell_ghz", n)]["median_exec_time_us"])
        ratio = h_all_median / bell_median
        ratios[board] = ratio
        top = max(h_all_median, bell_median)
        ax.annotate(f"{ratio:.2g}×", xy=(i, top), xytext=(0, 6), textcoords="offset points",
                    ha="center", va="bottom", fontsize=10, fontweight="bold", color=ps.INK_PRIMARY)

    return ratios, reps
