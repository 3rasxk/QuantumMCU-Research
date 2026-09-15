#!/usr/bin/env python3
# appendix_c_memory_wall_bar.py — ภาคผนวก ค, ภาพที่ ค-11
# Grouped bar chart: n สูงสุดตามทฤษฎี (2^n * 8 bytes <= SRAM รวม) เทียบ n สูงสุด
# ที่วัดได้จริง (รันสำเร็จก่อนเจอ Memory Wall) แยกตามบอร์ด
#
# แหล่งข้อมูล: results/phase2/memory_wall_summary.csv — ไฟล์นี้ถูกสร้างโดย
# analysis/phase2_plot.py::plot_memory_wall() อยู่แล้ว จากข้อมูลดิบ
# results/phase2/*_memory_wall.csv (สถานะ ok/build_or_upload_fail/runtime_hang_or_reset
# ต่อ n ต่อบอร์ด) รวมกับค่าคงที่ SRAM ของแต่ละบอร์ด — ใช้ไฟล์สรุปนี้ตรง ๆ แทนการ
# คำนวณ theoretical_max_n ซ้ำเป็นครั้งที่สาม (ซ้ำกับ phase2_plot.py และรายงาน
# บทที่ 4 §4.2.10 อยู่แล้ว) เพื่อไม่ให้ตัวเลขเพี้ยนกันระหว่างที่มา
#
# หากต้องการรันใหม่จากข้อมูลดิบ: รัน analysis/phase2_plot.py ก่อน (มันเขียน
# memory_wall_summary.csv ทับให้อัตโนมัติจาก *_memory_wall.csv ล่าสุด)
#
# ผลลัพธ์: results/phase2/memory_wall_comparison.png (300 DPI)

import csv
from pathlib import Path

import matplotlib
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results" / "phase2"
SUMMARY_PATH = RESULTS_DIR / "memory_wall_summary.csv"
OUT_PATH = RESULTS_DIR / "memory_wall_comparison.png"
FONT_PATH = Path.home() / "Library" / "Fonts" / "THSarabunNew.ttf"

# ลำดับการแสดงผลคงที่ (ไม่ใช้ sorted() เพราะ alphabetical จะได้ esp32,esp8266,uno
# ซึ่งไม่ใช่ลำดับที่รายงานใช้ — รายงานเรียงจากบอร์ดเล็กสุดไปใหญ่สุดเสมอ: Uno -> ESP8266 -> ESP32)
BOARD_ORDER = ["uno", "esp8266", "esp32"]
BOARD_LABEL = {"uno": "Arduino Uno R3", "esp8266": "NodeMCU ESP8266", "esp32": "ESP32 DevKit V1"}


def load_font():
    if FONT_PATH.exists():
        fm.fontManager.addfont(str(FONT_PATH))
        matplotlib.rcParams["font.family"] = fm.FontProperties(fname=str(FONT_PATH)).get_name()


def load_summary():
    if not SUMMARY_PATH.exists():
        raise SystemExit(
            f"error: {SUMMARY_PATH} not found. รัน analysis/phase2_plot.py ก่อน "
            "เพื่อสร้างไฟล์นี้จากข้อมูลดิบ results/phase2/*_memory_wall.csv"
        )
    rows = {}
    with open(SUMMARY_PATH, newline="") as f:
        for r in csv.DictReader(f):
            rows[r["board"]] = r
    return rows


def main():
    load_font()
    rows = load_summary()
    boards = [b for b in BOARD_ORDER if b in rows]

    theo_ns = [int(rows[b]["theoretical_max_n"]) for b in boards]
    meas_ns = [int(rows[b]["measured_max_n_safe"]) for b in boards]

    x = range(len(boards))
    width = 0.34
    fig, ax = plt.subplots(figsize=(8, 5.5), dpi=300)
    ax.set_facecolor("#fcfcfb")

    bars_theo = ax.bar(
        [i - width / 2 for i in x], theo_ns, width,
        label="ทฤษฎี (2^n × 8 bytes ≤ SRAM รวม)", color="#9a9a9a", zorder=3,
    )
    bars_meas = ax.bar(
        [i + width / 2 for i in x], meas_ns, width,
        label="วัดจริง (n สูงสุดที่รันสำเร็จ)", color="#2a78d6", zorder=3,
    )
    for bars in (bars_theo, bars_meas):
        ax.bar_label(bars, fontsize=10.5, padding=3, color="#2a2a2a")

    ax.set_xticks(list(x))
    ax.set_xticklabels([BOARD_LABEL[b] for b in boards], fontsize=11.5)
    ax.set_ylabel("จำนวนคิวบิตสูงสุด (n)", fontsize=12)
    ax.set_title("Memory Wall: ค่าทฤษฎี เทียบ ค่าที่วัดได้จริง", fontsize=13.5, pad=14)
    ax.set_ylim(0, max(theo_ns + meas_ns) * 1.2)
    ax.grid(True, which="major", axis="y", alpha=0.3, linewidth=0.8, zorder=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(fontsize=10, loc="upper left", frameon=False)
    fig.tight_layout()

    fig.savefig(OUT_PATH, bbox_inches="tight", dpi=300)
    print(f"graph -> {OUT_PATH}")

    for b in boards:
        gap = theo_ns[boards.index(b)] - meas_ns[boards.index(b)]
        print(f"  {b:8s} theoretical={theo_ns[boards.index(b)]:2d}  measured={meas_ns[boards.index(b)]:2d}  gap={gap} qubit(s)")


if __name__ == "__main__":
    main()
