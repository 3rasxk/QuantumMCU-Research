#!/usr/bin/env python3
# appendix_c_memory_wall_bar.py — ภาคผนวก ค
# Grouped bar chart: n สูงสุดตามทฤษฎี (2^n * 8 bytes <= SRAM รวม) เทียบ n สูงสุด
# ที่วัดได้จริง (รันสำเร็จก่อนเจอ Memory Wall) แยกตามบอร์ด
#
# แหล่งข้อมูล: data/processed/phase2/memory_wall_summary.csv — ไฟล์นี้ถูกสร้างโดย
# analysis/phase2_plot.py จากข้อมูลดิบ data/raw/phase2/<board>/<circuit>/memory_wall.csv
# (เส้นทางเปลี่ยนเมื่อ 2026-09-20, ดู run_log.md) — ใช้ไฟล์สรุป
# นี้ตรง ๆ แทนการคำนวณ theoretical_max_n ซ้ำ เพื่อไม่ให้ตัวเลขเพี้ยนกันระหว่างที่มา
# วาดด้วย phase2_plot.draw_memory_wall() ตัวเดียวกัน ภาพจึงตรงกันทุกประการ — สคริปต์นี้มี
# ไว้สร้างภาพใหม่จากไฟล์สรุปได้โดยไม่ต้องมีข้อมูลดิบ
#
# หากต้องการรันใหม่จากข้อมูลดิบ: รัน analysis/phase2_plot.py แทน (มันเขียน
# memory_wall_summary.csv ทับให้อัตโนมัติจาก *_memory_wall.csv ล่าสุด)
#
# ผลลัพธ์: data/figures/phase2/memory_wall_comparison.png

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pc"))
from shared import plot_style as ps  # noqa: E402
from phase2_plot import (  # noqa: E402
    MEMORY_WALL_SUMMARY_PATH, draw_memory_wall, load_summary, reps_by_board,
)


def main():
    if not MEMORY_WALL_SUMMARY_PATH.exists():
        raise SystemExit(
            f"error: {MEMORY_WALL_SUMMARY_PATH} not found. รัน analysis/phase2_plot.py ก่อน "
            "เพื่อสร้างไฟล์นี้จากข้อมูลดิบ data/raw/phase2/<board>/<circuit>/memory_wall.csv"
        )
    with open(MEMORY_WALL_SUMMARY_PATH, newline="") as f:
        summary = list(csv.DictReader(f))
    ps.apply_style()
    draw_memory_wall(summary, reps_by_board(load_summary()))


if __name__ == "__main__":
    main()
