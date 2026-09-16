#!/usr/bin/env python3
# phase4_flowchart.py
# วาด Decision Flowchart ของ Phase 4 (Local vs Offload) ด้วย matplotlib เอง
# (ไม่ใช้ไลบรารี graph เฉพาะทาง เพื่อคุมสไตล์ให้ตรงกับกราฟอื่นใน pc/shared/plot_style.py)
#
# ใช้หมึกเทาล้วน ไม่ใช้สีบอร์ด — สีน้ำเงิน/ส้ม/เขียวสงวนไว้บอก Uno/ESP8266/ESP32 เท่านั้น
# ค่าคงที่ตัวปรับสถาปัตยกรรม (+x คิวบิต) ไม่ใส่เป็นตัวเลข เพราะมาจาก dataset n=30 ที่ถูก
# แทนที่แล้ว — ต้องคำนวณใหม่จากข้อมูล REPS=100 ก่อนจึงจะใส่กลับได้
#
# ผลลัพธ์: data/figures/phase4/decision_flowchart.{png,svg}

import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import plot_style as ps  # noqa: E402

OUT_DIR = REPO_ROOT / "data" / "figures" / "phase4"

FILL_STEP = "#3a3a3a"      # กล่องขั้นตอน/คำถาม (ตัวอักษรขาว)
FILL_DETAIL = "#eeeeee"    # กล่องสูตร/รายละเอียด
FILL_OUTCOME = "#ffffff"   # ผลลัพธ์ LOCAL / OFFLOAD (กรอบหนา)
FILL_NOTE = "#f6f6f6"      # ข้อควรพิจารณา


def box(ax, xy, w, h, text, fc, text_color=ps.INK_PRIMARY, fontsize=10, lw=1.2, weight="normal"):
    x, y = xy
    patch = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=lw, edgecolor=ps.INK_PRIMARY, facecolor=fc,
    )
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize, color=text_color,
            linespacing=1.4, weight=weight)


def arrow(ax, start, end, label=None, label_offset=(0, 0.2), ha="center", va="bottom"):
    a = FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=14,
                        linewidth=1.3, color=ps.INK_SECONDARY)
    ax.add_patch(a)
    if label:
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        ax.text(mx + label_offset[0], my + label_offset[1], label, fontsize=9,
                ha=ha, va=va, color=ps.INK_PRIMARY, linespacing=1.2)


def main():
    ps.apply_style()
    fig, ax = plt.subplots(figsize=(9, 10.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(4.0, 26)
    ax.axis("off")

    box(ax, (5, 25), 6.5, 1.4, "Start: a circuit to run\non n qubits", FILL_DETAIL, fontsize=10.5)

    box(ax, (5, 22.5), 7.5, 1.6, "Step 1 — Memory Wall\nEstimate the board's n_max",
        FILL_STEP, text_color="white", fontsize=10.5)
    arrow(ax, (5, 24.3), (5, 23.3))

    box(ax, (5, 19.8), 8.5, 2.2,
        "n_max = floor(log₂(B / 8))\n"
        "B = largest contiguous free block (bytes), if measurable\n"
        "otherwise B ≈ total SRAM / 2 (one qubit below raw theory)",
        FILL_DETAIL, fontsize=9.5)
    arrow(ax, (5, 21.7), (5, 20.9))

    box(ax, (4.3, 17), 3.4, 1.6, "n > n_max ?", FILL_STEP, text_color="white", fontsize=11)
    arrow(ax, (5, 18.7), (4.3, 17.8))

    box(ax, (8.5, 17), 2.6, 1.4, "OFFLOAD\n(only option)", FILL_OUTCOME, lw=2.2, weight="bold")
    arrow(ax, (6.0, 17), (7.2, 17), "Yes\n(exceeds local\nmemory)", label_offset=(0, 0.2))

    box(ax, (5, 14.3), 7.8, 1.9,
        "Step 2 — Crossover Point\nEstimate n* from board class\nand circuit type",
        FILL_STEP, text_color="white", fontsize=10.5)
    arrow(ax, (4.3, 16.2), (5, 15.3), "No (fits in memory)", label_offset=(0.35, 0), ha="left", va="center")

    box(ax, (5, 11.6), 8.8, 2.6,
        "n* ≈ n*_reference + log₂(clock_new / clock_reference)\n"
        "      + architecture adjustment\n"
        "(word size, hardware FPU; constants to be\n"
        "re-derived from the REPS=100 dataset)",
        FILL_DETAIL, fontsize=9.5)
    arrow(ax, (5, 13.35), (5, 12.9))

    box(ax, (5, 8.6), 3.0, 1.6, "n < n* ?", FILL_STEP, text_color="white", fontsize=11)
    arrow(ax, (5, 10.3), (5, 9.4))

    box(ax, (1.5, 8.6), 2.6, 1.9, "LOCAL\n(faster than\noffload)", FILL_OUTCOME, lw=2.2, weight="bold",
        fontsize=9.5)
    arrow(ax, (3.5, 8.6), (2.8, 8.6), "Yes")

    box(ax, (8.5, 8.6), 2.6, 1.9, "OFFLOAD\n(faster than\nlocal)", FILL_OUTCOME, lw=2.2, weight="bold",
        fontsize=9.5)
    arrow(ax, (6.5, 8.6), (7.2, 8.6), "No")

    box(ax, (5, 5.6), 8.8, 2.4,
        "Considerations beyond speed:\n"
        "• Offload depends on the PC and serial link at all times\n"
        "  (an extra point of failure)\n"
        "• Local failure mode depends on memory policy\n"
        "  (static = silent hang, dynamic = detectable OOM)",
        FILL_NOTE, fontsize=9)
    arrow(ax, (1.5, 7.65), (3.3, 6.8))
    arrow(ax, (8.5, 7.65), (6.7, 6.8))

    fig.suptitle("Phase 4 — Decision flowchart: local simulation vs offload", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    ps.add_footnote(fig, "Schematic decision rule; not a data plot. "
                         "Architecture adjustment constants pending the REPS=100 rerun.")
    ps.save_figure(fig, OUT_DIR, "decision_flowchart")


if __name__ == "__main__":
    main()
