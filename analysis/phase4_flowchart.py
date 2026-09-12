#!/usr/bin/env python3
# phase4_flowchart.py
# วาด Decision Flowchart ของ Phase 4 (Local vs Offload) ด้วย matplotlib เอง
# (ไม่ใช้ไลบรารี graph เฉพาะทาง เพื่อควบคุมฟอนต์ไทยและสไตล์ให้ตรงกับกราฟอื่นในรายงาน)

from pathlib import Path

import matplotlib
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "results" / "phase4"
FONT_PATH = Path.home() / "Library" / "Fonts" / "THSarabunNew.ttf"

COLOR_DECISION = "#767676"
COLOR_LOCAL = "#2a78d6"
COLOR_OFFLOAD = "#eb6834"
COLOR_START = "#159873"


def load_font():
    if FONT_PATH.exists():
        fm.fontManager.addfont(str(FONT_PATH))
        matplotlib.rcParams["font.family"] = fm.FontProperties(fname=str(FONT_PATH)).get_name()


def box(ax, xy, w, h, text, fc, text_color="white", fontsize=11):
    x, y = xy
    patch = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.5, edgecolor="#4a4a4a", facecolor=fc,
    )
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=fontsize, color=text_color, linespacing=1.4)


def arrow(ax, start, end, label=None, label_offset=(0.15, 0)):
    a = FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=14,
                          linewidth=1.5, color="#4a4a4a")
    ax.add_patch(a)
    if label:
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        ax.text(mx + label_offset[0], my + label_offset[1], label, fontsize=9.5,
                 ha="left", va="center", color="#2a2a2a")


def main():
    load_font()
    fig, ax = plt.subplots(figsize=(9, 12), dpi=220)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 26)
    ax.axis("off")

    box(ax, (5, 25), 6.5, 1.4, "เริ่มต้น: มี n (จำนวนคิวบิต)\nและวงจรที่ต้องการรัน", COLOR_START)

    box(ax, (5, 22.5), 7.5, 1.6,
        "ขั้นที่ 1 — Memory Wall\nคำนวณ n_max ของบอร์ด",
        COLOR_DECISION)
    arrow(ax, (5, 24.3), (5, 23.3))

    box(ax, (5, 19.8), 8.5, 2.2,
        "n_max = floor(log2(B / 8))\nB = largest contiguous free block (ถ้าวัดได้)\n"
        "หรือ B = SRAM รวม − 1 คิวบิต (ถ้าเป็น static-allocation\nล้วน หรือไม่ทราบค่า largest block)",
        "#e8e8e8", text_color="#2a2a2a", fontsize=10)
    arrow(ax, (5, 21.7), (5, 20.9))

    box(ax, (4.3, 17), 3.4, 1.6, "n > n_max ?", COLOR_DECISION)
    arrow(ax, (5, 18.7), (4.3, 17.8))

    box(ax, (8.5, 17), 2.6, 1.4, "OFFLOAD\n(ทางเลือกเดียว)", COLOR_OFFLOAD)
    arrow(ax, (6.0, 17), (7.2, 17), "ใช่ (n เกิน\nความจุ local)")

    box(ax, (5, 14.3), 7.8, 1.9,
        "ขั้นที่ 2 — Crossover Point\nประมาณ n* จากคลาสบอร์ด + ชนิดวงจร\n(ดูตารางที่ 4.12)",
        COLOR_DECISION)
    arrow(ax, (4.3, 16.2), (5, 15.3), "ไม่ (ยังพอมี\nหน่วยความจำ)", label_offset=(-3.4, -0.1))

    box(ax, (5, 11.6), 8.8, 2.6,
        "n* ≈ n*_อ้างอิง + log2(clock ใหม่ / clock อ้างอิง)\n"
        "+ ปรับเพิ่มถ้าบอร์ดใหม่มี FPU แต่บอร์ดอ้างอิงไม่มี\n"
        "(ประมาณ +3 ถึง +5 คิวบิต จากข้อมูล 3 บอร์ดที่ทดสอบจริง\n"
        "ขึ้นกับความหนาแน่นการคำนวณเลขจุดทศนิยมของวงจร)",
        "#e8e8e8", text_color="#2a2a2a", fontsize=9.5)
    arrow(ax, (5, 13.35), (5, 12.9))

    box(ax, (5, 8.6), 3.0, 1.6, "n < n* ?", COLOR_DECISION)
    arrow(ax, (5, 10.3), (5, 9.4))

    box(ax, (1.5, 8.6), 2.6, 1.4, "LOCAL\n(เร็วกว่า offload)", COLOR_LOCAL)
    arrow(ax, (3.5, 8.6), (2.8, 8.6), "ใช่")

    box(ax, (8.5, 8.6), 2.6, 1.4, "OFFLOAD\n(เร็วกว่า local)", COLOR_OFFLOAD)
    arrow(ax, (6.5, 8.6), (7.2, 8.6), "ไม่")

    box(ax, (5, 5.6), 8.8, 2.4,
        "ข้อควรพิจารณาเพิ่มเติมนอกเหนือความเร็ว:\n"
        "• Offload ต้องพึ่ง PC/serial link ตลอดเวลา (จุดล้มเหลวเพิ่ม)\n"
        "• Local ล้มเหลวแบบต่างกันตามนโยบายหน่วยความจำ\n"
        "  (static = hang เงียบ, dynamic = ตรวจจับได้)",
        "#fff3cd", text_color="#5a4a1a", fontsize=9.5)
    arrow(ax, (1.5, 7.9), (3.3, 6.6))
    arrow(ax, (8.5, 7.9), (6.7, 6.6))

    fig.suptitle("ภาพที่ 4.10  Decision Flowchart: Local vs Offload", fontsize=13, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out_path = OUT_DIR / "fig_phase4_decision_flowchart.png"
    fig.savefig(out_path)
    print(f"flowchart -> {out_path}")


if __name__ == "__main__":
    main()
